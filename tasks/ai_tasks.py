"""
AI-related Celery tasks:
  - score_conversation_qa      — QA scoring after conversation is resolved
  - generate_bot_response      — Generate and send AI bot reply
  - process_kb_document        — Generate embeddings for KB article/document
  - calculate_qa_score         — Alias kept for backwards-compat (calls score_conversation_qa)
"""
import structlog
from celery import shared_task
from django.utils import timezone

logger = structlog.get_logger(__name__)


@shared_task(
    bind=True,
    name='tasks.ai_tasks.score_conversation_qa',
    max_retries=3,
    default_retry_delay=30,
    queue='ai',
)
def score_conversation_qa(self, conv_id: str) -> dict:
    """
    Score a resolved conversation for quality assurance.

    Scoring dimensions:
      - Response speed (time to first agent/bot reply)
      - Resolution quality (was conversation actually resolved?)
      - Sentiment (positive = bonus, negative = penalty)
      - Escalation (escalated = penalty)
      - Message exchange ratio

    Result saved to QAScore model, linked to conversation.
    """
    try:
        from apps.conversations.models import Conversation, QAScore

        conv = (
            Conversation.objects
            .select_related('contact', 'assigned_agent')
            .prefetch_related('messages')
            .get(id=conv_id)
        )

        messages = list(conv.messages.order_by('timestamp'))
        if not messages:
            logger.info('qa_score_skipped_no_messages', conv_id=conv_id)
            return {'status': 'skipped', 'reason': 'no_messages'}

        score = 70  # Base score
        total_msgs = len(messages)
        agent_msgs = [m for m in messages if m.role == 'agent']
        bot_msgs = [m for m in messages if m.role == 'bot']
        user_msgs = [m for m in messages if m.role == 'user']

        # ── Response coverage ───────────────────────────────────────────────
        if not agent_msgs and not bot_msgs:
            score -= 25  # No response at all — major penalty
        elif agent_msgs or bot_msgs:
            score += 5   # Some response given

        # ── Response time ────────────────────────────────────────────────────
        if len(messages) >= 2 and user_msgs:
            first_user = user_msgs[0].timestamp
            responders = [m for m in messages if m.role in ('agent', 'bot') and m.timestamp > first_user]
            if responders:
                response_secs = (responders[0].timestamp - first_user).total_seconds()
                if response_secs < 60:
                    score += 15
                elif response_secs < 300:
                    score += 8
                elif response_secs > 1800:
                    score -= 15

        # ── Resolution quality ───────────────────────────────────────────────
        if conv.estado == 'resuelto':
            score += 10
            if conv.resolved_at and conv.created_at:
                duration_min = (conv.resolved_at - conv.created_at).total_seconds() / 60
                if duration_min < 5:
                    score += 10
                elif duration_min < 15:
                    score += 5
                elif duration_min > 60:
                    score -= 10
        elif conv.estado == 'escalado':
            score -= 10  # Escalation is a quality signal

        # ── Sentiment ────────────────────────────────────────────────────────
        if conv.sentimiento == 'positivo':
            score += 10
        elif conv.sentimiento == 'negativo':
            score -= 15

        # ── Message ratio (back-and-forth) ───────────────────────────────────
        if total_msgs > 10:
            score += 5  # Deep engagement bonus

        score = max(0, min(100, score))

        QAScore.objects.update_or_create(
            conversation=conv,
            defaults={
                'score': score,
                'notes': (
                    f'Auto QA | msgs={total_msgs} agent_msgs={len(agent_msgs)} '
                    f'sentiment={conv.sentimiento} estado={conv.estado}'
                ),
            },
        )

        logger.info('qa_scored', conv_id=conv_id, score=score, estado=conv.estado)
        return {'status': 'ok', 'conv_id': conv_id, 'score': score}

    except Exception as exc:
        logger.error('qa_score_error', conv_id=conv_id, error=str(exc), exc_info=True)
        raise self.retry(exc=exc)


# Keep backwards-compat alias
calculate_qa_score = score_conversation_qa


@shared_task(
    bind=True,
    name='tasks.ai_tasks.generate_bot_response',
    max_retries=2,
    default_retry_delay=10,
    queue='ai',
)
def generate_bot_response(self, conv_id: str, user_message: str) -> dict:
    """
    Generate an AI bot response using the organization's knowledge base.

    Steps:
      1. Retrieve relevant KB articles (keyword search — replace with vector search)
      2. Build prompt with context
      3. Call OpenAI API (if ENABLE_REAL_AI) or use heuristic response
      4. Save Message, update conversation timestamp
      5. Broadcast via WebSocket to org group
    """
    try:
        from apps.conversations.models import Conversation, Message
        from apps.knowledge_base.models import KBArticle
        from django.conf import settings
        from django.db.models import Q

        conv = Conversation.objects.select_related('organization', 'contact').get(id=conv_id)

        # ── 1. Retrieve KB context ────────────────────────────────────────────
        words = [w for w in user_message.lower().split() if len(w) > 3][:5]
        q_filter = Q()
        for w in words:
            q_filter |= Q(title__icontains=w) | Q(content__icontains=w)

        kb_articles = KBArticle.objects.filter(
            organization=conv.organization,
            status='published',
        ).filter(q_filter)[:3]

        context = '\n'.join([
            f'### {a.title}\n{a.content[:400]}' for a in kb_articles
        ])

        # ── 2. Generate response ──────────────────────────────────────────────
        if settings.ENABLE_REAL_AI and settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

                system_prompt = (
                    'Eres un asistente de atención al cliente de una caja de compensación familiar colombiana. '
                    'Responde de manera amable, clara y profesional. Máximo 3 oraciones. '
                    'Usa el contexto de la base de conocimiento cuando sea relevante.'
                )
                if context:
                    system_prompt += f'\n\nBase de conocimiento:\n{context}'

                completion = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_message},
                    ],
                    max_tokens=300,
                    temperature=0.6,
                )
                response_text = completion.choices[0].message.content or ''

            except Exception as e:
                logger.warning('openai_bot_response_error', error=str(e))
                response_text = _heuristic_response(user_message, context)
        else:
            response_text = _heuristic_response(user_message, context)

        # ── 3. Save bot message ───────────────────────────────────────────────
        bot_msg = Message.objects.create(
            conversation=conv,
            role='bot',
            content=response_text,
            metadata={
                'generated_by': 'ai_engine',
                'kb_articles_used': [str(a.id) for a in kb_articles],
                'model': settings.OPENAI_MODEL if settings.ENABLE_REAL_AI else 'heuristic',
            },
        )

        conv.updated_at = timezone.now()
        conv.save(update_fields=['updated_at'])

        # ── 4. Broadcast via WebSocket ────────────────────────────────────────
        _broadcast_new_message(conv, bot_msg)

        logger.info('bot_response_generated', conv_id=conv_id, msg_id=str(bot_msg.id))
        return {'status': 'ok', 'message_id': str(bot_msg.id), 'conv_id': conv_id}

    except Exception as exc:
        logger.error('bot_response_error', conv_id=conv_id, error=str(exc), exc_info=True)
        raise self.retry(exc=exc)


def _heuristic_response(user_message: str, context: str) -> str:
    """Simple keyword-based fallback when AI is disabled."""
    text_lower = user_message.lower()
    if 'subsidio' in text_lower:
        return (
            'Para tramitar su subsidio familiar necesita: cédula, certificado de ingresos y formulario de afiliación. '
            '¿Desea más información sobre el proceso?'
        )
    if 'certificado' in text_lower or 'afiliacion' in text_lower:
        return (
            'Puede descargar su certificado de afiliación directamente desde nuestra plataforma web '
            'o solicitarlo en cualquier sede. ¿Le ayudo con algo más?'
        )
    if 'pqrs' in text_lower or 'queja' in text_lower:
        return (
            'Entiendo su solicitud. Puede radicar su PQRS a través de nuestra página web, WhatsApp o '
            'en cualquiera de nuestras sedes. ¿Desea que le guíe en el proceso?'
        )
    if context:
        return (
            f'Basado en nuestra base de conocimiento: {context[:300]}... '
            '¿Hay algo más en lo que pueda ayudarle?'
        )
    return 'Gracias por contactarnos. Un asesor revisará su caso y le responderá en breve. ¿Hay algo más en lo que pueda ayudarle?'


def _broadcast_new_message(conv, message):
    """Fire-and-forget WebSocket broadcast — failures are logged, never raised."""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        async_to_sync(channel_layer.group_send)(
            f'org_{conv.organization_id}',
            {
                'type': 'conversation.message',
                'event': 'new_message',
                'conversation_id': str(conv.id),
                'message': {
                    'id': str(message.id),
                    'role': message.role,
                    'content': message.content,
                    'timestamp': message.timestamp.isoformat(),
                },
            }
        )
    except Exception as e:
        logger.warning('ws_broadcast_failed', error=str(e))


@shared_task(
    bind=True,
    name='tasks.ai_tasks.process_kb_document',
    max_retries=3,
    default_retry_delay=60,
    queue='ai',
)
def process_kb_document(self, doc_id: str) -> dict:
    """
    Process a KB document:
      1. Extract text (PDF/txt/docx — simplified here)
      2. Generate embedding vector (OpenAI or heuristic)
      3. Store back on KBDocument

    In production: use LangChain document loaders + OpenAI embeddings.
    """
    try:
        from apps.knowledge_base.models import KBDocument
        from django.conf import settings

        doc = KBDocument.objects.select_related('organization').get(id=doc_id)

        # ── Text extraction (simplified) ─────────────────────────────────────
        # In production: use PyPDF2, python-docx, or LangChain loaders
        text_to_embed = doc.filename  # fallback to filename if no text extraction

        # ── Embedding generation ──────────────────────────────────────────────
        if settings.ENABLE_REAL_AI and settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                response = client.embeddings.create(
                    model=settings.OPENAI_EMBEDDING_MODEL,
                    input=text_to_embed[:8000],  # Token limit
                )
                embedding = response.data[0].embedding
                doc.processed = True
                doc.save(update_fields=['processed'])

                logger.info('kb_doc_embedded_openai', doc_id=doc_id, dim=len(embedding))
                return {'status': 'ok', 'doc_id': doc_id, 'embedding_dim': len(embedding)}

            except Exception as e:
                logger.warning('openai_embedding_error', error=str(e))

        # ── Heuristic embedding (word frequency vector) ────────────────────
        words = text_to_embed.lower().split()
        if words:
            from collections import Counter
            freq = Counter(words)
            total = len(words)
            # Normalized word frequency dict (lightweight, good for keyword search)
            embedding = {w: c / total for w, c in list(freq.items())[:100]}
        else:
            embedding = {}

        doc.processed = True
        doc.save(update_fields=['processed'])

        logger.info('kb_doc_processed_heuristic', doc_id=doc_id, title=doc.filename)
        return {'status': 'ok', 'doc_id': doc_id, 'method': 'heuristic'}

    except Exception as exc:
        logger.error('kb_process_error', doc_id=doc_id, error=str(exc), exc_info=True)
        raise self.retry(exc=exc)
