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


def _message_role_label(role: str) -> str:
    if role == 'user':
        return 'Cliente'
    if role == 'bot':
        return 'IA'
    if role == 'agent':
        return 'Operador humano'
    return 'Sistema'


def _build_conversation_summary(messages: list[dict]) -> str:
    lines = []
    for msg in messages[-20:]:
        role = _message_role_label(str(msg.get('role', '')))
        content = str(msg.get('content', '')).strip()[:300]
        if content:
            lines.append(f'{role}: {content}')
    return '\n'.join(lines) or 'Sin mensajes.'


def _learning_source_metadata(messages: list[dict]) -> dict:
    counts = {
        'user': sum(1 for msg in messages if msg.get('role') == 'user' and str(msg.get('content', '')).strip()),
        'bot': sum(1 for msg in messages if msg.get('role') == 'bot' and str(msg.get('content', '')).strip()),
        'agent': sum(1 for msg in messages if msg.get('role') == 'agent' and str(msg.get('content', '')).strip()),
    }
    if counts['agent'] > 0:
        primary = 'agent'
    elif counts['bot'] > 0:
        primary = 'bot'
    elif counts['user'] > 0:
        primary = 'user'
    else:
        primary = 'system'
    return {
        'source_role': primary,
        'source_label': _message_role_label(primary),
        'source_roles_present': [role for role, count in counts.items() if count > 0],
        'source_counts': counts,
    }


def _conversation_learning_metadata(conversation, messages: list[dict]) -> dict:
    metadata = getattr(conversation, 'metadata', {}) or {}
    operator_state = metadata.get('operator_state') or {}
    owner = operator_state.get('owner') or 'ia'
    has_human_messages = any(msg.get('role') == 'agent' and str(msg.get('content', '')).strip() for msg in messages)
    has_ai_messages = any(msg.get('role') == 'bot' and str(msg.get('content', '')).strip() for msg in messages)

    if owner == 'humano' or has_human_messages:
        resolution_source = 'humano'
        resolution_label = 'Resuelta por humano'
    elif has_ai_messages:
        resolution_source = 'ia'
        resolution_label = 'Resuelta por IA'
    else:
        resolution_source = 'mixta'
        resolution_label = 'Resolucion mixta'

    return {
        'resolution_owner': owner,
        'resolution_source': resolution_source,
        'resolution_label': resolution_label,
        'assigned_agent_id': str(getattr(conversation, 'assigned_agent_id', '') or ''),
        'has_human_messages': has_human_messages,
        'has_ai_messages': has_ai_messages,
    }


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


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _should_learn_from(conversation, messages: list[dict]) -> tuple[bool, str | None]:
    """
    L1 — Pre-filter: decide if this conversation is worth learning from.
    Returns (should_learn, skip_reason).
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.conversations.models import QAScore

    # Rule 1: Minimum message count
    if len(messages) < 4:
        return False, 'too_few_messages'

    # Rule 2: Resolution must have human or mixed involvement, not pure IA
    source_meta = _learning_source_metadata(messages)
    if source_meta['source_role'] == 'user':
        # Only user spoke, no response
        return False, 'no_resolution_messages'

    conversation_meta = _conversation_learning_metadata(conversation, messages)
    if conversation_meta['resolution_source'] == 'ia':
        # Pure IA → lower priority, skip for now
        return False, 'pure_ai_resolution'

    # Rule 3: QA Score >= 65 if exists
    try:
        qa_score = QAScore.objects.get(conversation=conversation)
        if qa_score.score < 65:
            return False, 'low_qa_score'
    except QAScore.DoesNotExist:
        pass  # OK, QA score might not exist yet

    # Rule 4: Conversation is recent (not older than 30 days)
    if conversation.last_message_at:
        age_hours = (timezone.now() - conversation.last_message_at).total_seconds() / 3600
        if age_hours > 720:  # 30 days
            return False, 'conversation_too_old'

    # Rule 5: Simple prompt injection detector — check for obvious attack patterns
    suspicious_patterns = [
        'ignore', 'forget', 'override', 'instructions', 'system prompt',
        'debug', 'test', 'eval', 'exec', '__',
    ]
    all_text = ' '.join(m.get('content', '') for m in messages).lower()
    if any(pattern in all_text for pattern in suspicious_patterns):
        # Could be prompt injection; flag it
        logger.warning('suspected_prompt_injection', conversation_id=str(conversation.id))
        return False, 'suspected_prompt_injection'

    return True, None


def _dedupe_semantic(
    candidate_dict: dict, org_id: str, existing_candidates: list
) -> tuple[bool, str | None]:
    """
    L2 — Semantic deduplication.
    Given a new candidate (with embedding), check if it's too similar to existing ones.
    Returns (should_create, candidate_to_update_id).
    """
    new_embedding = candidate_dict.get('embedding')
    if not new_embedding:
        # No embedding, fall back to fingerprint-only dedupe (already done by get_or_create)
        return True, None

    new_title = candidate_dict.get('title', '')

    for existing in existing_candidates:
        existing_embedding = existing.get('metadata', {}).get('embedding')
        if not existing_embedding:
            continue

        similarity = _cosine_similarity(new_embedding, existing_embedding)
        if similarity > 0.88:
            # Too similar — update existing instead of creating new
            logger.info(
                'dedupe_semantic_hit',
                org_id=org_id,
                new_title=new_title,
                existing_title=existing.get('title'),
                similarity=similarity,
            )
            return False, existing.get('id')

    return True, None


def run_learning_engine(conversation_id: str) -> dict:
    """
    Core logic — importable synchronously or called from the Celery task.

    Extracts learnings via gpt-4o-mini and creates LearningCandidate entries
    (status='pending') for human review. Pre-generates embeddings so they are
    transferred to KBArticle at approval time without an extra API call.

    L1 — Pre-filters low-quality conversations before extraction.
    L2 — Deduplicates semantically similar candidates.
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

    # ── L1: Pre-filter low-quality conversations ────────────────────────────────
    should_learn, skip_reason = _should_learn_from(conversation, messages)
    if not should_learn:
        # Mark conversation with skip reason for audit
        try:
            meta = {**(conversation.metadata or {})}
            meta['learning_skipped_reason'] = skip_reason
            Conversation.objects.filter(id=conversation_id).update(metadata=meta)
        except Exception:
            pass
        logger.info('learning_engine_skipped', conversation_id=str(conversation_id), reason=skip_reason)
        return {'status': 'skipped', 'reason': skip_reason}

    org_id_str = str(org.id)
    conversation_text = _build_conversation_summary(messages)
    source_meta = _learning_source_metadata(messages)
    conversation_meta = _conversation_learning_metadata(conversation, messages)
    learnings = _extract_learnings_with_llm(conversation_text, org_name, org_id_str)

    created = 0
    updated = 0
    deduped = 0

    # ── L2: Pre-load existing candidates for semantic deduplication ──────────────
    existing_candidates_qs = LearningCandidate.objects.filter(
        organization=org, kind='faq', status__in=['pending', 'approved']
    ).values('id', 'title', 'metadata')
    existing_candidates = list(existing_candidates_qs)

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

        base_confidence = 0.84 if conversation_meta['resolution_source'] == 'humano' else 0.78

        # ── L2: Check for semantic duplicates ──────────────────────────────────
        candidate_dict = {
            'title': title,
            'embedding': embedding,
        }
        should_create, existing_id_to_update = _dedupe_semantic(
            candidate_dict, org_id_str, existing_candidates
        )

        if not should_create and existing_id_to_update:
            # Found a semantic duplicate; update the existing candidate
            try:
                candidate = LearningCandidate.objects.get(id=existing_id_to_update)
                # Bump confidence and evidence count
                candidate.evidence_count += 1
                candidate.confidence = min(0.97, round(base_confidence + candidate.evidence_count * 0.04, 2))
                meta = {**(candidate.metadata or {})}
                meta['embedding'] = embedding  # Use newer embedding
                meta['tags'] = tags
                meta.update(source_meta)
                meta.update(conversation_meta)
                candidate.metadata = meta
                candidate.save(update_fields=['evidence_count', 'confidence', 'metadata', 'updated_at'])
                deduped += 1
            except LearningCandidate.DoesNotExist:
                pass
            continue

        # Normal get_or_create path (fingerprint-based)
        candidate, was_created = LearningCandidate.objects.get_or_create(
            organization=org,
            kind='faq',
            fingerprint=fingerprint,
            defaults={
                'conversation': conversation,
                'title': title,
                'source_question': title,
                'proposed_answer': content,
                'confidence': base_confidence,
                'evidence_count': 1,
                'status': 'pending',
                'metadata': {
                    'source': 'llm',
                    'tags': tags,
                    'embedding': embedding,
                    'conversation_id': str(conversation_id),
                    **source_meta,
                    **conversation_meta,
                },
            },
        )
        if not was_created:
            # Refresh content and bump confidence on repeat detection
            candidate.proposed_answer = content
            candidate.evidence_count += 1
            candidate.confidence = min(0.97, round(base_confidence + candidate.evidence_count * 0.04, 2))
            meta = {**(candidate.metadata or {})}
            meta['embedding'] = embedding
            meta['tags'] = tags
            meta.update(source_meta)
            meta.update(conversation_meta)
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
                        **source_meta,
                        **conversation_meta,
                    },
                },
            )
            if was_created:
                style_created += 1

    # ── L3+L4: Conversation examples extraction (human-resolved only) ─────────────
    # Extract high-quality user → agent reply pairs for few-shot learning
    # L5: Boost confidence if conversation resulted in purchase
    examples_created = 0
    commercial_outcome = getattr(conversation, 'commercial_outcome', None) or 'browsing'
    base_example_confidence = {
        'purchased': 0.92,    # L5: highest confidence for purchases
        'abandoned': 0.70,    # Lower for abandoned conversations
        'browsing': 0.82,     # Medium for browsing
    }.get(commercial_outcome, 0.82)

    if conversation_meta['resolution_source'] == 'humano':
        # Only extract examples if human was involved in resolution
        agent_messages = [m for m in messages if m.get('role') == 'agent' and m.get('content')]
        if len(agent_messages) >= 1:
            # Group messages into user-agent pairs
            for i, msg in enumerate(messages):
                if msg.get('role') == 'agent' and msg.get('content'):
                    # Find preceding user message
                    user_msg = None
                    for j in range(i - 1, -1, -1):
                        if messages[j].get('role') == 'user' and messages[j].get('content'):
                            user_msg = messages[j].get('content', '')
                            break

                    if not user_msg:
                        continue

                    agent_reply = str(msg.get('content', '')).strip()
                    if len(agent_reply) < 20 or len(user_msg) < 10:
                        # Skip too short examples
                        continue

                    # Create fingerprint from agent reply
                    fingerprint = hashlib.sha256(f'example|{agent_reply.lower()}'.encode()).hexdigest()

                    # Generate embedding
                    example_text = f'{user_msg}\n---\n{agent_reply}'
                    embedding = _generate_embedding(example_text, org_id_str)

                    # Determine stage from conversation intent or message context
                    stage = 'discovering'  # default
                    if conversation.intent:
                        stage_hints = {
                            'comprar': 'intent_to_buy',
                            'precio': 'considering',
                            'disponibilidad': 'considering',
                            'promoción': 'discovering',
                            'descripción': 'discovering',
                        }
                        for hint, stage_val in stage_hints.items():
                            if hint in conversation.intent.lower():
                                stage = stage_val
                                break

                    _, was_created = LearningCandidate.objects.get_or_create(
                        organization=org,
                        kind='conversation_example',
                        fingerprint=fingerprint,
                        defaults={
                            'conversation': conversation,
                            'title': f'Ejemplo: {user_msg[:60]}…',
                            'source_question': user_msg[:500],
                            'proposed_answer': agent_reply[:500],
                            'confidence': base_example_confidence,  # L5: outcome-based confidence
                            'evidence_count': 1,
                            'status': 'pending',
                            'metadata': {
                                'source': 'conversation_example',
                                'conversation_id': str(conversation_id),
                                'embedding': embedding,
                                'stage': stage,
                                'channel': conversation.canal,
                                'commercial_outcome': commercial_outcome,  # L5: track outcome
                                **source_meta,
                                **conversation_meta,
                            },
                        },
                    )
                    if was_created:
                        examples_created += 1

    logger.info(
        'learning_engine_done',
        conversation_id=str(conversation_id),
        organization=str(org.id),
        learnings_extracted=len(learnings),
        candidates_created=created,
        candidates_updated=updated,
        candidates_deduped=deduped,
        style_patterns_created=style_created,
        examples_created=examples_created,
    )
    # Mark conversation as processed so the sweep task skips it
    try:
        from apps.conversations.models import Conversation as Conv
        Conv.objects.filter(id=conversation_id).update(
            metadata=_merge_metadata(conversation_id, {'learning_processed': True})
        )
    except Exception:
        pass

    return {'status': 'ok', 'extracted': len(learnings), 'created': created, 'updated': updated, 'deduped': deduped, 'examples_created': examples_created}  # noqa: RET504


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
