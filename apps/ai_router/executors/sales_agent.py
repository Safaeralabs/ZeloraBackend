"""
Sales Agent Executor — Main orchestrator for AI sales conversations.

Architecture:
  The system decides what to do.
  The LLM decides how to say it.

Pipeline:
  1. Load/create SalesSession
  2. Detect customer situation (LLM)
  3. Decide what to do (pure logic, no LLM)
  4. Load context (products, KB, promos)
  5. Generate response (LLM)
  6. Validate response (anti-hallucination)
  7. Update session
  8. Return reply or escalate
"""
import logging
from typing import Optional

from .base import BaseExecutor
from apps.ai_router.models import Conversation, Message
from apps.ai_engine.models import SalesSession
from apps.ai_engine.sales.session import SessionManager
from apps.ai_engine.sales.situation import SituationDetector
from apps.ai_engine.sales.decision import DecisionEngine
from apps.ai_engine.sales.catalog import CatalogService
from apps.ai_engine.sales.kb import KBService
from apps.ai_engine.sales.promo import PromoEngine
from apps.ai_engine.sales.recommendations import RecommendationEngine
from apps.ai_engine.sales.generator import ResponseGenerator
from apps.ai_engine.sales.validator import ResponseValidator
from apps.ai_engine.sales.handoff import HandoffHandler

logger = logging.getLogger(__name__)


class SalesAgentExecutor(BaseExecutor):
    """
    Main executor for sales conversations.
    Orchestrates all sub-modules: session, situation, decision, context, generation, validation.
    """

    def execute(
        self,
        *,
        conversation: Conversation,
        message,
        decision,
        organization,
    ) -> Optional[str]:
        """
        Execute sales agent pipeline.

        Args:
            conversation: Conversation instance
            message: Message instance with user content
            decision: Router decision (contains intents, risk_score, etc.)
            organization: Organization instance

        Returns:
            Reply string, or None if handoff initiated
        """
        try:
            message_text = message.content
            logger.info(f'SalesAgent processing message for conv {conversation.id}')

            # ===== 1. Session =====
            session = SessionManager.get_or_create(conversation)

            # ===== 2. Load conversation history =====
            history = list(
                Message.objects.filter(conversation=conversation)
                .order_by('timestamp')
                .values_list('role', 'content')[-12:]
            )
            history_objs = list(
                Message.objects.filter(conversation=conversation)
                .order_by('timestamp')[-12:]
            )

            # ===== 3. Detect situation (LLM) =====
            situation = SituationDetector.detect(
                user_message=message_text,
                conversation_history=history_objs,
                session=session,
            )
            logger.info(f'Detected situation: {situation}')

            # ===== 4. Decide what to do (pure logic) =====
            action = DecisionEngine.decide(situation, session)
            logger.info(f'Decision: {action}')

            # ===== 5a. Handoff check =====
            if action.get('requires_handoff'):
                reason = action.get('handoff_reason', 'User request')
                reply = HandoffHandler.escalate(conversation, session, organization, reason)
                return reply

            # ===== 5b. Load context based on decision =====
            context = self._load_context(
                action=action,
                session=session,
                organization=organization,
                message_text=message_text,
            )

            # ===== 6. Generate response (LLM) =====
            reply = ResponseGenerator.generate(
                user_message=message_text,
                conversation_history=history_objs,
                session=session,
                situation=situation,
                action=action,
                context=context,
            )
            logger.info(f'Generated reply: {len(reply)} chars')

            # ===== 7. Validate response =====
            reply = ResponseValidator.validate(reply, context)

            # ===== 8. Update session =====
            SessionManager.update(
                session=session,
                situation=situation,
                action=action,
                context=context,
                reply=reply,
            )

            return reply

        except Exception as e:
            logger.error(f'SalesAgent execution failed: {e}', exc_info=True)
            return self._safe_fallback()

    def _load_context(
        self,
        action: dict,
        session: SalesSession,
        organization,
        message_text: str,
    ) -> dict:
        """
        Load context (products, KB, promos) based on decision action.

        Args:
            action: DecisionEngine action
            session: SalesSession
            organization: Organization
            message_text: User message for search

        Returns:
            Context dict with recommended_products, kb_content, promotions
        """
        context = {
            'recommended_products': [],
            'kb_content': '',
            'promotions': [],
        }

        try:
            # Fetch products if requested
            if action.get('fetch_products'):
                strategy = action.get('response_strategy', 'discover')

                # If specific product search
                if strategy == 'discover' or strategy == 'recommend':
                    products = CatalogService.search(
                        query=message_text,
                        organization=organization,
                        session=session,
                        limit=5,
                    )
                    context['recommended_products'] = products

                # Build recommendations if we have base products
                if session.selected_products:
                    rec_set = RecommendationEngine.build(
                        base_products=session.selected_products,
                        session=session,
                        organization=organization,
                    )
                    # Add recommendation details to context for prompt inclusion
                    if rec_set.get('primary'):
                        if not context['recommended_products']:
                            context['recommended_products'] = []
                        context['recommended_products'].insert(0, rec_set['primary'])

            # Fetch KB if requested
            if action.get('fetch_kb'):
                purposes = action.get('fetch_kb', [])
                kb_content = KBService.fetch(
                    purposes=purposes,
                    organization=organization,
                    query=message_text,
                    max_articles=3,
                )
                if kb_content:
                    context['kb_content'] = kb_content

            # Fetch promotions if requested
            if action.get('fetch_promotions'):
                product_ids = [p['id'] for p in context.get('recommended_products', [])]
                category = session.category_interest

                promos = PromoEngine.get_active(
                    organization=organization,
                    products=product_ids if product_ids else None,
                    category=category,
                )
                context['promotions'] = promos

            logger.info(
                f'Loaded context: {len(context["recommended_products"])} products, '
                f'{len(context["kb_content"])} KB chars, '
                f'{len(context["promotions"])} promos'
            )

        except Exception as e:
            logger.error(f'Context loading failed: {e}')

        return context

    def _safe_fallback(self) -> str:
        """
        Return safe fallback when execution fails.

        Returns:
            Safe generic reply
        """
        return 'Disculpa, tuve un error procesando tu mensaje. Por favor intenta de nuevo.'
