"""
BlockExecutor — handles blocked messages (risk/security events).
"""
from __future__ import annotations
import structlog
from .base import BaseExecutor

logger = structlog.get_logger(__name__)


class BlockExecutor(BaseExecutor):
    def execute(self, *, conversation, message, decision, organization) -> str | None:
        from apps.conversations.models import TimelineEvent

        logger.warning(
            'router_message_blocked',
            conversation_id=str(conversation.id),
            decision_id=decision.decision_id,
            risk_flags=decision.risk_flags,
            org_id=str(organization.id),
        )

        TimelineEvent.objects.create(
            conversation=conversation,
            tipo='note',
            descripcion=f'Mensaje bloqueado por AI Router. Flags: {", ".join(decision.risk_flags)}',
            metadata={
                'decision_id': decision.decision_id,
                'blocked': True,
                'risk_flags': decision.risk_flags,
            },
        )

        return 'Lo siento, no puedo procesar esa solicitud. ¿Hay algo más en lo que pueda ayudarte?'
