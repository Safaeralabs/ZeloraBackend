"""
Session Manager — Load, create, update SalesSession state.
"""
import logging
import re
from decimal import Decimal
from typing import Optional
from django.utils import timezone

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

        # Expire product repetition memory for stale sessions.
        if session.updated_at and (timezone.now() - session.updated_at).total_seconds() > 86400:
            session.shown_products = []

        # Track shown products
        if context.get('recommended_products'):
            product_ids = [p['id'] for p in context['recommended_products']]
            session.shown_products = list(dict.fromkeys(
                (session.shown_products or []) + product_ids
            ))[-20:]  # Keep recent product history only

        # Persist explicit product selections confirmed by the customer.
        if context.get('selected_product_ids'):
            session.selected_products = list(dict.fromkeys(
                (session.selected_products or []) + context['selected_product_ids']
            ))[:20]
            if session.selected_products and session.stage == 'discovery':
                session.stage = 'considering'

        resolution = context.get('product_resolution') or {}
        if resolution.get('category'):
            session.category_interest = resolution['category'][:100]

        detected_objections = context.get('detected_objections') or []
        if detected_objections:
            session.objections = list(dict.fromkeys(
                (session.objections or []) + detected_objections
            ))[:10]

        shipping_city = context.get('shipping_city')
        if shipping_city:
            session.shipping_city = shipping_city[:100]

        checkout_data = context.get('checkout_data') or {}
        if checkout_data:
            current_checkout = dict(session.checkout_data or {})
            current_checkout.update(checkout_data)
            session.checkout_data = current_checkout

        summary = context.get('session_summary')
        if summary:
            session.summary = summary

        # A completed order closes the current checkout flow and resets cart state
        # so subsequent messages can start a fresh shopping cycle.
        if context.get('order_completed'):
            session.stage = 'discovery'
            session.checkout_step = 0
            session.selected_products = []
            session.category_interest = ''

        forced_stage = str(context.get('force_stage') or '').strip().lower()
        if forced_stage == 'considering':
            session.stage = 'considering'
            session.checkout_step = 0

        # Extract and update budget if detected
        if context.get('detected_budget'):
            budget = context['detected_budget']
            if budget.get('min'):
                session.budget_min = Decimal(str(budget['min']))
            if budget.get('max'):
                session.budget_max = Decimal(str(budget['max']))

        # Update stage if checkout started and there is at least one selected product.
        if action.get('checkout_step'):
            has_cart_items = bool(session.selected_products)
            if has_cart_items:
                session.checkout_step = action['checkout_step']
                if action['checkout_step'] >= 1:
                    session.stage = 'checkout'
            else:
                session.checkout_step = 0
                if session.stage == 'checkout':
                    session.stage = 'considering' if session.category_interest else 'discovery'

        # Update handoff flag
        if action.get('requires_handoff'):
            session.stage = 'handoff'

        # Increment message count
        session.message_count += 1

        # Update timestamp (auto)
        session.save(update_fields=[
            'situation', 'last_situation', 'intent', 'shown_products', 'selected_products',
            'budget_min', 'budget_max', 'stage', 'checkout_step',
            'message_count', 'updated_at', 'category_interest', 'objections',
            'shipping_city', 'checkout_data', 'summary'
        ])

        logger.debug(
            f'Updated session {session.id}: '
            f'situation={situation}, stage={session.stage}, '
            f'msg_count={session.message_count}'
        )

        # Best-effort: mirror the signals above onto the contact's
        # cross-conversation memory (no-op for anonymous contacts).
        try:
            from apps.ai_engine.sales.contact_memory import ContactMemoryService
            ContactMemoryService.sync_from_session(session=session, situation=situation, context=context)
        except Exception:
            pass

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

    @staticmethod
    def extract_session_signals(*, user_message: str, action: dict, context: dict) -> dict:
        text = (user_message or '').strip()
        lowered = text.lower()
        signals = {
            'detected_objections': [],
            'shipping_city': '',
        }

        objection_patterns = {
            'price': ['caro', 'costoso', 'precio alto', 'muy costoso'],
            'shipping': ['envío caro', 'envio caro', 'demora', 'tarda mucho', 'entrega lenta'],
            'quality': ['no me convence', 'mala calidad', 'calidad'],
            'trust': ['no confío', 'no confio', 'seguro?', 'garantía', 'garantia'],
        }
        for label, patterns in objection_patterns.items():
            if any(pattern in lowered for pattern in patterns):
                signals['detected_objections'].append(label)

        city_match = re.search(
            r'\b(?:en|a|hasta)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)',
            text
        )
        if city_match and any(keyword in lowered for keyword in ['envío', 'envio', 'entrega', 'mandar']):
            signals['shipping_city'] = city_match.group(1)

        if action.get('checkout_step'):
            signals['checkout_data'] = {}
            signals['checkout_data']['last_user_message'] = text[:300]
            signals['checkout_data']['step'] = action['checkout_step']

        return signals
