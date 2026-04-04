"""
AI Engine Celery tasks.

Learning Engine: triggered when a conversation is resolved, escalated, or abandoned.
Extracts learnings via gpt-4o-mini and creates LearningCandidate entries (status='pending')
so a human can review and approve them before they reach KBArticle.
The embedding is pre-generated and stored in candidate metadata so it is
transferred to KBArticle at approval time with no extra API call.
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def _build_conversation_summary(messages: list[dict]) -> str:
    lines = []
    for msg in messages[-20:]:
        role = 'Cliente' if msg.get('role') == 'user' else 'Agente'
        content = str(msg.get('content', '')).strip()[:300]
        if content:
            lines.append(f'{role}: {content}')
    return '\n'.join(lines) or 'Sin mensajes.'


def _extract_learnings_with_llm(conversation_text: str, organization_name: str, organization_id: str = '') -> list[dict]:
    """
    Ask gpt-4o-mini to extract 1-4 learnings from a resolved conversation.
    Returns list of {"title": str, "content": str, "tags": list[str]}.
    """
    import json
    import os
    import time

    from openai import OpenAI

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return []

    prompt = (
        f'Eres un analista de conversaciones para {organization_name}. '
        'Lee la siguiente conversación de soporte/ventas y extrae de 1 a 4 aprendizajes útiles '
        'que deben quedar documentados en la base de conocimiento para que el agente de IA '
        'los use en futuras conversaciones. '
        'Devuelve SOLO un JSON array con objetos que tengan: '
        '"title" (título breve, máx 120 caracteres), '
        '"content" (detalle útil y accionable, máx 400 caracteres), '
        '"tags" (lista de 1-3 palabras clave en minúscula). '
        'Si no hay aprendizajes relevantes devuelve []. '
        'No escribas nada fuera del JSON.\n\n'
        f'--- CONVERSACIÓN ---\n{conversation_text[:2800]}'
    )

    try:
        client = OpenAI(api_key=api_key)
        t0 = time.monotonic()
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            temperature=0.2,
            max_tokens=700,
            response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content': 'Responde solo con JSON válido.'},
                {'role': 'user', 'content': prompt},
            ],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if organization_id:
            from apps.ai_engine.usage_tracker import track
            usage = response.usage
            track(
                organization_id=organization_id,
                feature='learning',
                model='gpt-4o-mini',
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
            )
        raw = response.choices[0].message.content or '{}'
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        for key in ('learnings', 'results', 'items', 'data'):
            if isinstance(parsed.get(key), list):
                return parsed[key]
        return []
    except Exception as exc:
        logger.warning('learning_engine_llm_error', error=str(exc))
        return []


def _generate_embedding(text: str, organization_id: str = '') -> list[float]:
    """Generate OpenAI embedding for immediate cosine search availability."""
    try:
        import os
        import time

        from openai import OpenAI

        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            return []
        client = OpenAI(api_key=api_key)
        t0 = time.monotonic()
        response = client.embeddings.create(model='text-embedding-3-small', input=text[:512])
        latency_ms = int((time.monotonic() - t0) * 1000)
        if organization_id:
            from apps.ai_engine.usage_tracker import track
            usage = response.usage
            track(
                organization_id=organization_id,
                feature='embedding',
                model='text-embedding-3-small',
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=0,
                latency_ms=latency_ms,
            )
        return response.data[0].embedding
    except Exception:
        return []


def _extract_style_patterns_with_llm(user_messages: list[str], organization_name: str, organization_id: str = '') -> list[dict]:
    """
    Analyze how customers write (vocabulary, tone, length, emojis, formality)
    so the AI can mirror their communication style.
    Returns list of {"observation": str, "example": str}.
    """
    import json
    import os

    from openai import OpenAI

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key or not user_messages:
        return []

    sample = '\n'.join(f'- {m[:200]}' for m in user_messages[:30])
    prompt = (
        f'Analiza los siguientes mensajes REALES de clientes de {organization_name}. '
        'Identifica patrones de cómo escriben: vocabulario, formalidad, uso de emojis, '
        'longitud de mensajes, expresiones locales, abreviaciones, puntuación, etc. '
        'El objetivo es que el agente de IA aprenda a responder de forma similar '
        'para sonar más natural y menos robótico. '
        'Devuelve SOLO un JSON array con objetos que tengan: '
        '"observation" (patrón detectado, máx 200 caracteres), '
        '"example" (ejemplo real del texto que lo ilustra, máx 80 caracteres). '
        'Extrae de 1 a 3 observaciones. Si los mensajes son muy pocos o no hay patrones claros devuelve []. '
        'No escribas nada fuera del JSON.\n\n'
        f'--- MENSAJES DE CLIENTES ---\n{sample}'
    )

    try:
        import time
        client = OpenAI(api_key=api_key)
        t0 = time.monotonic()
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            temperature=0.2,
            max_tokens=400,
            response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content': 'Responde solo con JSON válido.'},
                {'role': 'user', 'content': prompt},
            ],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if organization_id:
            from apps.ai_engine.usage_tracker import track
            usage = response.usage
            track(
                organization_id=organization_id,
                feature='style_extraction',
                model='gpt-4o-mini',
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
            )
        raw = response.choices[0].message.content or '{}'
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        for key in ('observations', 'patterns', 'results', 'items', 'data'):
            if isinstance(parsed.get(key), list):
                return parsed[key]
        return []
    except Exception as exc:
        logger.warning('style_extraction_llm_error', error=str(exc))
        return []


def _fingerprint_llm(title: str) -> str:
    """SHA-256 fingerprint for deduplication of LLM-extracted candidates."""
    import hashlib
    import re
    normalized = re.sub(r'\s+', ' ', title.strip().lower())
    return hashlib.sha256(f'llm|{normalized}'.encode()).hexdigest()


def run_learning_engine(conversation_id: str) -> dict:
    """
    Core logic — importable synchronously or called from the Celery task.

    Extracts learnings via gpt-4o-mini and creates LearningCandidate entries
    (status='pending') for human review. Pre-generates embeddings so they are
    transferred to KBArticle at approval time without an extra API call.
    """
    import hashlib

    from apps.analytics.models import LearningCandidate
    from apps.conversations.models import Conversation

    try:
        conversation = (
            Conversation.objects
            .select_related('organization')
            .get(id=conversation_id)
        )
    except Exception as exc:
        logger.warning('learning_engine_conv_not_found', conversation_id=conversation_id, error=str(exc))
        return {'status': 'error', 'reason': 'conversation_not_found'}

    org = conversation.organization
    org_name = getattr(org, 'name', 'la empresa')

    try:
        messages = list(
            conversation.messages.order_by('timestamp').values('role', 'content')
        )
    except Exception:
        messages = []

    if not messages:
        return {'status': 'skipped', 'reason': 'no_messages'}

    org_id_str = str(org.id)
    conversation_text = _build_conversation_summary(messages)
    learnings = _extract_learnings_with_llm(conversation_text, org_name, org_id_str)

    created = 0
    updated = 0
    for item in learnings:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title', '')).strip()[:255]
        content = str(item.get('content', '')).strip()
        tags = item.get('tags', [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).lower()[:50] for t in tags[:3]]

        if not title or not content:
            continue

        fingerprint = _fingerprint_llm(title)
        embedding = _generate_embedding(f'{title}\n{content}', org_id_str)

        candidate, was_created = LearningCandidate.objects.get_or_create(
            organization=org,
            kind='faq',
            fingerprint=fingerprint,
            defaults={
                'conversation': conversation,
                'title': title,
                'source_question': title,
                'proposed_answer': content,
                'confidence': 0.78,
                'evidence_count': 1,
                'status': 'pending',
                'metadata': {
                    'source': 'llm',
                    'tags': tags,
                    'embedding': embedding,
                    'conversation_id': str(conversation_id),
                },
            },
        )
        if not was_created:
            # Refresh content and bump confidence on repeat detection
            candidate.proposed_answer = content
            candidate.evidence_count += 1
            candidate.confidence = min(0.95, round(0.78 + candidate.evidence_count * 0.04, 2))
            meta = {**(candidate.metadata or {})}
            meta['embedding'] = embedding
            meta['tags'] = tags
            candidate.metadata = meta
            candidate.save(update_fields=['proposed_answer', 'evidence_count', 'confidence', 'metadata', 'updated_at'])
            updated += 1
        else:
            created += 1

    # ── Style pattern extraction ──────────────────────────────────────────────
    # Only analyse conversations with enough user messages to detect patterns
    user_texts = [m['content'] for m in messages if m.get('role') == 'user' and m.get('content')]
    style_created = 0
    if len(user_texts) >= 3:
        style_patterns = _extract_style_patterns_with_llm(user_texts, org_name, org_id_str)
        for pattern in style_patterns:
            if not isinstance(pattern, dict):
                continue
            observation = str(pattern.get('observation', '')).strip()[:255]
            example = str(pattern.get('example', '')).strip()[:120]
            if not observation:
                continue
            import hashlib, re as _re
            normalized = _re.sub(r'\s+', ' ', observation.lower())
            fingerprint = hashlib.sha256(f'style|{normalized}'.encode()).hexdigest()
            title = observation[:120]
            _, was_created = LearningCandidate.objects.get_or_create(
                organization=org,
                kind='estilo_comunicacion',
                fingerprint=fingerprint,
                defaults={
                    'conversation': conversation,
                    'title': title,
                    'source_question': observation,
                    'proposed_answer': f'Ejemplo real: "{example}"' if example else observation,
                    'confidence': 0.70,
                    'evidence_count': 1,
                    'status': 'pending',
                    'metadata': {
                        'source': 'style_llm',
                        'conversation_id': str(conversation_id),
                        'example': example,
                    },
                },
            )
            if was_created:
                style_created += 1

    logger.info(
        'learning_engine_done',
        conversation_id=str(conversation_id),
        organization=str(org.id),
        learnings_extracted=len(learnings),
        candidates_created=created,
        candidates_updated=updated,
        style_patterns_created=style_created,
    )
    # Mark conversation as processed so the sweep task skips it
    try:
        from apps.conversations.models import Conversation as Conv
        Conv.objects.filter(id=conversation_id).update(
            metadata=_merge_metadata(conversation_id, {'learning_processed': True})
        )
    except Exception:
        pass

    return {'status': 'ok', 'extracted': len(learnings), 'created': created, 'updated': updated}  # noqa: RET504


def synthesize_playbook_from_kb(org_id: str) -> dict:
    """
    Reads all published KBArticles for an org, grouped by purpose, and asks
    gpt-4o-mini to generate structured sales playbook / brand config updates.
    Writes the result back into ChannelConfig.settings['onboarding'] so the
    Sales Agent picks it up on the next conversation without any manual config.

    Called after: LearningCandidate approval, periodic weekly run.
    """
    import json
    import os

    from openai import OpenAI

    from apps.channels_config.models import ChannelConfig
    from apps.knowledge_base.models import KBArticle

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return {'status': 'error', 'reason': 'no_api_key'}

    try:
        from apps.accounts.models import Organization
        org = Organization.objects.get(id=org_id)
    except Exception as exc:
        logger.warning('synthesize_playbook_org_not_found', org_id=org_id, error=str(exc))
        return {'status': 'error', 'reason': 'org_not_found'}

    articles = list(
        KBArticle.objects.filter(organization=org, is_active=True, status='published')
        .only('title', 'content', 'purpose')
        .order_by('purpose', '-updated_at')[:80]
    )
    if not articles:
        return {'status': 'skipped', 'reason': 'no_articles'}

    # Group by purpose
    grouped: dict[str, list[str]] = {}
    for art in articles:
        p = art.purpose or 'faq'
        if p not in grouped:
            grouped[p] = []
        snippet = f'{art.title}: {" ".join(art.content.split())[:180]}'
        grouped[p].append(snippet)

    # Build prompt sections
    sections: list[str] = []
    purpose_labels = {
        'faq': 'FAQs y Conocimiento General',
        'objection': 'Manejo de Objeciones',
        'closing': 'Técnicas de Cierre',
        'brand_voice': 'Voz y Tono de Marca',
        'policy': 'Políticas del Negocio',
        'product_context': 'Contexto de Productos',
    }
    for purpose, snippets in grouped.items():
        label = purpose_labels.get(purpose, purpose)
        sections.append(f'[{label}]\n' + '\n'.join(f'- {s}' for s in snippets[:10]))

    kb_text = '\n\n'.join(sections)

    prompt = (
        f'Eres un consultor experto en ventas para la empresa "{org.name}". '
        'Analiza los siguientes artículos de knowledge base y genera configuración de ventas estructurada '
        'que el agente de IA usará para vender, responder objeciones y adaptar su tono a la marca.\n\n'
        f'{kb_text[:3500]}\n\n'
        'Devuelve SOLO un JSON con esta estructura exacta (sin texto fuera del JSON):\n'
        '{\n'
        '  "sales_playbook": {\n'
        '    "opening_style": "cómo abrir la conversación (máx 120 chars)",\n'
        '    "recommendation_style": "cómo recomendar productos (máx 120 chars)",\n'
        '    "objection_style": "cómo manejar objeciones (máx 120 chars)",\n'
        '    "closing_style": "cómo cerrar ventas (máx 120 chars)",\n'
        '    "follow_up_style": "cómo hacer seguimiento (máx 120 chars)"\n'
        '  },\n'
        '  "brand_profile": {\n'
        '    "recommended_phrases": ["frase1", "frase2", "frase3"],\n'
        '    "avoid_phrases": ["frase_a_evitar1", "frase_a_evitar2"],\n'
        '    "key_differentiators": ["diferenciador1", "diferenciador2", "diferenciador3"]\n'
        '  },\n'
        '  "buyer_model": {\n'
        '    "common_objections": ["objecion1", "objecion2", "objecion3"],\n'
        '    "purchase_signals": ["señal1", "señal2", "señal3"],\n'
        '    "low_intent_signals": ["señal1", "señal2"]\n'
        '  }\n'
        '}'
    )

    try:
        import time
        client = OpenAI(api_key=api_key)
        t0 = time.monotonic()
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            temperature=0.3,
            max_tokens=900,
            response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content': 'Eres un experto en ventas. Responde solo con JSON válido.'},
                {'role': 'user', 'content': prompt},
            ],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        try:
            from apps.ai_engine.usage_tracker import track
            usage = response.usage
            track(
                organization_id=org_id,
                feature='playbook_synthesis',
                model='gpt-4o-mini',
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
            )
        except Exception:
            pass
        raw = response.choices[0].message.content or '{}'
        synthesis = json.loads(raw)
    except Exception as exc:
        logger.warning('synthesize_playbook_llm_error', org_id=org_id, error=str(exc))
        return {'status': 'error', 'reason': str(exc)}

    # Merge into ChannelConfig.settings (onboarding channel carries agent config)
    try:
        config, _ = ChannelConfig.objects.get_or_create(
            organization=org,
            channel='onboarding',
            defaults={'settings': {}},
        )
        settings = dict(config.settings or {})

        # Deep-merge: only overwrite fields that LLM returned and that are non-empty
        def _merge_dict(existing: dict, incoming: dict) -> dict:
            result = dict(existing)
            for k, v in incoming.items():
                if v or v == 0:  # skip null / empty string / empty list
                    result[k] = v
            return result

        if 'sales_playbook' in synthesis and isinstance(synthesis['sales_playbook'], dict):
            settings['sales_playbook'] = _merge_dict(
                settings.get('sales_playbook') or {}, synthesis['sales_playbook']
            )
        if 'brand_profile' in synthesis and isinstance(synthesis['brand_profile'], dict):
            settings['brand_profile'] = _merge_dict(
                settings.get('brand_profile') or {}, synthesis['brand_profile']
            )
        if 'buyer_model' in synthesis and isinstance(synthesis['buyer_model'], dict):
            settings['buyer_model'] = _merge_dict(
                settings.get('buyer_model') or {}, synthesis['buyer_model']
            )

        sales_agent_profile = dict(settings.get('sales_agent_profile') or {})
        if 'brand_profile' in synthesis and isinstance(synthesis['brand_profile'], dict):
            sales_agent_profile['brand_profile'] = _merge_dict(
                sales_agent_profile.get('brand_profile') or settings.get('brand_profile') or {},
                synthesis['brand_profile'],
            )
        if 'sales_playbook' in synthesis and isinstance(synthesis['sales_playbook'], dict):
            sales_agent_profile['sales_playbook'] = _merge_dict(
                sales_agent_profile.get('sales_playbook') or settings.get('sales_playbook') or {},
                synthesis['sales_playbook'],
            )
        if 'buyer_model' in synthesis and isinstance(synthesis['buyer_model'], dict):
            sales_agent_profile['buyer_model'] = _merge_dict(
                sales_agent_profile.get('buyer_model') or settings.get('buyer_model') or {},
                synthesis['buyer_model'],
            )
        if sales_agent_profile:
            sales_agent_profile['what_you_sell'] = sales_agent_profile.get('what_you_sell') or settings.get('what_you_sell', '')
            sales_agent_profile['who_you_sell_to'] = sales_agent_profile.get('who_you_sell_to') or settings.get('who_you_sell_to', '')
            sales_agent_profile['commerce_rules'] = sales_agent_profile.get('commerce_rules') or settings.get('commerce_rules') or {}
            settings['sales_agent_profile'] = sales_agent_profile

        # Record last synthesis timestamp for observability
        settings['_kb_synthesis_at'] = __import__('datetime').datetime.utcnow().isoformat()
        settings['_kb_synthesis_articles'] = len(articles)

        config.settings = settings
        config.save(update_fields=['settings', 'updated_at'])
        logger.info('synthesize_playbook_done', org_id=org_id, articles=len(articles))
        return {'status': 'ok', 'articles_read': len(articles), 'sections': list(grouped.keys())}
    except Exception as exc:
        logger.warning('synthesize_playbook_save_error', org_id=org_id, error=str(exc))
        return {'status': 'error', 'reason': str(exc)}


def _merge_metadata(conversation_id: str, patch: dict) -> dict:
    """Return merged metadata dict for a conversation (safe read-modify)."""
    from apps.conversations.models import Conversation as Conv
    try:
        meta = Conv.objects.values_list('metadata', flat=True).get(id=conversation_id) or {}
    except Exception:
        meta = {}
    return {**meta, **patch}


def sweep_inactive_conversations() -> dict:
    """
    Scan conversations that have been inactive for >INACTIVITY_HOURS and
    haven't been processed by the learning engine yet.
    Covers: abandoned leads, escalated-but-not-resolved, long-running open chats.
    """
    from django.utils import timezone

    from apps.conversations.models import Conversation

    INACTIVITY_HOURS = 24
    cutoff = timezone.now() - timezone.timedelta(hours=INACTIVITY_HOURS)

    # Any non-resolved conversation with no activity in 24h and not yet learned
    candidates = Conversation.objects.filter(
        last_message_at__lt=cutoff,
    ).exclude(
        estado='resuelto',
    ).exclude(
        metadata__learning_processed=True,
    ).values_list('id', flat=True)[:200]

    queued = 0
    for conv_id in candidates:
        try:
            extract_conversation_learnings.delay(str(conv_id))
            queued += 1
        except Exception:
            pass

    logger.info('learning_sweep_done', queued=queued)
    return {'status': 'ok', 'queued': queued}


# ── Celery tasks ─────────────────────────────────────────────────────────────

try:
    from tasks.celery_app import app as celery_app

    @celery_app.task(
        name='ai_engine.tasks.extract_conversation_learnings',
        bind=True,
        max_retries=2,
        default_retry_delay=60,
        ignore_result=False,
        queue='ai',
    )
    def extract_conversation_learnings(self, conversation_id: str) -> dict:
        """
        Celery task — triggered on resolve, escalation, or inactivity sweep.
        Extracts learnings and writes them to KBArticle (category='ai_aprendido').
        """
        try:
            return run_learning_engine(conversation_id)
        except Exception as exc:
            logger.error('learning_engine_task_error', conversation_id=conversation_id, error=str(exc))
            raise self.retry(exc=exc)

    @celery_app.task(
        name='ai_engine.tasks.sweep_inactive_conversations',
        ignore_result=True,
        queue='ai',
    )
    def sweep_inactive_conversations_task() -> dict:
        """Periodic task — sweep inactive conversations for learning extraction."""
        return sweep_inactive_conversations()

    @celery_app.task(
        name='ai_engine.tasks.synthesize_playbook_from_kb',
        bind=False,
        ignore_result=False,
        queue='ai',
    )
    def synthesize_playbook_task(org_id: str) -> dict:
        """Celery task — synthesize sales playbook from KB articles for one org."""
        return synthesize_playbook_from_kb(org_id)

    @celery_app.task(
        name='ai_engine.tasks.synthesize_all_orgs_playbooks',
        ignore_result=True,
        queue='ai',
    )
    def synthesize_all_orgs_playbooks_task() -> dict:
        """Weekly periodic task — re-synthesizes playbooks for all active orgs."""
        from apps.accounts.models import Organization
        queued = 0
        for org in Organization.objects.filter(is_active=True).values_list('id', flat=True):
            try:
                synthesize_playbook_task.delay(str(org))
                queued += 1
            except Exception:
                pass
        logger.info('synthesize_all_orgs_done', queued=queued)
        return {'status': 'ok', 'queued': queued}

    @celery_app.task(
        name='ai_engine.tasks.backfill_kb_embeddings',
        ignore_result=False,
        queue='ai',
    )
    def backfill_kb_embeddings_task(org_id: str | None = None) -> dict:
        """
        Generate missing embedding_vector for all published KBArticles.
        Can be scoped to a single org by passing org_id.
        """
        import os
        import time

        from openai import OpenAI

        from apps.knowledge_base.models import KBArticle

        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            return {'status': 'error', 'reason': 'no_api_key'}

        qs = KBArticle.objects.filter(is_active=True, status='published', embedding_vector=[])
        if org_id:
            qs = qs.filter(organization__id=org_id)

        articles = list(qs[:200])
        if not articles:
            return {'status': 'ok', 'embedded': 0}

        client = OpenAI(api_key=api_key)
        done = 0
        batch_size = 50

        for i in range(0, len(articles), batch_size):
            batch = articles[i: i + batch_size]
            texts = [f"{a.title}\n{a.content}"[:512] for a in batch]
            try:
                response = client.embeddings.create(model='text-embedding-3-small', input=texts)
                for article, emb_data in zip(batch, response.data):
                    article.embedding_vector = emb_data.embedding
                KBArticle.objects.bulk_update(batch, ['embedding_vector'])
                done += len(batch)
                time.sleep(0.3)
            except Exception as exc:
                logger.warning('backfill_kb_batch_error', error=str(exc))

        logger.info('backfill_kb_embeddings_done', embedded=done)
        return {'status': 'ok', 'embedded': done}

except ImportError:
    def extract_conversation_learnings(conversation_id: str) -> dict:  # type: ignore[misc]
        return run_learning_engine(conversation_id)

    def sweep_inactive_conversations_task() -> dict:  # type: ignore[misc]
        return sweep_inactive_conversations()

    def synthesize_playbook_task(org_id: str) -> dict:  # type: ignore[misc]
        return synthesize_playbook_from_kb(org_id)

    def synthesize_all_orgs_playbooks_task() -> dict:  # type: ignore[misc]
        return {'status': 'skipped', 'reason': 'celery_not_available'}

    def backfill_kb_embeddings_task(org_id: str | None = None) -> dict:  # type: ignore[misc]
        return {'status': 'skipped', 'reason': 'celery_not_available'}
