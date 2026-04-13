"""
Session Manager — Load, create, update SalesSession state.
"""
import logging
from decimal import Decimal
from typing import Optional

from apps.ai_engine.models import SalesSession
from apps.conversations.models import Conversation, Message

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages SalesSession lifecycle and state updates."""

    @staticmethod
    def get_or_create(conversation: Conversation) -> SalesSession:
        """
        Load or create SalesSession for a conversation.

        Args:
            conversation: The Conversation instance

        Returns:
            SalesSession instance, created if not exists
        """
        try:
            return SalesSession.objects.get(conversation=conversation)
        except SalesSession.DoesNotExist:
            session = SalesSession.objects.create(
                conversation=conversation,
                organization=conversation.organization,
                stage='discovery',
                situation='discovery',
            )
            logger.info(f'Created new SalesSession for conversation {conversation.id}')
            return session

    @staticmethod
    def update(
        session: SalesSession,
        situation: str,
        action: 'AgentAction',
        context: dict,
        reply: str,
    ) -> None:
        """
        Update SalesSession state after bot response.

        Args:
            session: SalesSession to update
            situation: Detected customer situation
            action: DecisionEngine action with fetch/checkout flags
            context: Loaded context dict (products, kb, promos)
            reply: The bot's response text (for audit)
        """
        # Update situation
        if session.situation != situation:
            session.last_situation = session.situation
            session.situation = situation
            logger.info(f'Situation change: {session.last_situation} → {situation}')

        # Update intent
        if action.get('intent'):
            session.intent = action['intent']

        # Track shown products
        if context.get('recommended_products'):
            product_ids = [p['id'] for p in context['recommended_products']]
            session.shown_products = list(set(
                session.shown_products + product_ids
            ))[:50]  # Cap at 50 to avoid bloat

        # Extract and update budget if detected
        if context.get('detected_budget'):
            budget = context['detected_budget']
            if budget.get('min'):
                session.budget_min = Decimal(str(budget['min']))
            if budget.get('max'):
                session.budget_max = Decimal(str(budget['max']))

        # Update stage if checkout started
        if action.get('checkout_step'):
            session.checkout_step = action['checkout_step']
            if action['checkout_step'] >= 1:
                session.stage = 'checkout'

        # Update handoff flag
        if action.get('requires_handoff'):
            session.stage = 'handoff'

        # Increment message count
        session.message_count += 1

        # Update timestamp (auto)
        session.save(update_fields=[
            'situation', 'last_situation', 'intent', 'shown_products',
            'budget_min', 'budget_max', 'stage', 'checkout_step',
            'message_count', 'updated_at'
        ])

        logger.debug(
            f'Updated session {session.id}: '
            f'situation={situation}, stage={session.stage}, '
            f'msg_count={session.message_count}'
        )

    @staticmethod
    def get_context_summary(session: SalesSession, history: list) -> str:
        """
        Generate a brief session summary for LLM context.

        Used when message count exceeds threshold to avoid token bloat.

        Args:
            session: SalesSession instance
            history: Recent message history

        Returns:
            Markdown-formatted summary string
        """
        lines = [
            '## Session Summary',
            f'**Stage:** {session.stage}',
            f'**Situation:** {session.situation}',
        ]

        if session.intent:
            lines.append(f'**Intent:** {session.intent}')

        if session.budget_min or session.budget_max:
            budget_str = f'${session.budget_min or "?"}–${session.budget_max or "?"}'
            lines.append(f'**Budget:** {budget_str}')

        if session.category_interest:
            lines.append(f'**Interest:** {session.category_interest}')

        if session.selected_products:
            lines.append(f'**Interested in {len(session.selected_products)} products**')

        if session.objections:
            objs = ', '.join(session.objections[:3])
            lines.append(f'**Objections:** {objs}')

        if session.checkout_step:
            lines.append(f'**Checkout Step:** {session.checkout_step}')

        return '\n'.join(lines)
