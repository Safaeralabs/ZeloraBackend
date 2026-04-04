from __future__ import annotations

import re

from apps.analytics.models import LearningCandidate
from apps.conversations.models import Conversation
from apps.knowledge_base.models import KBArticle


def _title_from_question(question: str) -> str:
    clean = re.sub(r'[?!.]+$', '', (question or '').strip())
    if len(clean) <= 110:
        return clean or 'Pregunta frecuente detectada'
    return f'{clean[:107]}...'


def learn_from_conversation(conversation: Conversation) -> dict[str, int]:
    """
    Compatibility wrapper.

    The only learning engine lives in apps.ai_engine.tasks. This wrapper keeps
    older imports working without maintaining a second heuristic pipeline.
    """
    from apps.ai_engine.tasks import run_learning_engine

    result = run_learning_engine(str(conversation.id))
    return {
        'created': int(result.get('created', 0) or 0),
        'updated': int(result.get('updated', 0) or 0),
        'extracted': int(result.get('extracted', 0) or 0),
    }


def generate_learning_candidates_for_org(*, organization, limit: int = 150) -> dict[str, int]:
    """
    Manual regeneration for the Learning UI.

    Uses the same LLM-based engine that runs on resolve/escalate/inactivity, so
    the system has a single learning pipeline.
    """
    from apps.ai_engine.tasks import run_learning_engine

    conversations = (
        Conversation.objects.filter(organization=organization)
        .order_by('-updated_at')[:limit]
    )
    totals = {'created': 0, 'updated': 0, 'extracted': 0, 'processed_conversations': 0}
    for conversation in conversations:
        result = run_learning_engine(str(conversation.id))
        totals['created'] += int(result.get('created', 0) or 0)
        totals['updated'] += int(result.get('updated', 0) or 0)
        totals['extracted'] += int(result.get('extracted', 0) or 0)
        totals['processed_conversations'] += 1
    return totals


def _apply_style_to_channel_config(candidate: LearningCandidate) -> None:
    """
    Append an approved style observation to ChannelConfig.brand_profile.customer_style_notes
    so the Sales Agent picks it up on the next conversation.
    """
    from apps.channels_config.models import ChannelConfig

    try:
        config, _ = ChannelConfig.objects.get_or_create(
            organization=candidate.organization,
            channel='onboarding',
            defaults={'settings': {}},
        )
        settings = dict(config.settings or {})

        # Append to brand_profile.customer_style_notes
        brand_profile = dict(settings.get('brand_profile') or {})
        existing_notes = brand_profile.get('customer_style_notes', '') or ''
        new_note = candidate.source_question.strip()
        if new_note and new_note not in existing_notes:
            separator = ' | ' if existing_notes else ''
            brand_profile['customer_style_notes'] = f'{existing_notes}{separator}{new_note}'
        settings['brand_profile'] = brand_profile

        # Mirror into sales_agent_profile.brand_profile too
        sales_agent_profile = dict(settings.get('sales_agent_profile') or {})
        sap_brand = dict(sales_agent_profile.get('brand_profile') or {})
        sap_brand['customer_style_notes'] = brand_profile['customer_style_notes']
        sales_agent_profile['brand_profile'] = sap_brand
        settings['sales_agent_profile'] = sales_agent_profile

        config.settings = settings
        config.save(update_fields=['settings', 'updated_at'])
    except Exception:
        pass  # Non-critical


def approve_learning_candidate(*, candidate: LearningCandidate, author=None) -> KBArticle:
    meta = candidate.metadata or {}
    is_llm = meta.get('source') == 'llm'

    if candidate.kind == 'estilo_comunicacion':
        # Style candidates update brand config directly instead of creating a KB article.
        _apply_style_to_channel_config(candidate)
        # Also create a brand_voice KB article so synthesize_playbook can incorporate it.
        content = (
            f'Patrón de estilo detectado en conversaciones reales:\n{candidate.source_question}\n\n'
            f'{candidate.proposed_answer}'
        ).strip()
        category = 'Estilo de comunicación'
        purpose = 'brand_voice'
        tags = sorted({'estilo', 'auto_learning', 'customer_style'})
        embedding = meta.get('embedding', [])
    elif is_llm:
        content = candidate.proposed_answer
        category = 'ai_aprendido'
        purpose = 'faq'
        tags = sorted(set(meta.get('tags', []) + ['ai_aprendido', 'auto_learning']))
        embedding = meta.get('embedding', [])
    elif candidate.kind == 'objection':
        content = (
            f'Objecion detectada:\n- {candidate.source_question}\n\n'
            f'Respuesta sugerida:\n{candidate.proposed_answer}'
        ).strip()
        category = 'Objeciones detectadas'
        purpose = 'objection'
        tags = sorted(set([candidate.kind, 'auto_learning', 'conversation_memory']))
        embedding = []
    else:
        content = (
            f'Pregunta detectada:\n- {candidate.source_question}\n\n'
            f'Respuesta recomendada:\n{candidate.proposed_answer}'
        ).strip()
        category = 'Aprendizaje automatico'
        purpose = 'faq'
        tags = sorted(set([candidate.kind, 'auto_learning', 'conversation_memory']))
        embedding = []

    article, created = KBArticle.objects.get_or_create(
        organization=candidate.organization,
        title=candidate.title or _title_from_question(candidate.source_question),
        defaults={
            'author': author,
            'content': content,
            'category': category,
            'purpose': purpose,
            'tags': tags,
            'status': 'published',
            'is_active': True,
            'embedding_vector': embedding,
        },
    )
    if not created and embedding:
        article.embedding_vector = embedding
        article.content = content
        article.save(update_fields=['content', 'embedding_vector', 'updated_at'])

    candidate.status = 'approved'
    candidate.approved_article = article
    candidate.save(update_fields=['status', 'approved_article', 'updated_at'])

    # Flywheel: re-synthesize playbook from KB so the agent adapts immediately
    try:
        from apps.ai_engine.tasks import synthesize_playbook_task
        synthesize_playbook_task.delay(str(candidate.organization_id))
    except Exception:
        pass  # Non-critical — synthesis will run on the weekly sweep anyway

    return article
