"""
AI Router inbound handler.

`handle_inbound_message` is the single entry point connecting any inbound
message (WhatsApp, web chat, app chat) to the AI Router pipeline and executing
the resulting decision.

Returns (bot_reply_text, decision). The caller is responsible for persisting
the bot reply as a Message record and sending it back via the appropriate channel.
"""
from __future__ import annotations

import structlog
from datetime import datetime, timezone

from .schemas import RouteType, IntentName
from .router import build_ai_router_service
from .decision_object import RouterDecision
from .executors.direct_reply import DirectReplyExecutor
from .executors.escalate import EscalateExecutor
from .executors.block import BlockExecutor
from .executors.sales_agent import SalesAgentExecutor

logger = structlog.get_logger(__name__)

_SENTIMENT_MAP = {
    'positive': 'positivo',
    'negative': 'negativo',
    'neutral':  'neutro',
}


def _conversation_is_human_owned(conversation) -> bool:
    metadata = getattr(conversation, 'metadata', None) or {}
    operator_state = (metadata.get('operator_state') or {})
    return operator_state.get('owner') == 'humano'


def _active_ai_agent(conversation) -> str | None:
    metadata = getattr(conversation, 'metadata', None) or {}
    operator_state = (metadata.get('operator_state') or {})
    active_agent = operator_state.get('active_ai_agent')
    if active_agent in {'general', 'sales', 'marketing', 'operations'}:
        return active_agent
    return None


def _sales_agent_enabled(organization) -> bool:
    try:
        from apps.channels_config.models import ChannelConfig
        from apps.channels_config.settings_schema import normalise_settings

        config = (
            ChannelConfig.objects
            .filter(organization=organization, channel='onboarding')
            .only('settings')
            .first()
        )
        settings_payload = normalise_settings((config.settings or {}) if config else {})
        return (settings_payload.get('sales_agent') or {}).get('enabled', True)
    except Exception:
        return True


def handle_inbound_message(
    *,
    conversation,
    message,
    organization,
) -> tuple[str | None, RouterDecision | None]:
    """
    Run the full AI Router pipeline for an inbound message and execute the decision.

    Args:
        conversation: Conversation model instance (already saved)
        message:      Message model instance with role='user' (already saved)
        organization: Organization model instance

    Returns:
        (bot_reply_text, decision)
        bot_reply_text may be None if the route produces no reply (e.g. silent escalation).
    """
    try:
        raw_event = {
            'tenant_id': str(organization.id),
            'channel': conversation.canal,
            'contact_id': str(conversation.contact_id) if conversation.contact_id else None,
            'conversation_id': str(conversation.id),
            'sender_id': str(conversation.contact_id) if conversation.contact_id else None,
            'message_text': message.content,
            'language': 'es',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'metadata': {
                'canal': conversation.canal,
                'active_ai_agent': _active_ai_agent(conversation),
                'agent_capabilities': {
                    'sales_enabled': _sales_agent_enabled(organization),
                },
            },
        }

        router = build_ai_router_service()
        decision: RouterDecision = router.route(raw_event)

        # Update conversation intent + sentiment from router decision
        update_fields = ['updated_at']
        if decision.intent:
            conversation.intent = decision.intent
            update_fields.append('intent')
        sentiment_label = _SENTIMENT_MAP.get(decision.sentiment, 'neutro')
        if conversation.sentimiento != sentiment_label:
            conversation.sentimiento = sentiment_label
            update_fields.append('sentimiento')
        conversation.save(update_fields=update_fields)

        # Persist audit log (non-blocking)
        _persist_decision(conversation, message, decision, organization)

        if _conversation_is_human_owned(conversation):
            logger.info(
                'router_suppressed_for_human_owned_conversation',
                org_id=str(organization.id),
                conv_id=str(conversation.id),
                intent=decision.intent,
                route=str(decision.route),
            )
            return None, decision

        # Dispatch to executor
        bot_reply = _execute_decision(
            decision=decision,
            conversation=conversation,
            message=message,
            organization=organization,
        )

        logger.info(
            'router_handled',
            org_id=str(organization.id),
            conv_id=str(conversation.id),
            intent=decision.intent,
            route=str(decision.route),
            has_reply=bool(bot_reply),
        )
        return bot_reply, decision

    except Exception as exc:
        logger.error('router_handler_error', error=str(exc), exc_info=True)
        return 'Recibí tu mensaje. Un asesor lo revisará pronto.', None


def _execute_decision(
    *,
    decision: RouterDecision,
    conversation,
    message,
    organization,
) -> str | None:
    route = decision.route

    if route == RouteType.BLOCK_ACTION:
        executor = BlockExecutor()
    elif route == RouteType.ESCALATE_TO_HUMAN:
        executor = EscalateExecutor()
    elif route == RouteType.ROUTE_TO_SALES_AGENT:
        # First-class sales route: works on ANY channel (incl. WhatsApp).
        executor = SalesAgentExecutor() if _sales_agent_enabled(organization) else DirectReplyExecutor()
    else:
        # Route to SalesAgent for app/web channels (any intent)
        # SalesAgent handles discovery, product inquiries, checkout, etc.
        if conversation.canal in ('app', 'web'):
            executor = SalesAgentExecutor() if _sales_agent_enabled(organization) else EscalateExecutor()
        else:
            # WhatsApp, Instagram, etc. use DirectReply
            executor = DirectReplyExecutor()

    bot_reply = executor.execute(
        conversation=conversation,
        message=message,
        decision=decision,
        organization=organization,
    )

    try:
        metadata_getter = getattr(executor, 'get_message_metadata', None)
        if callable(metadata_getter):
            message_metadata = metadata_getter() or {}
            if message_metadata:
                decision.post_actions.append({
                    'action_type': 'bot_message_metadata',
                    'payload': message_metadata,
                })
    except Exception:
        logger.warning('executor_message_metadata_failed')

    try:
        followup_getter = getattr(executor, 'get_followup_message', None)
        if callable(followup_getter):
            followup_text = followup_getter()
            if followup_text:
                decision.post_actions.append({
                    'action_type': 'bot_followup_message',
                    'payload': {'text': followup_text},
                })
    except Exception:
        logger.warning('executor_followup_message_failed')

    return bot_reply


def _persist_decision(conversation, message, decision: RouterDecision, organization) -> None:
    try:
        from .models import RouterDecisionLog
        RouterDecisionLog.objects.create(
            organization=organization,
            conversation=conversation,
            message=message,
            decision_id=decision.decision_id,
            intent=decision.intent,
            confidence=decision.confidence,
            risk_level=decision.risk_level,
            route_type=str(decision.route),
            agent=decision.agent or '',
            model_name=decision.model_name or '',
            post_actions=decision.post_actions,
            full_decision=decision.to_dict(),
        )
    except Exception as exc:
        logger.warning('router_decision_persist_failed', error=str(exc))
