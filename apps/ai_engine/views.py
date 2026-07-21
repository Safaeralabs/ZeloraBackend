"""
AI Engine views — AI Workspace backend.
Powers: Memory, Tasks, Insights, Performance, Copilot, Summarize, Intent Detection.
"""
import structlog
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from django.utils import timezone
from django.db.models import Avg, Count
from core.permissions import IsOrganizationMember, IsOrganizationAdmin
from core.mixins import OrgScopedMixin

from .models import AITask, AIInsight, AIPerformanceLog, SalesSession
from .serializers import (
    AITaskSerializer,
    AIInsightSerializer,
    AIPerformanceLogSerializer,
)

logger = structlog.get_logger(__name__)

# ─── Mock response bank (replace with real LLM calls via ENABLE_REAL_AI flag) ──
_MOCK_SUGGESTIONS = {
    'Subsidio familiar': [
        'Para tramitar su subsidio familiar necesita: cédula, certificado de ingresos y formulario de afiliación.',
        'El subsidio familiar se paga los primeros 5 días hábiles de cada mes a los trabajadores activos.',
    ],
    'Certificado de afiliación': [
        'Puede descargar su certificado de afiliación en la página web o solicitarlo en cualquier sede.',
        'El certificado de afiliación está disponible de forma inmediata en nuestra plataforma digital.',
    ],
    'PQRS': [
        'Para radicar una PQRS puede hacerlo en nuestra página web, WhatsApp o en cualquiera de nuestras sedes.',
        'Su PQRS será atendida en un plazo máximo de 15 días hábiles según la ley.',
    ],
    'Actualización de datos': [
        'Para actualizar sus datos debe presentar cédula de ciudadanía vigente y los documentos que soporten el cambio.',
    ],
    'Consulta pensión': [
        'Para consultar el estado de su pensión puede llamar a nuestra línea de atención o ingresar a la plataforma web.',
    ],
    'default': [
        'Entiendo su consulta. Le ayudaré con gusto. ¿Podría darme más detalles?',
        'Estoy revisando su caso. Un momento por favor.',
    ],
}

_INTENT_MAP = {
    'subsidio': 'Subsidio familiar',
    'certificado': 'Certificado de afiliación',
    'afiliacion': 'Certificado de afiliación',
    'afiliación': 'Certificado de afiliación',
    'pqrs': 'PQRS',
    'queja': 'PQRS',
    'reclamo': 'PQRS',
    'peticion': 'PQRS',
    'actualiz': 'Actualización de datos',
    'datos': 'Actualización de datos',
    'pension': 'Consulta pensión',
    'pensión': 'Consulta pensión',
}


def _detect_intent(text: str) -> tuple[str, float]:
    """Keyword-based intent detection. Replace with LLM classifier in production."""
    text_lower = text.lower()
    for keyword, intent in _INTENT_MAP.items():
        if keyword in text_lower:
            return intent, 0.85
    return 'Consulta general', 0.60


# ─── AI Copilot ────────────────────────────────────────────────────────────────

class CopilotView(APIView):
    """
    POST /api/ai/copilot/
    Provides AI-generated response suggestions for an agent handling a conversation.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        intent = request.data.get('intent', 'default')
        conversation_id = request.data.get('conversation_id')
        context_messages = request.data.get('messages', [])

        if settings.ENABLE_REAL_AI and settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

                messages = [
                    {
                        'role': 'system',
                        'content': (
                            'Eres un asistente de atención al cliente experto en servicios de caja de compensación '
                            'familiar en Colombia. Genera 2 respuestas cortas, amables y profesionales para el agente.'
                            ' Responde en español. Sé conciso (máximo 2 oraciones por sugerencia).'
                        ),
                    },
                    {
                        'role': 'user',
                        'content': f'Genera 2 respuestas para la intención: {intent}',
                    },
                ]

                completion = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=messages,
                    max_tokens=400,
                    temperature=0.7,
                )
                raw = completion.choices[0].message.content or ''
                # Split by newline to get individual suggestions
                suggestions = [s.strip() for s in raw.split('\n') if s.strip()][:3]

            except Exception as e:
                logger.warning('openai_copilot_error', error=str(e))
                suggestions = _MOCK_SUGGESTIONS.get(intent, _MOCK_SUGGESTIONS['default'])
        else:
            suggestions = _MOCK_SUGGESTIONS.get(intent, _MOCK_SUGGESTIONS['default'])

        logger.info('copilot_request', intent=intent, conversation_id=conversation_id)
        return Response({
            'suggestions': suggestions,
            'intent': intent,
            'conversation_id': conversation_id,
        })


# ─── Tone Preview (onboarding) ──────────────────────────────────────────────────

_TONE_FALLBACKS = {
    'formal': 'Buenas tardes, un gusto saludarle. Contamos con {product}, pensado especialmente para {audience}. ¿En qué puedo ayudarle hoy?',
    'casual': '¡Ey, qué tal! 👋 Tenemos {product}, ideal si eres de {audience}. ¿Qué te muestro primero?',
    'balanced': '¡Hola! Soy tu asistente virtual. Tenemos {product} pensado para {audience}. Cuéntame qué buscas y te ayudo.',
}

_TONE_LABELS = {
    'formal': 'formal y respetuoso, tratando de "usted"',
    'balanced': 'cercano pero profesional, tuteando con calidez',
    'casual': 'informal, juvenil y con emojis moderados',
}


class TonePreviewView(APIView):
    """
    POST /api/ai/tone-preview/
    Generates a one-off example sentence showing how the Sales Agent would
    greet a customer at a given formality level, for the onboarding tone picker.
    Falls back to a canned example when AI is disabled or the call fails —
    the onboarding flow must never block on this.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        formality = request.data.get('formality')
        if formality not in _TONE_FALLBACKS:
            formality = 'balanced'
        sell = str(request.data.get('what_you_sell') or '').strip()[:200] or 'lo que vendes'
        audience = str(request.data.get('who_you_sell_to') or '').strip()[:200] or 'tus clientes'

        fallback = _TONE_FALLBACKS[formality].format(product=sell, audience=audience)

        if not (settings.ENABLE_REAL_AI and settings.OPENAI_API_KEY):
            return Response({'example': fallback, 'source': 'fallback'})

        try:
            import openai
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            completion = client.chat.completions.create(
                model=settings.OPENAI_SITUATION_MODEL or 'gpt-4.1-nano',
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            'Escribes UNA sola oracion de ejemplo (maximo 220 caracteres) que muestra como '
                            'saludaria un vendedor de WhatsApp/chat a un cliente nuevo, en un tono '
                            f'{_TONE_LABELS[formality]}. Responde solo con la oracion, sin comillas ni explicaciones.'
                        ),
                    },
                    {
                        'role': 'user',
                        'content': f'Vende: {sell}\nA quien le vende: {audience}',
                    },
                ],
                max_tokens=120,
                temperature=0.9,
            )
            text = (completion.choices[0].message.content or '').strip().strip('"')
            if not text:
                return Response({'example': fallback, 'source': 'fallback'})
            return Response({'example': text[:280], 'source': 'ai'})
        except Exception as exc:
            logger.warning('tone_preview_error', error=str(exc))
            return Response({'example': fallback, 'source': 'fallback'})


# ─── Conversation Summarize ────────────────────────────────────────────────────

class SummarizeView(APIView):
    """
    POST /api/ai/summarize/
    Returns a text summary of a conversation.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        conversation_id = request.data.get('conversation_id')
        if not conversation_id:
            return Response({'error': 'conversation_id required'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.conversations.models import Conversation
        try:
            conv = Conversation.objects.prefetch_related('messages').get(
                id=conversation_id, organization=request.user.organization
            )
        except Conversation.DoesNotExist:
            return Response({'error': 'Conversation not found'}, status=status.HTTP_404_NOT_FOUND)

        messages = list(conv.messages.order_by('timestamp'))
        msg_count = len(messages)

        if settings.ENABLE_REAL_AI and settings.OPENAI_API_KEY and msg_count > 0:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                transcript = '\n'.join(
                    [f'[{m.role.upper()}] {m.content[:500]}' for m in messages[-20:]]
                )
                completion = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {
                            'role': 'system',
                            'content': 'Resume la siguiente conversación de atención al cliente en 3 frases máximo. Español.',
                        },
                        {'role': 'user', 'content': transcript},
                    ],
                    max_tokens=200,
                )
                summary = completion.choices[0].message.content or ''
            except Exception as e:
                logger.warning('openai_summarize_error', error=str(e))
                summary = self._heuristic_summary(conv, msg_count)
        else:
            summary = self._heuristic_summary(conv, msg_count)

        return Response({'summary': summary, 'message_count': msg_count})

    @staticmethod
    def _heuristic_summary(conv, msg_count: int) -> str:
        return (
            f'Conversación sobre "{conv.intent or "consulta general"}". '
            f'{msg_count} mensajes. Estado actual: {conv.estado}. '
            f'Canal: {conv.canal}. Sentimiento: {conv.sentimiento}.'
        )


# ─── Intent Detection ──────────────────────────────────────────────────────────

class IntentDetectView(APIView):
    """
    POST /api/ai/intent/
    Detect intent from a message text.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        text = request.data.get('text', '')
        if not text:
            return Response({'error': 'text required'}, status=status.HTTP_400_BAD_REQUEST)

        intent, confidence = _detect_intent(text)
        return Response({'intent': intent, 'confidence': confidence, 'text': text[:100]})


# ─── QA Score Trigger ──────────────────────────────────────────────────────────

class QAScoreView(APIView):
    """
    POST /api/ai/qa-score/
    Queue an async QA scoring task for a conversation.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        conversation_id = request.data.get('conversation_id')
        if not conversation_id:
            return Response({'error': 'conversation_id required'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify conversation belongs to this org
        from apps.conversations.models import Conversation
        if not Conversation.objects.filter(
            id=conversation_id, organization=request.user.organization
        ).exists():
            return Response({'error': 'Conversation not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            from tasks.ai_tasks import score_conversation_qa
            result = score_conversation_qa.delay(str(conversation_id))
            return Response({'status': 'queued', 'task_id': result.id})
        except Exception as e:
            logger.warning('qa_score_queue_error', error=str(e))
            return Response({'status': 'queued', 'note': 'Task queued (Celery may be starting)'})


# ─── AI Tasks ViewSet ──────────────────────────────────────────────────────────

class AITaskViewSet(OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only list/retrieve of AI background tasks."""
    permission_classes = [IsOrganizationMember]
    serializer_class = AITaskSerializer
    filterset_fields = ['status', 'task_type', 'priority']

    def get_queryset(self):
        return AITask.objects.filter(organization=self.request.user.organization)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        task = self.get_object()
        if task.status not in ('pending', 'running'):
            return Response({'error': f'Cannot cancel task in status {task.status}'}, status=400)

        if task.celery_task_id:
            try:
                from tasks.celery_app import app
                app.control.revoke(task.celery_task_id, terminate=True)
            except Exception:
                pass

        task.status = 'cancelled'
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'completed_at'])
        return Response({'status': 'cancelled'})


# ─── AI Insights ViewSet ───────────────────────────────────────────────────────

class AIInsightViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    """AI-generated insights for the organization."""
    permission_classes = [IsOrganizationMember]
    serializer_class = AIInsightSerializer
    filterset_fields = ['category', 'severity', 'is_read']

    def get_queryset(self):
        return AIInsight.objects.filter(organization=self.request.user.organization)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        insight = self.get_object()
        insight.is_read = True
        insight.save(update_fields=['is_read'])
        return Response({'status': 'marked_read'})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        count = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'marked_read': count})


# ─── AI Performance ViewSet ────────────────────────────────────────────────────

class AIPerformanceViewSet(OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read AI model performance logs."""
    permission_classes = [IsOrganizationMember]
    serializer_class = AIPerformanceLogSerializer
    filterset_fields = ['model_name']

    def get_queryset(self):
        return AIPerformanceLog.objects.filter(organization=self.request.user.organization)


class SalesSessionMetricsView(APIView):
    """Aggregate sales session funnel and activity metrics for the current organization."""
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        qs = SalesSession.objects.filter(organization=request.user.organization)
        total_sessions = qs.count()

        stage_counts = {stage: 0 for stage, _label in SalesSession.STAGE_CHOICES}
        for row in qs.values('stage').annotate(count=Count('id')):
            stage_counts[row['stage']] = row['count']

        top_situations = [
            {
                'situation': row['situation'],
                'count': row['count'],
            }
            for row in qs.values('situation').annotate(count=Count('id')).order_by('-count', 'situation')[:5]
        ]

        checkout_sessions = qs.filter(checkout_step__gte=1).count()
        active_sessions = total_sessions - stage_counts.get('closed', 0)
        avg_messages = qs.aggregate(avg=Avg('message_count'))['avg'] or 0

        contract_metric_totals: dict[str, int] = {}
        sessions_with_contract_metrics = 0
        for checkout_data in qs.values_list('checkout_data', flat=True):
            if not isinstance(checkout_data, dict):
                continue
            metrics = checkout_data.get('contract_metrics')
            if not isinstance(metrics, dict) or not metrics:
                continue
            sessions_with_contract_metrics += 1
            for key, value in metrics.items():
                metric_key = str(key or '').strip()
                if not metric_key:
                    continue
                try:
                    amount = int(value or 0)
                except (TypeError, ValueError):
                    amount = 0
                contract_metric_totals[metric_key] = int(contract_metric_totals.get(metric_key, 0)) + amount

        return Response({
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'avg_messages_per_session': round(float(avg_messages), 1) if total_sessions else 0,
            'checkout_sessions': checkout_sessions,
            'checkout_rate_pct': round((checkout_sessions / total_sessions) * 100, 1) if total_sessions else 0,
            'stage_counts': stage_counts,
            'top_situations': top_situations,
            'opportunities': stage_counts.get('considering', 0) + stage_counts.get('checkout', 0),
            'handoff_sessions': stage_counts.get('handoff', 0),
            'closed_sessions': stage_counts.get('closed', 0),
            'sessions_with_contract_metrics': sessions_with_contract_metrics,
            'contract_metrics': contract_metric_totals,
        })


# ─── Voice import (self-serve: onboarding + knowledge base) ────────────────────

class VoiceImportPreviewView(APIView):
    """
    POST /api/ai/voice-import/preview/  (multipart/form-data)

    Fields: `files` (repeatable: .txt / .html / .zip), `pasted_text`,
    optional `brand_name` (which participant is the brand).

    Parses WhatsApp/Instagram/pasted chats IN MEMORY, compiles the brand's
    measurable voice fingerprint and returns it for the user to confirm.
    Nothing is persisted here: raw chats are discarded when the request ends.
    """
    permission_classes = [IsOrganizationMember]

    MAX_FILES = 30
    MAX_FILE_BYTES = 3 * 1024 * 1024      # per file / per zip member
    MAX_TOTAL_BYTES = 20 * 1024 * 1024    # whole request, uncompressed
    MAX_ZIP_MEMBERS = 200
    MAX_PASTED_CHARS = 400_000

    def post(self, request):
        from apps.ai_engine.sales.voice_import import (
            compile_voice_card,
            parse_chat_payload,
            select_example_exchanges,
        )

        uploads = request.FILES.getlist('files')
        pasted_text = str(request.data.get('pasted_text') or '')[:self.MAX_PASTED_CHARS]
        brand_name = str(request.data.get('brand_name') or '').strip() or None
        # Structured interviews (onboarding) are reliable evidence from fewer
        # messages than organic chats; clamped so nobody compiles from noise.
        try:
            min_messages = max(6, min(10, int(request.data.get('min_messages') or 10)))
        except (TypeError, ValueError):
            min_messages = 10

        if not uploads and not pasted_text.strip():
            return Response(
                {'error': 'Sube al menos un archivo o pega una conversación.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(uploads) > self.MAX_FILES:
            return Response(
                {'error': f'Máximo {self.MAX_FILES} archivos por importación.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            files = self._collect_text_files(uploads)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = parse_chat_payload(files, pasted_text=pasted_text, brand_name=brand_name)
        conversations = payload['conversations']
        if not conversations:
            return Response(
                {
                    'error': 'No pudimos leer conversaciones en lo que subiste. '
                             'Formatos soportados: export de WhatsApp (.txt), export de '
                             'Instagram/Messenger (.html o .zip) o texto pegado "Nombre: mensaje".',
                    'skipped': payload['skipped'],
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        compiled = compile_voice_card(conversations, min_messages=min_messages)
        exchanges = select_example_exchanges(conversations)
        logger.info(
            'voice_import_preview',
            organization_id=str(request.user.organization_id),
            conversations=len(conversations),
            brand_messages=compiled['stats'].get('brand_messages', 0),
            sources=payload['sources'],
        )
        return Response({
            'voice_card': compiled['voice_card'],
            'voice_examples': compiled['voice_examples'],
            'exchanges': exchanges,
            'stats': {**compiled['stats'], 'conversations': len(conversations)},
            'brand': payload['brand'],
            'participants': payload['participants'],
            'sources': payload['sources'],
            'skipped': payload['skipped'],
        })

    def _collect_text_files(self, uploads) -> list[tuple[str, str]]:
        """Expand uploads (including zips) into (name, text) pairs, in memory,
        with hard size caps so a hostile zip can't blow up the worker."""
        import io
        import zipfile

        files: list[tuple[str, str]] = []
        total = 0
        for upload in uploads:
            data = upload.read()
            total += len(data)
            if len(data) > self.MAX_FILE_BYTES and not upload.name.lower().endswith('.zip'):
                raise ValueError(f'"{upload.name}" supera el límite de 3 MB por archivo.')
            if total > self.MAX_TOTAL_BYTES:
                raise ValueError('La importación supera el límite total de 20 MB.')
            name = upload.name or 'archivo'
            if name.lower().endswith('.zip'):
                try:
                    archive = zipfile.ZipFile(io.BytesIO(data))
                except zipfile.BadZipFile:
                    raise ValueError(f'"{name}" no es un zip válido.')
                members = 0
                for info in archive.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(('.txt', '.html', '.htm')):
                        continue
                    if info.file_size > self.MAX_FILE_BYTES:
                        continue
                    total += info.file_size
                    if total > self.MAX_TOTAL_BYTES:
                        raise ValueError('La importación supera el límite total de 20 MB.')
                    members += 1
                    if members > self.MAX_ZIP_MEMBERS:
                        break
                    files.append((info.filename, archive.read(info).decode('utf-8', errors='replace')))
            else:
                files.append((name, data.decode('utf-8', errors='replace')))
        return files


class VoiceImportApplyView(APIView):
    """
    POST /api/ai/voice-import/apply/  (JSON)

    Body: the `voice_card`, `voice_examples` and `exchanges` returned by
    preview (the user confirmed them). Everything is re-sanitized server-side
    (key whitelist, PII re-check, caps) so a tampered payload can't smuggle
    junk into the system prompt. A voice_card the user marked as manual is
    never overwritten.
    """
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        from apps.ai_engine.sales.voice_import import (
            _contains_pii,
            apply_voice_to_settings,
            seed_example_candidates,
        )
        from apps.channels_config.settings_schema import _VOICE_CARD_DEFAULTS

        organization = request.user.organization

        card_in = request.data.get('voice_card')
        if not isinstance(card_in, dict) or not card_in:
            return Response(
                {'error': 'voice_card inválida o vacía. Corre primero el preview.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Whitelist: only known voice_card fields survive; normalise_settings
        # clamps values again on every read.
        voice_card = {
            key: card_in[key]
            for key in _VOICE_CARD_DEFAULTS
            if key in card_in and key != 'source'
        }

        examples_in = request.data.get('voice_examples') or []
        voice_examples = []
        if isinstance(examples_in, list):
            for item in examples_in[:24]:
                text = str(item).strip()[:280]
                if text and not _contains_pii(text):
                    voice_examples.append(text)
        voice_examples = voice_examples[:12]

        exchanges_in = request.data.get('exchanges') or []
        exchanges = [item for item in exchanges_in if isinstance(item, dict)][:20] \
            if isinstance(exchanges_in, list) else []

        applied = apply_voice_to_settings(
            organization, voice_card, voice_examples, source='imported',
        )
        seeded = seed_example_candidates(organization, exchanges) if exchanges else 0

        logger.info(
            'voice_import_applied',
            organization_id=str(organization.id),
            applied=applied,
            examples=len(voice_examples),
            exchanges_seeded=seeded,
        )
        return Response({
            'applied': applied,
            'manual_locked': not applied,
            'voice_examples_saved': len(voice_examples) if applied else 0,
            'exchanges_seeded': seeded,
        })


