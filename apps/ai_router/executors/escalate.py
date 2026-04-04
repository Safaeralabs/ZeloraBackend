"""
EscalateExecutor — marks conversation as escalated and notifies the customer.
"""
from __future__ import annotations
from .base import BaseExecutor


class EscalateExecutor(BaseExecutor):
    def execute(self, *, conversation, message, decision, organization) -> str | None:
        from apps.conversations.models import TimelineEvent

        conversation.estado = 'escalado'
        conversation.save(update_fields=['estado', 'updated_at'])

        reasons = ', '.join(decision.policy_reasons) if decision.policy_reasons else 'router_decision'
        TimelineEvent.objects.create(
            conversation=conversation,
            tipo='escalated',
            descripcion=f'Escalado por AI Router. Intent: {decision.intent}. Razón: {reasons}',
            metadata={
                'decision_id': decision.decision_id,
                'intent': decision.intent,
                'risk_level': decision.risk_level,
            },
        )

        return 'Voy a conectarte con un asesor humano que podrá ayudarte mejor. En breve te atenderán.'
