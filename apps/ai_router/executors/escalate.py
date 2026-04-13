"""
EscalateExecutor — marks conversation as escalated and notifies the customer.
"""
from __future__ import annotations
from .base import BaseExecutor


class EscalateExecutor(BaseExecutor):
    def execute(self, *, conversation, message, decision, organization) -> str | None:
        from apps.conversations.models import TimelineEvent, Message

        conversation.estado = 'escalado'

        # Mark conversation as owned by human — this suppresses AI responses
        metadata = {**(conversation.metadata or {})}
        operator_state = {**(metadata.get('operator_state') or {})}
        operator_state['owner'] = 'humano'
        operator_state['commercial_status'] = 'escalado'
        metadata['operator_state'] = operator_state
        conversation.metadata = metadata
        conversation.save(update_fields=['estado', 'metadata', 'updated_at'])

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

        # Create system message for appchat to show escalation visually
        Message.objects.create(
            conversation=conversation,
            role='system',
            content='Conectado con un asesor. En breve te atenderán.',
        )

        return 'Voy a conectarte con un asesor humano que podrá ayudarte mejor. En breve te atenderán.'
