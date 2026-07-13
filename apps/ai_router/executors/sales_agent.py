"""
Sales Agent Executor Ã¢â‚¬â€ Main orchestrator for AI sales conversations.

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
from decimal import Decimal
from typing import Optional
from django.utils import timezone

from .base import BaseExecutor
from apps.conversations.models import Conversation, Message
from apps.ai_engine.models import SalesSession
from apps.ai_engine.sales.session import SessionManager
from apps.ai_engine.sales.situation import SituationDetector
from apps.ai_engine.sales.decision import DecisionEngine
from apps.ai_engine.sales.policy import SalesPolicyEngine
from apps.ai_engine.sales.catalog import CatalogService
from apps.ai_engine.sales.kb import KBService
from apps.ai_engine.sales.examples import ExampleBank
from apps.ai_engine.sales.customer_history import CustomerHistoryService
from apps.ai_engine.sales.contact_memory import ContactMemoryService
from apps.ai_engine.sales.promo import PromoEngine
from apps.ai_engine.sales.recommendations import RecommendationEngine
from apps.ai_engine.sales.generator import ResponseGenerator
from apps.ai_engine.sales.validator import ResponseValidator
from apps.ai_engine.sales.contracts import ResponseContractEnforcer
from apps.ai_engine.sales.handoff import HandoffHandler

logger = logging.getLogger(__name__)


class SalesAgentExecutor(BaseExecutor):
    """
    Main executor for sales conversations.
    Orchestrates all sub-modules: session, situation, decision, context, generation, validation.
    """

    def __init__(self) -> None:
        self._message_metadata: dict = {}
        self._followup_message: str | None = None
        self._current_message = None

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
        self._message_metadata = {}
        self._followup_message = None
        self._current_message = message

        try:
            message_text = message.content
            logger.info(f'SalesAgent processing message for conv {conversation.id}')

            # ===== 1. Session =====
            session = SessionManager.get_or_create(conversation)
            removed_product_event = self._handle_cart_item_removal(session=session, organization=organization)

            # ===== 2. Load conversation history =====
            # Django QuerySets don't support negative indexing Ã¢â‚¬â€ fetch newest first, then reverse
            history_objs = list(
                Message.objects.filter(
                    conversation=conversation,
                    conversation__organization=organization,
                )
                .order_by('-timestamp')[:12]
            )
            history_objs.reverse()  # oldest Ã¢â€ â€™ newest order for LLM context

            # ===== 3. Detect situation (LLM) =====
            situation = SituationDetector.detect(
                user_message=message_text,
                conversation_history=history_objs,
                session=session,
            )
            logger.info(f'Detected situation: {situation}')

            # ===== 4. Decide what to do (pure logic) =====
            action = DecisionEngine.decide(situation, session.stage)
            logger.info(f'Decision: {action}')

            # ===== 5a. Handoff check =====
            if action.get('requires_handoff'):
                reason = action.get('handoff_reason', 'User request')
                reply = HandoffHandler.escalate(conversation, session, organization, reason)
                return reply

            # ===== 5b. Build accumulated query from recent user messages =====
            # Combines current message + past user turns so attributes like
            # "blancos", "formales", "gamuza" accumulate into a richer search query
            user_messages = [
                msg.content for msg in history_objs
                if msg.role == 'user'
            ][-4:]
            accumulated_query = self._build_catalog_query(
                current_message=message_text,
                user_messages=user_messages,
            )

            # ===== 5c. Load context based on decision =====
            context = self._load_context(
                action=action,
                session=session,
                organization=organization,
                message_text=accumulated_query,
            )
            if isinstance(getattr(session, 'checkout_data', None), dict) and session.checkout_data:
                merged_checkout = dict(session.checkout_data)
                incoming_checkout = context.get('checkout_data')
                if isinstance(incoming_checkout, dict):
                    merged_checkout.update(incoming_checkout)
                context['checkout_data'] = merged_checkout
            if removed_product_event:
                context['cart_event'] = removed_product_event
            context['shipping_profile'] = self._load_shipping_profile(organization)
            context['payment_profile'] = self._load_payment_profile(organization)

            shipping_submission = self._extract_shipping_form_submission()
            if shipping_submission:
                checkout_data = context.get('checkout_data') or {}
                checkout_data['shipping_form'] = shipping_submission
                checkout_data['shipping_form_updated_at'] = timezone.now().isoformat()
                context['checkout_data'] = checkout_data
                if shipping_submission.get('city'):
                    context['shipping_city'] = shipping_submission.get('city')

            checkout_submission = self._extract_compact_checkout_submission()

            # Policy guards must run BEFORE the checkout handlers below:
            # an exploration message from checkout has to reopen the sale
            # (force_stage=considering) instead of being hijacked by the
            # "missing checkout data" guidance.
            action = self._apply_policy_guards(
                action=action,
                session=session,
                context=context,
                situation=situation,
                shipping_submission=shipping_submission,
                checkout_submission=checkout_submission,
            )

            checkout_data = context.get('checkout_data') or {}
            awaiting_order_confirmation = bool(checkout_data.get('awaiting_order_confirmation'))
            has_confirmed_order = bool(str(checkout_data.get('order_id') or '').strip())

            inferred_payment_method = self._infer_requested_payment_method(message_text)
            if inferred_payment_method and not has_confirmed_order:
                compact_form = dict(checkout_data.get('compact_checkout_form') or {})
                if compact_form.get('payment_method') != inferred_payment_method:
                    compact_form['payment_method'] = inferred_payment_method
                    checkout_data['compact_checkout_form'] = compact_form
                    checkout_data['compact_checkout_form_updated_at'] = timezone.now().isoformat()
                    context['checkout_data'] = checkout_data

            if checkout_submission:
                checkout_data['compact_checkout_form'] = checkout_submission
                checkout_data['compact_checkout_form_updated_at'] = timezone.now().isoformat()
                context['checkout_data'] = checkout_data
                if checkout_submission.get('city'):
                    context['shipping_city'] = checkout_submission.get('city')

                can_auto_confirm_now = (
                    not has_confirmed_order
                    and not awaiting_order_confirmation
                    and self._is_explicit_order_confirmation(message_text)
                    and self._is_checkout_submission_complete(context=context, session=session, action=action)
                )
                if can_auto_confirm_now:
                    order_result = self._create_guest_checkout_order(
                        organization=organization,
                        conversation=conversation,
                        session=session,
                        context=context,
                        submission=checkout_submission,
                    )
                    if order_result:
                        return self._finalize_order_confirmation(
                            session=session,
                            situation=situation,
                            action=action,
                            context=context,
                            message_text=message_text,
                            order_result=order_result,
                        )

                # Two-step checkout:
                # 1) save draft data and request explicit confirmation
                # 2) create order only after a dedicated confirmation turn
                if not has_confirmed_order and not awaiting_order_confirmation:
                    checkout_data['awaiting_order_confirmation'] = True
                    checkout_data['awaiting_order_confirmation_at'] = timezone.now().isoformat()
                    context['checkout_data'] = checkout_data
                    reply = self._build_order_confirmation_request(
                        context=context,
                        session=session,
                        action=action,
                    )
                    reply = ResponseValidator.validate(reply, context)
                    reply = ResponseContractEnforcer.enforce(
                        reply=reply,
                        session_stage=str(session.stage or ''),
                        action=action,
                        context=context,
                        user_message=message_text,
                    )
                    self._message_metadata = self._build_message_metadata(context, session=session, action=action)
                    self._merge_session_signals(
                        context=context,
                        signals=SessionManager.extract_session_signals(
                            user_message=message_text,
                            action=action,
                            context=context,
                        ),
                    )
                    SessionManager.update(
                        session=session,
                        situation=situation,
                        action=action,
                        context=context,
                        reply=reply,
                    )
                    return reply

            if (
                not has_confirmed_order
                and awaiting_order_confirmation
                and self._is_explicit_order_confirmation(message_text)
            ):
                draft_submission = dict((context.get('checkout_data') or {}).get('compact_checkout_form') or {})
                order_result = self._create_guest_checkout_order(
                    organization=organization,
                    conversation=conversation,
                    session=session,
                    context=context,
                    submission=draft_submission,
                )
                if order_result:
                    return self._finalize_order_confirmation(
                        session=session,
                        situation=situation,
                        action=action,
                        context=context,
                        message_text=message_text,
                        order_result=order_result,
                    )

            pending_payment_reply = self._handle_pending_payment_ping(
                message_text=message_text,
                context=context,
            )
            if pending_payment_reply:
                pending_payment_reply = ResponseValidator.validate(pending_payment_reply, context)
                pending_payment_reply = ResponseContractEnforcer.enforce(
                    reply=pending_payment_reply,
                    session_stage=str(session.stage or ''),
                    action=action,
                    context=context,
                    user_message=message_text,
                )
                self._message_metadata = self._build_message_metadata(context, session=session, action=action)
                self._merge_session_signals(
                    context=context,
                    signals=SessionManager.extract_session_signals(
                        user_message=message_text,
                        action=action,
                        context=context,
                    ),
                )
                SessionManager.update(
                    session=session,
                    situation=situation,
                    action=action,
                    context=context,
                    reply=pending_payment_reply,
                )
                return pending_payment_reply

            post_order_modification_reply, post_order_modification_handoff = self._handle_post_order_modification_request(
                message_text=message_text,
                context=context,
            )
            if post_order_modification_reply:
                if post_order_modification_handoff:
                    HandoffHandler.escalate(
                        conversation=conversation,
                        session=session,
                        organization=organization,
                        reason='order_modification',
                    )
                self._message_metadata = {}
                self._merge_session_signals(
                    context=context,
                    signals=SessionManager.extract_session_signals(
                        user_message=message_text,
                        action=action,
                        context=context,
                    ),
                )
                SessionManager.update(
                    session=session,
                    situation=situation,
                    action=action,
                    context=context,
                    reply=post_order_modification_reply,
                )
                return post_order_modification_reply

            post_order_payment_reply, post_order_payment_handoff = self._handle_post_order_payment_question(
                message_text=message_text,
                context=context,
                organization=organization,
            )
            if post_order_payment_reply:
                if post_order_payment_handoff:
                    HandoffHandler.escalate(
                        conversation=conversation,
                        session=session,
                        organization=organization,
                        reason='payment',
                    )
                    self._message_metadata = {}
                    return post_order_payment_reply

                post_order_payment_reply = ResponseValidator.validate(post_order_payment_reply, context)
                post_order_payment_reply = ResponseContractEnforcer.enforce(
                    reply=post_order_payment_reply,
                    session_stage=str(session.stage or ''),
                    action=action,
                    context=context,
                    user_message=message_text,
                )
                self._message_metadata = {}
                self._merge_session_signals(
                    context=context,
                    signals=SessionManager.extract_session_signals(
                        user_message=message_text,
                        action=action,
                        context=context,
                    ),
                )
                SessionManager.update(
                    session=session,
                    situation=situation,
                    action=action,
                    context=context,
                    reply=post_order_payment_reply,
                )
                return post_order_payment_reply

            post_order_shipping_reply, post_order_shipping_handoff = self._handle_post_order_shipping_question(
                message_text=message_text,
                context=context,
                organization=organization,
            )
            if post_order_shipping_reply:
                if post_order_shipping_handoff:
                    HandoffHandler.escalate(
                        conversation=conversation,
                        session=session,
                        organization=organization,
                        reason='shipping_delivery_unknown',
                    )
                    self._message_metadata = {}
                    return post_order_shipping_reply

                post_order_shipping_reply = ResponseValidator.validate(post_order_shipping_reply, context)
                post_order_shipping_reply = ResponseContractEnforcer.enforce(
                    reply=post_order_shipping_reply,
                    session_stage=str(session.stage or ''),
                    action=action,
                    context=context,
                    user_message=message_text,
                )
                self._message_metadata = {}
                self._merge_session_signals(
                    context=context,
                    signals=SessionManager.extract_session_signals(
                        user_message=message_text,
                        action=action,
                        context=context,
                    ),
                )
                SessionManager.update(
                    session=session,
                    situation=situation,
                    action=action,
                    context=context,
                    reply=post_order_shipping_reply,
                )
                return post_order_shipping_reply

            pre_order_payment_without_cart = self._handle_pre_order_payment_without_cart(
                message_text=message_text,
                session=session,
                context=context,
            )
            if pre_order_payment_without_cart:
                pre_order_payment_without_cart = ResponseValidator.validate(pre_order_payment_without_cart, context)
                pre_order_payment_without_cart = ResponseContractEnforcer.enforce(
                    reply=pre_order_payment_without_cart,
                    session_stage=str(session.stage or ''),
                    action=action,
                    context=context,
                    user_message=message_text,
                )
                self._message_metadata = {}
                self._merge_session_signals(
                    context=context,
                    signals=SessionManager.extract_session_signals(
                        user_message=message_text,
                        action=action,
                        context=context,
                    ),
                )
                SessionManager.update(
                    session=session,
                    situation=situation,
                    action=action,
                    context=context,
                    reply=pre_order_payment_without_cart,
                )
                return pre_order_payment_without_cart

            pre_order_checkout_reply = self._handle_pre_order_checkout_guidance(
                message_text=message_text,
                session=session,
                action=action,
                context=context,
            )
            if pre_order_checkout_reply:
                pre_order_checkout_reply = ResponseValidator.validate(pre_order_checkout_reply, context)
                pre_order_checkout_reply = ResponseContractEnforcer.enforce(
                    reply=pre_order_checkout_reply,
                    session_stage=str(session.stage or ''),
                    action=action,
                    context=context,
                    user_message=message_text,
                )
                self._message_metadata = self._build_message_metadata(context, session=session, action=action)
                self._merge_session_signals(
                    context=context,
                    signals=SessionManager.extract_session_signals(
                        user_message=message_text,
                        action=action,
                        context=context,
                    ),
                )
                SessionManager.update(
                    session=session,
                    situation=situation,
                    action=action,
                    context=context,
                    reply=pre_order_checkout_reply,
                )
                return pre_order_checkout_reply

            payment_handoff_reason = self._resolve_payment_info_handoff_reason(
                message_text=message_text,
                context=context,
            )
            if payment_handoff_reason:
                reply = HandoffHandler.escalate(
                    conversation=conversation,
                    session=session,
                    organization=organization,
                    reason='payment',
                )
                self._message_metadata = {}
                return reply

            if removed_product_event:
                event_type = str(removed_product_event.get('type') or '')
                removed_product_id = str(removed_product_event.get('product_id') or '')
                if removed_product_id:
                    # Never re-suggest the product the customer just removed.
                    context['recommended_products'] = [
                        product for product in (context.get('recommended_products') or [])
                        if str((product or {}).get('id') or '') != removed_product_id
                    ]
                if event_type == 'blocked_after_order':
                    order_number = (removed_product_event.get('order_number') or '').strip()
                    order_ref = f' #{order_number}' if order_number else ''
                    reply = (
                        f'Tu pedido{order_ref} ya fue confirmado y no puedo modificarlo desde este carrito. '
                        'Si quieres, te ayudo a crear un nuevo pedido con los productos que elijas.'
                    )
                elif event_type == 'empty_cart_noop':
                    reply = (
                        'Tu carrito ya esta vacio. '
                        'Si quieres, te muestro opciones para volver a agregar productos.'
                    )
                elif event_type == 'missing_item_noop':
                    reply = (
                        'Ese producto ya no esta en tu carrito. '
                        'Si quieres, te ayudo a revisar lo que te queda disponible.'
                    )
                else:
                    removed_title = (removed_product_event.get('removed_product_title') or 'ese producto').strip()
                    retention_allowed = bool(removed_product_event.get('retention_allowed'))
                    remaining_items = int(removed_product_event.get('remaining_items_count') or 0)
                    if retention_allowed:
                        # Kept generic on purpose: this fires for any catalog vertical
                        # (ropa, utiles escolares, servicios...), so it can't assume
                        # fashion-only attributes like talla/color/estilo.
                        if remaining_items <= 0:
                            reply = (
                                f'Listo, ya quite {removed_title} del carrito. '
                                'Si quieres, te muestro opciones parecidas. '
                                '¿Que no te convencio: el precio, la calidad o algo mas?'
                            )
                        else:
                            reply = (
                                f'Listo, ya quite {removed_title}. '
                                'Si quieres, te ayudo a reemplazarlo por algo que te encaje mejor. '
                                '¿Que no te convencio: el precio, la calidad o algo mas?'
                            )
                    else:
                        if remaining_items <= 0:
                            reply = (
                                f'Hecho, ya quite {removed_title} y tu carrito quedo vacio. '
                                'Â¿Quieres que te muestre algo mas?'
                            )
                        else:
                            reply = (
                                f'Hecho, ya quite {removed_title}. '
                                'Â¿Quieres que te muestre algo mas parecido a lo que buscas?'
                            )
                reply = ResponseValidator.validate(reply, context)
                if event_type in {'blocked_after_order', 'empty_cart_noop', 'missing_item_noop'}:
                    self._message_metadata = {}
                else:
                    self._message_metadata = self._build_message_metadata(context, session=session, action=action)
                if event_type != 'blocked_after_order':
                    # Ship the post-removal cart state so the client widget can
                    # sync (or hide itself when the cart became empty).
                    self._attach_cart_snapshot(session=session, organization=organization)

                self._merge_session_signals(
                    context=context,
                    signals=SessionManager.extract_session_signals(
                        user_message=message_text,
                        action=action,
                        context=context,
                    ),
                )
                SessionManager.update(
                    session=session,
                    situation=situation,
                    action=action,
                    context=context,
                    reply=reply,
                )
                return reply

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
            reply = ResponseContractEnforcer.enforce(
                reply=reply,
                session_stage=str(session.stage or ''),
                action=action,
                context=context,
                user_message=message_text,
            )
            self._message_metadata = self._build_message_metadata(context, session=session, action=action)

            # ===== 8. Update session =====
            self._merge_session_signals(
                context=context,
                signals=SessionManager.extract_session_signals(
                    user_message=message_text,
                    action=action,
                    context=context,
                ),
            )
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
            self._message_metadata = {}
            return self._safe_fallback()

    def get_message_metadata(self) -> dict:
        return dict(self._message_metadata or {})

    def get_followup_message(self) -> str | None:
        return self._followup_message

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
            'unavailable_products': [],
            'kb_content': '',
            'sales_examples': '',
            'customer_order_history': '',
            'customer_history_totals': [],
            'contact_memory_summary': '',
            'order_lookup': '',
            'promotions': [],
            'product_resolution': {},
            'selected_product_ids': [],
        }

        try:
            from apps.ai_engine.sales.brand import BrandVoice
            context['brand_guard'] = BrandVoice.brand_guard(
                BrandVoice.load_runtime_config(organization)
            )
        except Exception as e:
            logger.error(f'Brand guard loading failed: {e}')

        try:
            from apps.ecommerce.models import Product
            # Full catalog titles: the validator's allowed set for product
            # mentions, so real products are never flagged as hallucinations.
            context['catalog_titles'] = list(
                Product.objects.filter(organization=organization).values_list('title', flat=True)[:300]
            )
        except Exception as e:
            logger.error(f'Catalog titles loading failed: {e}')

        try:
            # Cross-conversation memory: if this contact has a stable identity
            # (email/phone resolved during a past checkout), surface their
            # order history and soft preference signals so a brand-new
            # conversation isn't a blank slate.
            contact = getattr(session.conversation, 'contact', None)
            history = CustomerHistoryService.fetch(
                organization=organization,
                contact=contact,
                exclude_conversation_id=session.conversation_id,
            )
            if history['text']:
                context['customer_order_history'] = history['text']
                context['customer_history_totals'] = history['totals']

            contact_memory_summary = ContactMemoryService.fetch_summary(contact=contact)
            if contact_memory_summary:
                context['contact_memory_summary'] = contact_memory_summary
        except Exception as e:
            logger.error(f'Customer history loading failed: {e}')

        try:
            # Explicit order-number lookup: the customer typed a code (e.g.
            # from their confirmation message) and wants its status. Distinct
            # from customer_order_history above, which only auto-surfaces the
            # last few orders for a *recognized* contact — this handles a
            # specific order the agent wouldn't otherwise have in context.
            from apps.ai_engine.sales.order_lookup import OrderLookupService
            current_message_text = getattr(self._current_message, 'content', '') or message_text
            order_lookup = OrderLookupService.build_context(
                organization=organization,
                message_text=current_message_text,
                requester_contact=contact,
            )
            if order_lookup['text']:
                context['order_lookup'] = order_lookup['text']
        except Exception as e:
            logger.error(f'Order lookup failed: {e}')

        try:
            selected_product_ids = self._extract_selected_product_ids(
                organization=organization,
                session=session,
            )
            if selected_product_ids:
                selected_products = [
                    CatalogService.get_product_by_id(product_id, organization)
                    for product_id in selected_product_ids
                ]
                selected_products = [product for product in selected_products if product]
                if selected_products:
                    context['recommended_products'] = selected_products
                    context['selected_product_ids'] = selected_product_ids
                    context['product_resolution'] = {
                        'match_type': 'confirmed_selection',
                        'needs_confirmation': False,
                        'query_type': 'product_lookup',
                        'interpreted_query': ', '.join(
                            product.get('title', '') for product in selected_products[:2]
                        ),
                        'reason': 'user_selected_product',
                        'confidence': 1.0,
                    }

            if (session.stage == 'checkout' or action.get('checkout_step')) and session.selected_products:
                revalidated = [
                    CatalogService.get_product_by_id(product_id, organization)
                    for product_id in session.selected_products
                ]
                revalidated = [product for product in revalidated if product]
                context['recommended_products'] = revalidated
                context['product_resolution'] = {
                    'match_type': 'checkout_revalidation',
                    'needs_confirmation': False,
                    'query_type': 'product_lookup',
                    'interpreted_query': ', '.join(
                        product.get('title', '') for product in revalidated[:2]
                    ),
                    'reason': 'checkout_revalidation',
                    'confidence': 1.0,
                }

            # Always search products if:
            # a) action explicitly requests it, OR
            # b) session already has category_interest (client has been giving attributes)
            should_fetch_products = (
                action.get('fetch_products')
                or bool(session.category_interest)
            )

            if should_fetch_products and not context['recommended_products']:
                # Build enriched query combining current message + session accumulated context
                query_parts = [message_text]
                if session.category_interest:
                    query_parts.append(session.category_interest)

                enriched_query = ' '.join(filter(None, query_parts))

                resolution = CatalogService.resolve_query(
                    query=enriched_query,
                    organization=organization,
                    session=session,
                    limit=5,
                )
                resolution_meta = resolution.get('resolution') or {}
                if not resolution_meta.get('category'):
                    interpreted = str(resolution_meta.get('interpreted_query') or '').strip().lower()
                    if interpreted:
                        stopwords = {'quiero', 'busco', 'necesito', 'me', 'interesa', 'de', 'del', 'la', 'el', 'los', 'las', 'un', 'una'}
                        token = next((part for part in interpreted.split() if part and part not in stopwords), interpreted.split()[0])
                        resolution_meta['category'] = token[:100]
                        resolution['resolution'] = resolution_meta
                context['recommended_products'] = resolution.get('products', [])
                context['unavailable_products'] = resolution.get('unavailable_products', [])
                context['product_resolution'] = resolution.get('resolution', {})

                # Build recommendations if we have base products
                if session.selected_products and not context['product_resolution'].get('needs_confirmation'):
                    rec_set = RecommendationEngine.build(
                        base_products=session.selected_products,
                        session=session,
                        organization=organization,
                    )
                    if rec_set.get('primary'):
                        context['recommended_products'].insert(0, rec_set['primary'])

            if self._is_variant_question(message_text):
                variant_info = self._resolve_variant_info(
                    session=session,
                    context=context,
                    organization=organization,
                )
                if variant_info:
                    context['variant_info'] = variant_info

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

            # Few-shot: how the brand actually replied in similar situations.
            # Cheap when the org has no approved examples (single indexed query).
            sales_examples = ExampleBank.fetch(
                organization=organization,
                query=message_text,
                stage=session.stage,
                max_examples=2,
            )
            if sales_examples:
                context['sales_examples'] = sales_examples

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

    def _extract_selected_product_ids(self, *, organization, session: SalesSession) -> list[str]:
        structured_payload = {}
        message = getattr(self, '_current_message', None)
        if message is not None:
            structured_payload = (getattr(message, 'metadata', None) or {}).get('structured_payload') or {}

        if not isinstance(structured_payload, dict):
            return []

        interactive = structured_payload.get('interactive') or structured_payload
        if not isinstance(interactive, dict):
            return []

        if interactive.get('action') == 'select_product':
            product_id = str(interactive.get('product_id') or '').strip()
            return [product_id] if product_id else []

        message_text = str(getattr(message, 'content', '') or '').strip()
        if not self._is_implicit_selection_intent(message_text):
            return []

        try:
            resolution = CatalogService.resolve_query(
                query=message_text,
                organization=organization,
                session=session,
                limit=3,
            )
        except Exception:
            return []

        products = [item for item in (resolution.get('products') or []) if isinstance(item, dict)]
        if not products:
            return []

        resolution_meta = resolution.get('resolution') or {}
        needs_confirmation = bool(resolution_meta.get('needs_confirmation'))
        if len(products) == 1 and not needs_confirmation:
            product_id = str(products[0].get('id') or '').strip()
            return [product_id] if product_id else []

        lowered = message_text.lower()
        matches = []
        for product in products:
            title = str(product.get('title') or '').strip().lower()
            product_id = str(product.get('id') or '').strip()
            if not title or not product_id:
                continue
            if title in lowered or lowered in title:
                matches.append(product_id)

        if matches:
            return list(dict.fromkeys(matches))[:1]

        return []

    @staticmethod
    def _is_implicit_selection_intent(message_text: str) -> bool:
        text = (message_text or '').strip().lower()
        if not text:
            return False
        keywords = (
            'me lo llevo',
            'me la llevo',
            'me llevo',
            'lo llevo',
            'la llevo',
            'lo quiero',
            'la quiero',
            'me quedo con',
            'me interesa',
            'agregalo',
            'agrÃ©galo',
            'agregar al carrito',
        )
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _is_variant_question(message_text: str) -> bool:
        text = (message_text or '').strip().lower()
        if not text:
            return False
        return any(
            token in text
            for token in (
                'talla',
                'tallas',
                'size',
                'sizes',
                'color',
                'colores',
                'referencia',
                'sku',
            )
        )

    def _resolve_variant_info(self, *, session: SalesSession, context: dict, organization) -> dict:
        candidate_ids = []
        candidate_ids.extend([
            str(item) for item in (context.get('selected_product_ids') or [])
            if str(item).strip()
        ])
        candidate_ids.extend([
            str(item) for item in (session.selected_products or [])
            if str(item).strip()
        ])
        candidate_ids.extend([
            str((item or {}).get('id') or '')
            for item in (context.get('recommended_products') or [])
            if str((item or {}).get('id') or '').strip()
        ])
        candidate_ids = list(dict.fromkeys(candidate_ids))
        if not candidate_ids:
            return {}

        product_id = candidate_ids[0]
        product = CatalogService.get_product_by_id(product_id, organization)
        if not product:
            return {}

        snapshot = CatalogService.get_variant_snapshot(product_id, organization)
        return {
            'product_id': product_id,
            'product_title': str(product.get('title') or '').strip(),
            'labels_available': snapshot.get('labels_available') or [],
            'labels_unavailable': snapshot.get('labels_unavailable') or [],
        }

    @staticmethod
    def _is_explicit_order_confirmation(message_text: str) -> bool:
        text = (message_text or '').strip().lower()
        if not text:
            return False
        keywords = (
            'confirmo mi pedido',
            'confirmar pedido',
            'si, confirmo',
            'sÃ­, confirmo',
            'si confirmo',
            'sÃ­ confirmo',
            'confirmalo',
            'confÃ­rmalo',
            'confirmar compra',
            'listo, confirmo',
        )
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _asked_for_payment_details(message_text: str) -> bool:
        text = (message_text or '').strip().lower()
        if not text:
            return False
        keywords = (
            'como lo pago',
            'cÃ³mo lo pago',
            'como pago',
            'cÃ³mo pago',
            'que cuenta',
            'quÃ© cuenta',
            'numero de cuenta',
            'nÃºmero de cuenta',
            'datos bancarios',
            'cuenta bancaria',
            'datos de pago',
            'instrucciones de pago',
            'como transfiero',
            'cÃ³mo transfiero',
            'donde transfiero',
            'dÃ³nde transfiero',
            'a donde transfiero',
            'a dÃ³nde transfiero',
            'a que cuenta',
            'a quÃ© cuenta',
            'a que nequi',
            'a quÃ© nequi',
            'numero nequi',
            'nÃºmero nequi',
            'titular nequi',
        )
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _infer_requested_payment_method(message_text: str) -> str:
        text = (message_text or '').strip().lower()
        if not text:
            return ''
        if (
            'transferencia' in text
            or 'transfier' in text
            or 'cuenta bancaria' in text
            or 'que cuenta' in text
            or 'quÃ© cuenta' in text
        ):
            return 'transferencia_bancaria'
        if 'nequi' in text:
            return 'nequi'
        if 'efectivo' in text:
            return 'efectivo'
        return ''

    @staticmethod
    def _is_uncertain_payment_instructions(instructions: str) -> bool:
        text = (instructions or '').strip().lower()
        if not text:
            return True
        uncertain_tokens = (
            'te compartiremos',
            'te enviaremos',
            'contacta',
            'contacte',
            'soporte',
            'servicio al cliente',
            'asesor',
            'por definir',
            'pendiente',
            'luego',
            'despues',
            'despuÃ©s',
        )
        return any(token in text for token in uncertain_tokens)

    def _resolve_payment_info_handoff_reason(self, *, message_text: str, context: dict) -> str:
        if not self._asked_for_payment_details(message_text):
            return ''

        checkout_data = dict(context.get('checkout_data') or {})
        compact_form = dict(checkout_data.get('compact_checkout_form') or {})
        selected_method = str(
            checkout_data.get('payment_method')
            or compact_form.get('payment_method')
            or ''
        ).strip().lower()
        requested_method = self._infer_requested_payment_method(message_text) or selected_method
        if not requested_method:
            return ''

        methods = [
            item for item in ((context.get('payment_profile') or {}).get('methods') or [])
            if isinstance(item, dict)
        ]
        method_payload = next(
            (
                item for item in methods
                if str(item.get('id') or '').strip().lower() == requested_method
            ),
            {},
        )
        instructions = str(checkout_data.get('payment_instructions') or '').strip()
        if not instructions:
            instructions = str(method_payload.get('instructions') or '').strip()

        if requested_method in {'transferencia_bancaria', 'nequi'}:
            if self._is_uncertain_payment_instructions(instructions):
                return 'missing_or_uncertain_payment_details'
        return ''

    @staticmethod
    def _normalize_field_label(field: str) -> str:
        labels = {
            'full_name': 'nombre completo',
            'phone': 'telefono',
            'payment_method': 'metodo de pago',
            'address_line1': 'direccion',
            'city': 'ciudad',
            'postal_code': 'codigo postal',
            'reference': 'referencia de entrega',
        }
        return labels.get(field, field)

    @staticmethod
    def _is_payment_submission_ping(message_text: str) -> bool:
        text = (message_text or '').strip().lower()
        if not text:
            return False
        keywords = (
            'listo ya',
            'ya pague',
            'ya paguÃ©',
            'pagado',
            'hice la transferencia',
            'ya transferi',
            'ya transferÃ­',
            'envie comprobante',
            'enviÃ© comprobante',
            'ya lo pague',
            'ya lo paguÃ©',
        )
        return any(keyword in text for keyword in keywords)

    def _handle_pending_payment_ping(self, *, message_text: str, context: dict) -> str:
        checkout_data = context.get('checkout_data')
        if not isinstance(checkout_data, dict):
            return ''
        if not str(checkout_data.get('order_id') or '').strip():
            return ''
        if not self._is_payment_submission_ping(message_text):
            return ''

        already_reported = bool(checkout_data.get('payment_reported_by_customer'))
        if not already_reported:
            checkout_data['payment_reported_by_customer'] = True
            checkout_data['payment_reported_at'] = timezone.now().isoformat()
            context['checkout_data'] = checkout_data

        order_number = str(checkout_data.get('order_number') or '').strip()
        order_ref = f' #{order_number}' if order_number else ''
        payment_label = str(checkout_data.get('payment_method_label') or 'el metodo elegido').strip()
        if already_reported:
            return (
                f'Ya tengo registrado tu reporte de pago para el pedido{order_ref}. '
                'Sigue pendiente de validacion manual por parte de la tienda; te avisaremos apenas quede confirmado.'
            )
        return (
            f'Perfecto, ya registre tu reporte de pago para el pedido{order_ref} ({payment_label}). '
            'Ahora queda pendiente de validacion manual por parte de la tienda; te avisaremos cuando este confirmado.'
        )

    def _handle_pre_order_payment_without_cart(self, *, message_text: str, session: SalesSession, context: dict) -> str:
        checkout_data = context.get('checkout_data')
        if not isinstance(checkout_data, dict):
            checkout_data = {}
        if str(checkout_data.get('order_id') or '').strip():
            return ''

        requested_method = self._infer_requested_payment_method(message_text)
        if not requested_method and not self._asked_for_payment_details(message_text):
            return ''

        selected_ids = [str(item) for item in (session.selected_products or []) if str(item).strip()]
        selected_ids.extend([
            str(item) for item in (context.get('selected_product_ids') or [])
            if str(item).strip()
        ])
        has_cart_items = bool(list(dict.fromkeys(selected_ids)))
        if has_cart_items:
            return ''

        return (
            'Ahora mismo tu carrito esta vacio y no puedo continuar al pago. '
            'Primero agrega un producto y luego te ayudo a confirmar el pedido.'
        )

    def _handle_post_order_payment_question(self, *, message_text: str, context: dict, organization) -> tuple[str, bool]:
        checkout_data = context.get('checkout_data')
        if not isinstance(checkout_data, dict):
            return '', False
        if not str(checkout_data.get('order_id') or '').strip():
            return '', False
        if not self._asked_for_payment_details(message_text):
            return '', False

        selected_method = str(checkout_data.get('payment_method') or '').strip().lower()
        inferred_method = self._infer_requested_payment_method(message_text)
        effective_method = inferred_method or selected_method
        if effective_method and effective_method != 'transferencia_bancaria':
            return '', False

        selected_label = str(checkout_data.get('payment_method_label') or 'transferencia bancaria').strip()
        instructions = str(checkout_data.get('payment_instructions') or '').strip()
        if not instructions:
            methods = [
                item for item in ((context.get('payment_profile') or {}).get('methods') or [])
                if isinstance(item, dict)
            ]
            transfer_method = next(
                (
                    item for item in methods
                    if str(item.get('id') or '').strip().lower() == 'transferencia_bancaria'
                ),
                {},
            )
            instructions = str(transfer_method.get('instructions') or '').strip()

        order_number = str(checkout_data.get('order_number') or '').strip()
        order_ref = f' #{order_number}' if order_number else ''
        if instructions:
            return (
                f'Claro. Tu pedido{order_ref} esta con {selected_label}. '
                f'Datos para pagar: {instructions}. '
                'Cuando hagas la transferencia, enviame una captura de pantalla del comprobante y validamos el pago.'
            ), False

        return (
            f'Tu pedido{order_ref} esta por transferencia bancaria, pero no tengo la cuenta configurada ahora mismo. '
            'Te conecto con soporte para compartirte los datos exactos de pago.'
        ), True

    @staticmethod
    def _is_confirmed_order_change_request(message_text: str) -> bool:
        """
        Detects a request to change items/quantities on an ALREADY confirmed
        order (e.g. "en lugar de 1 cuaderno quiero 3", "puedo cambiar mi
        pedido?"). Without this guard the conversational path has no idea an
        Order already exists and will happily narrate a fake re-checkout
        (new quantity, new total, new address) without ever touching the
        real Order record — the customer believes the change went through,
        but the DB still has the original order.
        """
        text = (message_text or '').strip().lower()
        if not text:
            return False
        keywords = (
            'cambiar mi pedido', 'cambiar el pedido', 'modificar mi pedido', 'modificar el pedido',
            'editar mi pedido', 'editar el pedido', 'actualizar mi pedido', 'actualizar el pedido',
            'corregir mi pedido', 'corregir el pedido',
            'agregar a mi pedido', 'agregar al pedido', 'anadir a mi pedido', 'añadir a mi pedido',
            'quitar de mi pedido', 'quitar del pedido', 'eliminar de mi pedido', 'eliminar del pedido',
            'en lugar de', 'en vez de', 'cambiar la cantidad', 'cambiar cantidad',
        )
        return any(keyword in text for keyword in keywords)

    def _handle_post_order_modification_request(self, *, message_text: str, context: dict) -> tuple[str, bool]:
        checkout_data = context.get('checkout_data')
        if not isinstance(checkout_data, dict):
            return '', False
        if not str(checkout_data.get('order_id') or '').strip():
            return '', False
        if not self._is_confirmed_order_change_request(message_text):
            return '', False

        order_number = str(checkout_data.get('order_number') or '').strip()
        order_ref = f' #{order_number}' if order_number else ''
        return (
            f'Tu pedido{order_ref} ya fue confirmado, asi que no puedo modificarlo yo mismo desde el chat. '
            'Le paso tu solicitud a un asesor para que lo ajuste cuanto antes.'
        ), True

    @staticmethod
    def _is_post_order_shipping_question(message_text: str) -> bool:
        text = (message_text or '').strip().lower()
        if not text:
            return False
        keywords = (
            'cuando me llega',
            'cuanto tarda',
            'cuanto demora',
            'cuando lo envian',
            'cuando lo envÃ­an',
            'cuando me lo envian',
            'cuando me lo envÃ­an',
            'fecha de entrega',
            'tiempo de entrega',
            'cuando llega',
            'envio',
            'envÃ­o',
            'despacho',
        )
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _is_urgent_shipping_request(message_text: str) -> bool:
        text = (message_text or '').strip().lower()
        if not text:
            return False
        urgency_tokens = (
            'urgente',
            'ya',
            'hoy',
            'ahora',
            'rapido',
            'rÃ¡pido',
            'de una',
            'asap',
            'cuanto antes',
        )
        return any(token in text for token in urgency_tokens)

    @staticmethod
    def _extract_shipping_kb_answer(kb_text: str) -> str:
        text = str(kb_text or '').strip()
        if not text:
            return ''
        compact = ' '.join(text.replace('**', ' ').split())
        if not compact:
            return ''
        lowered = compact.lower()
        if not any(token in lowered for token in ('envio', 'envÃ­o', 'entrega', 'despacho', 'dias', 'dÃ­as', 'habil', 'hÃ¡bil')):
            return ''
        return compact[:280].rstrip(' .')

    def _handle_post_order_shipping_question(self, *, message_text: str, context: dict, organization) -> tuple[str, bool]:
        checkout_data = context.get('checkout_data')
        if not isinstance(checkout_data, dict):
            return '', False
        if not str(checkout_data.get('order_id') or '').strip():
            return '', False
        if not self._is_post_order_shipping_question(message_text):
            return '', False

        shipping_profile = context.get('shipping_profile') or {}
        avg_days = str(shipping_profile.get('avg_days') or '').strip()
        shipping_policy = str(shipping_profile.get('policy') or '').strip()
        shipping_coverage = str(shipping_profile.get('coverage') or '').strip()
        ships_same_day = bool(shipping_profile.get('ships_same_day'))

        if avg_days:
            dispatch_line = (
                'Tu pedido se despacha hoy mismo.' if ships_same_day
                else 'Tu pedido ya esta en proceso interno de despacho.'
            )
            parts = [f'{dispatch_line} El tiempo estimado de ENTREGA (cuando llega a tu direccion) es de {avg_days}.']
            if shipping_coverage:
                parts.append(f'Cobertura: {shipping_coverage}.')
            if shipping_policy:
                parts.append(shipping_policy)
            return ' '.join(parts).strip(), False

        kb_text = KBService.fetch(
            purposes=['policy', 'faq'],
            organization=organization,
            query=message_text,
            max_articles=2,
        )
        kb_answer = self._extract_shipping_kb_answer(kb_text)
        if kb_answer:
            return (
                f'Segun nuestra politica de envios: {kb_answer}. '
                'Si quieres, reviso tu caso puntual y te confirmo el rango exacto.'
            ), False

        # If we cannot answer with confidence, switch to human urgently.
        if self._is_urgent_shipping_request(message_text):
            return 'Dejame validarlo un momento internamente; te conecto con un asesor para confirmarte el tiempo exacto de entrega.', True

        return 'Dejame validarlo un momento internamente para darte una fecha precisa de entrega.', True

    def _handle_pre_order_checkout_guidance(self, *, message_text: str, session: SalesSession, action: dict, context: dict) -> str:
        checkout_data = dict(context.get('checkout_data') or {})
        if str(checkout_data.get('order_id') or '').strip():
            return ''

        in_checkout = (
            str(session.stage or '') == 'checkout'
            or bool((action or {}).get('checkout_step'))
            or bool(session.selected_products)
        )
        if not in_checkout:
            return ''

        payload = self._build_checkout_compact_payload(context, session=session, action=action) or {}
        if not payload:
            return ''

        awaiting_order_confirmation = bool(checkout_data.get('awaiting_order_confirmation'))
        if awaiting_order_confirmation and not self._is_explicit_order_confirmation(message_text):
            return self._build_order_confirmation_request(context=context, session=session, action=action)

        required_fields = [str(field).strip() for field in (payload.get('required_fields') or []) if str(field).strip()]
        initial_values = payload.get('initial_values') or {}
        missing = [field for field in required_fields if not str((initial_values or {}).get(field) or '').strip()]
        if missing:
            missing_labels = ', '.join(self._normalize_field_label(field) for field in missing[:4])
            # Acknowledge a payment method chosen in this very message so the
            # customer feels heard (account details only come after the order).
            prefix = ''
            method_id = self._infer_requested_payment_method(message_text)
            if method_id:
                method_label = next(
                    (
                        str((option or {}).get('label') or '').strip()
                        for option in (payload.get('payment_options') or [])
                        if str((option or {}).get('id') or '').strip() == method_id
                    ),
                    '',
                ) or method_id.replace('_', ' ')
                prefix = f'Perfecto, dejamos {method_label} como metodo de pago. '
            return (
                f'{prefix}Para crear tu pedido me faltan: {missing_labels}. '
                'Compartelos en el formulario de confirmacion y en el siguiente paso te pido validar el resumen final.'
            )
        return ''

    def _build_order_confirmation_request(self, *, context: dict, session: SalesSession, action: dict) -> str:
        payload = self._build_checkout_compact_payload(context, session=session, action=action) or {}
        cart_items = [item for item in (payload.get('cart_items') or []) if isinstance(item, dict)]
        if not cart_items:
            return 'Antes de crear el pedido, confirmame por favor los datos de envio y el metodo de pago.'

        item_parts = []
        for item in cart_items[:3]:
            title = str(item.get('title') or 'Producto').strip()
            qty = int(item.get('qty') or 1)
            item_parts.append(f'{title} x{qty}')
        items_text = ', '.join(item_parts)

        subtotal = float(payload.get('total') or 0)
        discounted_total = float(payload.get('total_after_discount') or subtotal)
        discount_total = float(payload.get('discount_total') or 0)
        initial_values = payload.get('initial_values') or {}
        selected_payment = str(initial_values.get('payment_method') or '').strip()
        payment_label = ''
        for option in (payload.get('payment_options') or []):
            if str((option or {}).get('id') or '').strip() == selected_payment:
                payment_label = str((option or {}).get('label') or '').strip()
                break
        payment_text = payment_label or 'pendiente por definir'
        pricing_text = f'Total ${int(discounted_total):,} COP.'
        if discount_total > 0:
            pricing_text = (
                f'Subtotal ${int(subtotal):,} COP. '
                f'Descuento ${int(discount_total):,} COP. '
                f'Total ${int(discounted_total):,} COP.'
            )
        return (
            f'Perfecto. Antes de crear tu pedido te resumo: {items_text}. '
            f'{pricing_text} Metodo de pago: {payment_text}. '
            'Â¿Confirmas que cree el pedido ahora?'
        )

    def _is_checkout_submission_complete(self, *, context: dict, session: SalesSession, action: dict) -> bool:
        payload = self._build_checkout_compact_payload(context, session=session, action=action) or {}
        if not payload:
            return False
        required_fields = [str(item).strip() for item in (payload.get('required_fields') or []) if str(item).strip()]
        if not required_fields:
            return True
        initial_values = payload.get('initial_values') or {}
        return all(str((initial_values or {}).get(field) or '').strip() for field in required_fields)

    def _finalize_order_confirmation(
        self,
        *,
        session: SalesSession,
        situation: str,
        action: dict,
        context: dict,
        message_text: str,
        order_result: dict,
    ) -> str:
        checkout_data = context.get('checkout_data') or {}
        checkout_data.pop('awaiting_order_confirmation', None)
        checkout_data.pop('awaiting_order_confirmation_at', None)
        checkout_data['order_id'] = order_result['order_id']
        checkout_data['order_number'] = order_result['order_number']
        checkout_data['order_total'] = order_result['order_total']
        checkout_data['payment_method'] = order_result.get('payment_method') or ''
        checkout_data['payment_method_label'] = order_result.get('payment_method_label') or ''
        checkout_data['payment_instructions'] = order_result.get('payment_instructions') or ''
        checkout_data['order_completed_at'] = timezone.now().isoformat()
        context['checkout_data'] = checkout_data
        context['order_completed'] = True
        self._message_metadata = {}
        self._followup_message = self._build_order_followup_message(order_result=order_result)

        final_action = dict(action)
        final_action.pop('checkout_step', None)
        self._merge_session_signals(
            context=context,
            signals=SessionManager.extract_session_signals(
                user_message=message_text,
                action=final_action,
                context=context,
            ),
        )
        SessionManager.update(
            session=session,
            situation=situation,
            action=final_action,
            context=context,
            reply=order_result['message'],
        )
        return order_result['message']

    def _extract_removed_product_id(self) -> str:
        structured_payload = {}
        message = getattr(self, '_current_message', None)
        if message is not None:
            structured_payload = (getattr(message, 'metadata', None) or {}).get('structured_payload') or {}

        if not isinstance(structured_payload, dict):
            return ''

        interactive = structured_payload.get('interactive') or structured_payload
        if not isinstance(interactive, dict):
            return ''
        if interactive.get('action') != 'remove_cart_item':
            return ''

        return str(interactive.get('product_id') or '').strip()

    def _handle_cart_item_removal(self, *, session: SalesSession, organization) -> dict | None:
        removed_product_id = self._extract_removed_product_id()
        if not removed_product_id:
            return None

        checkout_data = dict(getattr(session, 'checkout_data', {}) or {})
        existing_order_id = str(checkout_data.get('order_id') or '').strip()
        if existing_order_id:
            return {
                'type': 'blocked_after_order',
                'order_id': existing_order_id,
                'order_number': str(checkout_data.get('order_number') or '').strip(),
            }

        selected = [str(item) for item in (session.selected_products or []) if str(item).strip()]
        if not selected:
            return {'type': 'empty_cart_noop'}
        if removed_product_id not in selected:
            return {'type': 'missing_item_noop', 'product_id': removed_product_id}

        next_selected = [item for item in selected if item != removed_product_id]
        attempts = dict(checkout_data.get('retention_attempts') or {})
        prior_attempts = int(attempts.get(removed_product_id, 0) or 0)
        retention_allowed = prior_attempts < 1
        if retention_allowed:
            attempts[removed_product_id] = prior_attempts + 1
        checkout_data['retention_attempts'] = attempts
        checkout_data['last_cart_event'] = {
            'type': 'item_removed',
            'product_id': removed_product_id,
            'retention_allowed': retention_allowed,
            'at': timezone.now().isoformat(),
        }

        session.selected_products = next_selected
        session.checkout_data = checkout_data
        session.save(update_fields=['selected_products', 'checkout_data', 'updated_at'])

        product = CatalogService.get_product_by_id(removed_product_id, organization)
        return {
            'type': 'item_removed',
            'product_id': removed_product_id,
            'removed_product_title': (product or {}).get('title', ''),
            'retention_allowed': retention_allowed,
            'remaining_items_count': len(next_selected),
        }

    def _extract_shipping_form_submission(self) -> dict:
        structured_payload = {}
        message = getattr(self, '_current_message', None)
        if message is not None:
            structured_payload = (getattr(message, 'metadata', None) or {}).get('structured_payload') or {}

        if not isinstance(structured_payload, dict):
            return {}

        interactive = structured_payload.get('interactive') or structured_payload
        if not isinstance(interactive, dict):
            return {}
        if interactive.get('action') != 'submit_shipping_form':
            return {}

        data = interactive.get('data') or {}
        if not isinstance(data, dict):
            return {}

        allowed_keys = {'full_name', 'phone', 'city', 'address_line1', 'address_line2', 'postal_code', 'reference'}
        return {
            key: str(value).strip()
            for key, value in data.items()
            if key in allowed_keys and value is not None and str(value).strip()
        }

    def _extract_compact_checkout_submission(self) -> dict:
        structured_payload = {}
        message = getattr(self, '_current_message', None)
        if message is not None:
            structured_payload = (getattr(message, 'metadata', None) or {}).get('structured_payload') or {}

        if not isinstance(structured_payload, dict):
            return {}

        interactive = structured_payload.get('interactive') or structured_payload
        if not isinstance(interactive, dict):
            return {}
        if interactive.get('action') != 'submit_compact_checkout':
            return {}

        data = interactive.get('data') or {}
        if not isinstance(data, dict):
            return {}

        allowed_keys = {
            'full_name',
            'phone',
            'email',
            'payment_method',
            'city',
            'address_line1',
            'address_line2',
            'postal_code',
            'reference',
        }
        return {
            key: str(value).strip()
            for key, value in data.items()
            if key in allowed_keys and value is not None and str(value).strip()
        }

    def _create_guest_checkout_order(
        self,
        *,
        organization,
        conversation: Conversation,
        session: SalesSession,
        context: dict,
        submission: dict,
    ) -> dict | None:
        try:
            from apps.accounts.models import Contact
            from apps.ecommerce.models import Order, Product
            from apps.ecommerce.promotion_engine import PromotionEngine
        except Exception:
            return None

        selected_ids = [str(item) for item in (session.selected_products or []) if str(item).strip()]
        if not selected_ids:
            selected_ids = [
                str((item or {}).get('id') or '')
                for item in (context.get('recommended_products') or [])
                if (item or {}).get('id')
            ]
        selected_ids = [item for item in selected_ids if item]
        if not selected_ids:
            return None

        products = Product.objects.filter(organization=organization, id__in=selected_ids).prefetch_related('variants')
        product_map = {str(product.id): product for product in products}

        items: list[dict] = []
        total = Decimal('0')
        requires_shipping = False
        for product_id in selected_ids:
            product = product_map.get(product_id)
            if not product:
                continue
            variants = sorted(list(product.variants.all()), key=lambda item: item.price)
            variant = variants[0] if variants else None
            unit_price = Decimal(str(variant.price if variant and variant.price is not None else 0))
            items.append({
                'product_id': str(product.id),
                'sku': variant.sku if variant and variant.sku else f'prd-{str(product.id)[:8]}',
                'qty': 1,
                'unit_price': float(unit_price),
                'title': product.title,
                'offer_type': product.offer_type,
                'category': product.category or '',
            })
            total += unit_price
            requires_shipping = requires_shipping or bool(product.requires_shipping)

        if not items:
            return None

        required_fields = ['full_name', 'phone']
        payment_profile = context.get('payment_profile') or {}
        available_payment_method_ids = [
            str((item or {}).get('id') or '').strip()
            for item in (payment_profile.get('methods') or [])
            if str((item or {}).get('id') or '').strip()
        ]
        if available_payment_method_ids:
            required_fields.append('payment_method')
        shipping_profile = context.get('shipping_profile') or {}
        if requires_shipping:
            required_fields.append('address_line1')
            if shipping_profile.get('require_city', True):
                required_fields.append('city')
            if shipping_profile.get('require_postal_code'):
                required_fields.append('postal_code')
            if shipping_profile.get('require_reference', True):
                required_fields.append('reference')
        if any(not str(submission.get(field, '')).strip() for field in required_fields):
            return None

        selected_payment_method = str(submission.get('payment_method') or '').strip()
        if available_payment_method_ids and selected_payment_method not in available_payment_method_ids:
            return None

        full_name = str(submission.get('full_name') or '').strip() or 'Cliente'
        first_name, _, last_name = full_name.partition(' ')
        email = str(submission.get('email') or '').strip().lower()
        phone = str(submission.get('phone') or '').strip()

        contact_lookup = {}
        if email:
            contact_lookup['email'] = email
        elif phone:
            contact_lookup['telefono'] = phone

        contact_defaults = {
            'nombre': first_name or 'Cliente',
            'apellido': last_name,
            'email': email,
            'telefono': phone,
            'canal': conversation.canal or 'app',
            'tipo': 'cliente',
        }
        if contact_lookup:
            contact, _ = Contact.objects.get_or_create(
                organization=organization,
                defaults=contact_defaults,
                **contact_lookup,
            )
            patch_fields = []
            if not contact.nombre and first_name:
                contact.nombre = first_name
                patch_fields.append('nombre')
            if not contact.apellido and last_name:
                contact.apellido = last_name
                patch_fields.append('apellido')
            if email and not contact.email:
                contact.email = email
                patch_fields.append('email')
            if phone and not contact.telefono:
                contact.telefono = phone
                patch_fields.append('telefono')
            if patch_fields:
                contact.save(update_fields=[*patch_fields, 'updated_at'])
        else:
            contact = Contact.objects.create(organization=organization, **contact_defaults)

        # The conversation may still point at an anonymous placeholder
        # contact created when the widget session started (no email/phone
        # known yet). Re-point it to the identity resolved from checkout so
        # a future conversation from the same phone/email can find this
        # order in CustomerHistoryService.
        if conversation.contact_id != contact.id:
            conversation.contact = contact
            conversation.save(update_fields=['contact', 'updated_at'])

        shipping_data = {
            'full_name': full_name,
            'phone': phone,
            'email': email,
            'address_line1': str(submission.get('address_line1') or '').strip(),
            'address_line2': str(submission.get('address_line2') or '').strip(),
            'city': str(submission.get('city') or '').strip(),
            'postal_code': str(submission.get('postal_code') or '').strip(),
            'reference': str(submission.get('reference') or '').strip(),
        }
        payment_method_payload = next(
            (
                item for item in (payment_profile.get('methods') or [])
                if str((item or {}).get('id') or '').strip() == selected_payment_method
            ),
            None,
        ) or {}
        payment_method_label = str(payment_method_payload.get('label') or selected_payment_method or 'No definido').strip()
        payment_instructions = str(payment_method_payload.get('instructions') or '').strip()

        pricing = PromotionEngine.evaluate_cart(
            organization=organization,
            lines=items,
            shipping_amount=0,
        )
        discounted_total = Decimal(str(pricing.get('total') or total))

        order = Order.objects.create(
            organization=organization,
            contact=contact,
            customer_name=full_name,
            order_kind='purchase',
            channel='app',
            status='new',
            items=items,
            total=discounted_total,
            currency='COP',
            payment_method=selected_payment_method,
            conversation=conversation,
            fulfillment_summary={
                'checkout_source': 'appchat_compact',
                'requires_shipping': requires_shipping,
                'form_submission': {k: v for k, v in submission.items() if v not in (None, '')},
                'shipping': shipping_data,
                'pricing': pricing,
                'payment': {
                    'method': selected_payment_method,
                    'method_label': payment_method_label,
                    'instructions': payment_instructions,
                    'status': 'pending_confirmation',
                },
            },
            notes='Pedido creado desde flujo de checkout compacto en chat.',
        )
        short_order = str(order.id).split('-')[0].upper()
        payment_line = f'Metodo de pago: {payment_method_label}.'
        instruction_line = f' Instrucciones: {payment_instructions}' if payment_instructions else ''
        proof_line = ''
        if selected_payment_method == 'transferencia_bancaria':
            proof_line = ' Cuando hagas la transferencia, enviame una captura de pantalla del comprobante y validamos el pago.'
        return {
            'order_id': str(order.id),
            'order_number': short_order,
            'order_total': float(discounted_total),
            'payment_method': selected_payment_method,
            'payment_method_label': payment_method_label,
            'payment_instructions': payment_instructions,
            'requires_shipping': requires_shipping,
            'message': (
                f'¡Listo! Tu pedido #{short_order} quedo confirmado por ${int(discounted_total):,}. '
                f'Guarda este numero de pedido: te va a servir para preguntarme por el estado de tu compra mas adelante. '
                f'{payment_line}{instruction_line}{proof_line}'
            ),
        }

    @staticmethod
    def _build_order_followup_message(*, order_result: dict) -> str:
        """
        Proactive "what happens next" message sent right after order
        confirmation, as a second chat bubble, so the customer never has to
        ask how to proceed.
        """
        payment_method = str(order_result.get('payment_method') or '')
        requires_shipping = bool(order_result.get('requires_shipping'))

        if payment_method == 'efectivo':
            action_line = 'Como pagas contra entrega, no tienes que hacer nada mas por ahora.'
        elif payment_method == 'transferencia_bancaria':
            action_line = 'Apenas recibamos tu comprobante, confirmamos el pago y alistamos tu pedido.'
        elif payment_method == 'nequi':
            action_line = 'Apenas quede reflejado el pago por Nequi, alistamos tu pedido.'
        else:
            action_line = 'Ya quedo registrado tu pedido y seguimos con el alistamiento.'

        next_line = (
            'Te escribo por aqui para coordinar la entrega y contarte tiempos.'
            if requires_shipping
            else 'Te escribo por aqui apenas este listo.'
        )

        return f'{action_line} {next_line} Si tienes alguna duda mientras tanto, aqui estoy.'

    def _build_catalog_query(self, *, current_message: str, user_messages: list[str]) -> str:
        relevant_keywords = (
            'quiero', 'busco', 'necesito', 'me interesa', 'top', 'legging', 'camiseta',
            'chaqueta', 'guantes', 'oxÃƒÂ­metro', 'oximetro', 'negro', 'negra', 'blanco',
            'blanca', 'rojo', 'roja', 'azul', 'verde', 'arena', 'beige', 'formal',
            'casual', 'deportivo', 'sport', 'algodÃƒÂ³n', 'algodon', 'lino',
        )
        noisy_keywords = ('envÃƒÂ­o', 'envio', 'entrega', 'lima', 'bogotÃƒÂ¡', 'bogota', 'medellÃƒÂ­n', 'medellin')

        relevant = []
        for text in user_messages + [current_message]:
            lowered = text.lower()
            if any(keyword in lowered for keyword in noisy_keywords) and not any(
                keyword in lowered for keyword in relevant_keywords
            ):
                continue
            relevant.append(text.strip())

        if not relevant:
            return current_message

        return ' '.join(relevant[-3:])

    def _load_shipping_profile(self, organization) -> dict:
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
            shipping = (settings_payload.get('org_profile') or {}).get('shipping_profile') or {}
            if not isinstance(shipping, dict):
                return {}
            return {
                'country_code': (shipping.get('country_code') or 'CO'),
                'city_label': (shipping.get('city_label') or 'Ciudad'),
                'require_city': shipping.get('require_city', True) is not False,
                'require_postal_code': bool(shipping.get('require_postal_code', False)),
                'require_reference': shipping.get('require_reference', True) is not False,
                'blocked_zones': shipping.get('blocked_zones') or [],
                'address_example': shipping.get('address_example') or 'Ej: Calle 10 # 23-45, Apto 302',
                'avg_days': (settings_payload.get('sales_agent') or {}).get('shipping_avg_days') or '',
                'policy': (settings_payload.get('sales_agent') or {}).get('shipping_policy') or '',
                'coverage': (settings_payload.get('sales_agent') or {}).get('shipping_coverage') or '',
                'ships_same_day': bool((settings_payload.get('sales_agent') or {}).get('ships_same_day', False)),
            }
        except Exception:
            return {}

    def _load_payment_profile(self, organization) -> dict:
        try:
            from apps.channels_config.models import ChannelConfig
            from apps.channels_config.settings_schema import normalise_settings

            config = (
                ChannelConfig.objects
                .filter(organization=organization, channel='onboarding')
                .only('settings')
                .first()
            )
            raw_settings = (config.settings or {}) if config else {}
            normalized = normalise_settings(raw_settings)

            raw_methods = raw_settings.get('payment_methods') or []
            org_methods = ((normalized.get('org_profile') or {}).get('payment_methods') or [])
            methods = []
            for value in [*raw_methods, *org_methods]:
                cleaned = str(value or '').strip().lower()
                if cleaned:
                    methods.append(cleaned)
            methods = list(dict.fromkeys(methods))

            payment_settings = dict(raw_settings.get('payment_settings') or {})
            bank_enabled = payment_settings.get('bank_transfer_enabled', True) is not False
            cash_enabled = payment_settings.get('cash_enabled', True) is not False
            nequi_enabled = payment_settings.get('nequi_enabled', True) is not False

            bank_name = str(payment_settings.get('bank_name') or '').strip()
            account_type = str(payment_settings.get('account_type') or '').strip()
            account_number = str(payment_settings.get('account_number') or '').strip()
            account_holder = str(payment_settings.get('account_holder') or '').strip()
            payment_reference_note = str(payment_settings.get('payment_reference_note') or '').strip()
            cash_instructions = str(payment_settings.get('cash_instructions') or '').strip()
            nequi_number = str(payment_settings.get('nequi_number') or '').strip()
            nequi_holder = str(payment_settings.get('nequi_holder') or '').strip()
            nequi_note = str(payment_settings.get('nequi_note') or '').strip()

            options = []
            if any(item in methods for item in ('nequi',)):
                # Require real account details — a method listed as "active" with no
                # configured data must never be offered to a customer as payable.
                if nequi_enabled and nequi_number and nequi_holder:
                    instructions_parts = []
                    if nequi_number:
                        instructions_parts.append(f'Numero: {nequi_number}')
                    if nequi_holder:
                        instructions_parts.append(f'Titular: {nequi_holder}')
                    if nequi_note:
                        instructions_parts.append(nequi_note)
                    elif payment_reference_note:
                        instructions_parts.append(payment_reference_note)
                    options.append({
                        'id': 'nequi',
                        'label': 'Nequi',
                        'description': 'Pago inmediato por Nequi.',
                        'instructions': '. '.join(instructions_parts).strip('. '),
                    })

            if any(item in methods for item in ('transferencia bancaria', 'transferencia', 'bancaria')):
                if bank_enabled and bank_name and account_number and account_holder:
                    instructions_parts = []
                    if bank_name:
                        instructions_parts.append(f'Banco: {bank_name}')
                    if account_type:
                        instructions_parts.append(f'Tipo: {account_type}')
                    if account_number:
                        instructions_parts.append(f'Cuenta: {account_number}')
                    if account_holder:
                        instructions_parts.append(f'Titular: {account_holder}')
                    if payment_reference_note:
                        instructions_parts.append(payment_reference_note)
                    options.append({
                        'id': 'transferencia_bancaria',
                        'label': 'Transferencia bancaria',
                        'description': 'Transferencia a cuenta bancaria.',
                        'instructions': '. '.join(instructions_parts).strip('. '),
                    })

            if any(item in methods for item in ('efectivo', 'cash')):
                if cash_enabled and cash_instructions:
                    options.append({
                        'id': 'efectivo',
                        'label': 'Efectivo',
                        'description': 'Pago contra entrega o en punto fisico.',
                        'instructions': cash_instructions,
                    })

            return {'methods': options}
        except Exception:
            # No configured payment methods is a valid, safe state — never fabricate
            # methods the org hasn't actually set up.
            return {'methods': []}

    def _build_cart_snapshot(self, *, session: SalesSession, organization) -> dict:
        """Current cart state (post-mutation) for client-side cart widgets."""
        items = []
        total = 0.0
        selected_ids = [str(item) for item in (session.selected_products or []) if str(item).strip()]
        for product_id in selected_ids[:5]:
            product = CatalogService.get_product_by_id(product_id, organization)
            if not product:
                continue
            price = float(product.get('price_min') or 0)
            total += price
            items.append({
                'product_id': product_id,
                'title': product.get('title', ''),
                'qty': 1,
                'unit_price': price,
                'subtotal': price,
                'currency': 'COP',
            })
        return {'cart_items': items, 'total': total, 'currency': 'COP'}

    def _attach_cart_snapshot(self, *, session: SalesSession, organization) -> None:
        """Attach the fresh cart state to the outgoing message metadata."""
        snapshot = self._build_cart_snapshot(session=session, organization=organization)
        metadata = dict(self._message_metadata or {})
        ui_payload = metadata.get('ui_payload')
        if isinstance(ui_payload, dict):
            ui_payload = dict(ui_payload)
            ui_payload['cart_snapshot'] = snapshot
            metadata['ui_payload'] = ui_payload
        else:
            metadata['ui_payload'] = {'type': 'cart_update', **snapshot}
        self._message_metadata = metadata

    def _build_message_metadata(self, context: dict, *, session: SalesSession, action: dict) -> dict:
        checkout_compact_payload = self._build_checkout_compact_payload(context, session=session, action=action)
        shipping_form_payload = self._build_shipping_form_payload(context, session=session, action=action)
        products = context.get('recommended_products') or []
        if not products and not shipping_form_payload and not checkout_compact_payload:
            return {}

        resolution = context.get('product_resolution') or {}
        title = 'Productos sugeridos'
        if resolution.get('needs_confirmation'):
            title = 'Ã‚Â¿CuÃƒÂ¡l de estas opciones buscas?'
        elif resolution.get('match_type') == 'browse':
            title = 'Productos disponibles'

        cards = []
        card_ids = []
        if self._should_show_product_cards(context=context, session=session, action=action, products=products):
            seen_ids = set()
            for product in products[:3]:
                product_id = product.get('id')
                if not product_id or product_id in seen_ids:
                    continue

                seen_ids.add(product_id)
                card_ids.append(str(product_id))
                cards.append({
                    'id': product_id,
                    'title': product.get('title', ''),
                    'brand': product.get('brand', ''),
                    'category': product.get('category', ''),
                    'image_url': product.get('image_url', ''),
                    'price_min': product.get('price_min'),
                    'price_max': product.get('price_max'),
                    'price_type': product.get('price_type', ''),
                    'availability_label': product.get('availability_label', ''),
                    'is_available': bool(product.get('is_available')),
                    'cta_label': 'Seleccionar',
                    'selection_message': f"Me interesa {product.get('title', '').strip()}",
                    'selection_payload': {
                        'interactive': {
                            'action': 'select_product',
                            'product_id': product_id,
                        }
                    },
                })

        if card_ids:
            checkout_data = context.get('checkout_data') or {}
            checkout_data['last_products_shown_ids'] = card_ids
            checkout_data['last_products_shown_turn'] = int(session.message_count or 0)
            context['checkout_data'] = checkout_data

        if checkout_compact_payload:
            return {'ui_payload': checkout_compact_payload}
        if shipping_form_payload:
            return {'ui_payload': shipping_form_payload}
        if cards:
            return {
                'ui_payload': {
                    'type': 'product_list',
                    'layout': 'cards',
                    'title': title,
                    'products': cards,
                }
            }
        return {'ui_payload': shipping_form_payload} if shipping_form_payload else {}

    def _should_show_product_cards(self, *, context: dict, session: SalesSession, action: dict, products: list[dict]) -> bool:
        if not products:
            return False
        forcing_considering = context.get('force_stage') == 'considering'
        if not forcing_considering and (session.stage == 'checkout' or action.get('checkout_step')):
            return False

        message_text = str(getattr(self._current_message, 'content', '') or '').strip().lower()
        resolution = context.get('product_resolution') or {}
        cart_event = context.get('cart_event') or {}
        explicit_browse = self._is_explicit_product_browse(message_text)
        needs_confirmation = bool(resolution.get('needs_confirmation'))
        replacement_flow = cart_event.get('type') == 'item_removed'
        low_signal_followup = self._is_low_signal_followup(message_text)
        product_seeking_message = self._is_product_seeking_message(message_text)

        if low_signal_followup and not explicit_browse and not needs_confirmation and not replacement_flow:
            return False

        if explicit_browse or needs_confirmation or replacement_flow:
            return True

        checkout_data = dict(session.checkout_data or {})
        previous_ids = [str(item) for item in (checkout_data.get('last_products_shown_ids') or []) if str(item).strip()]
        current_ids = [str((item or {}).get('id') or '').strip() for item in products[:3] if str((item or {}).get('id') or '').strip()]
        same_cards = bool(previous_ids) and current_ids == previous_ids

        last_turn = int(checkout_data.get('last_products_shown_turn') or -99)
        current_turn = int(session.message_count or 0)
        within_cooldown = (current_turn - last_turn) < 3

        if within_cooldown:
            return False

        # If user is already considering selected products and did not ask for options, avoid noisy repeats.
        has_selected = bool(session.selected_products or context.get('selected_product_ids'))
        if has_selected and not action.get('fetch_products'):
            return False

        if has_selected and not explicit_browse and same_cards:
            return False

        if not product_seeking_message:
            return False

        return bool(action.get('fetch_products') or resolution.get('match_type') in {'browse', 'category'})

    @staticmethod
    def _is_explicit_product_browse(message_text: str) -> bool:
        if not message_text:
            return False
        keywords = [
            'que tienes',
            'quÃƒÂ© tienes',
            'catalogo',
            'catÃƒÂ¡logo',
            'muestrame',
            'muÃƒÂ©strame',
            'mostrar productos',
            'ver opciones',
            'otras opciones',
            'otro producto',
            'otros productos',
            'similares',
            'similar',
            'parecido',
            'parecidos',
            'ver productos',
            'productos disponibles',
        ]
        return any(keyword in message_text for keyword in keywords)

    @staticmethod
    def _is_low_signal_followup(message_text: str) -> bool:
        text = (message_text or '').strip().lower()
        if not text:
            return True
        if len(text) <= 2:
            return True
        low_signal_phrases = {
            'ok', 'oki', 'okey', 'dale', 'listo', 'perfecto',
            'gracias', 'muchas gracias', 'genial', 'super', 'sÃƒÂºper',
            'si', 'sÃƒÂ­', 'no', 'aja', 'ajÃƒÂ¡', 'vale',
        }
        return text in low_signal_phrases

    @staticmethod
    def _is_product_seeking_message(message_text: str) -> bool:
        text = (message_text or '').strip().lower()
        if not text:
            return False
        keywords = [
            'quiero', 'busco', 'necesito', 'me interesa', 'tienes', 'tienen',
            'comprar', 'comprarlo', 'comprarla', 'comprarlo',
            'producto', 'productos', 'catalogo', 'catÃƒÂ¡logo', 'opciones',
            'precio', 'cuanto', 'cuÃƒÂ¡nto', 'disponible', 'stock',
            'talla', 'color', 'modelo', 'referencia', 'agregar', 'carrito',
            'ver otro', 'otra opcion', 'otra opciÃƒÂ³n',
        ]
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _is_checkout_trigger_message(message_text: str) -> bool:
        text = (message_text or '').strip().lower()
        if not text:
            return False
        keywords = (
            'comprar',
            'comprarlo',
            'comprarla',
            'pagar',
            'pago',
            'checkout',
            'pedido',
            'confirmo',
            'confirmar pedido',
            'transferencia',
            'nequi',
            'efectivo',
        )
        return any(keyword in text for keyword in keywords)

    def _build_checkout_compact_payload(self, context: dict, *, session: SalesSession, action: dict) -> dict | None:
        if context.get('force_stage') == 'considering':
            return None
        selected_ids = [str(item) for item in (session.selected_products or []) if str(item).strip()]
        selected_ids.extend([
            str(item) for item in (context.get('selected_product_ids') or [])
            if str(item).strip()
        ])
        selected_ids = list(dict.fromkeys(selected_ids))

        current_message = str(getattr(self._current_message, 'content', '') or '').strip()
        incoming_checkout = context.get('checkout_data') or {}
        compact_seed = isinstance(incoming_checkout, dict) and bool(
            (incoming_checkout.get('compact_checkout_form') or {})
        )
        in_checkout_mode = bool(session.stage == 'checkout' or action.get('checkout_step'))
        should_soft_open_checkout = bool(
            selected_ids
            and (
                compact_seed
                or self._is_checkout_trigger_message(current_message)
            )
        )
        if not in_checkout_mode and not should_soft_open_checkout:
            return None

        current_checkout = dict(getattr(session, 'checkout_data', {}) or {})
        if incoming_checkout:
            current_checkout.update(incoming_checkout)
        if current_checkout.get('order_id'):
            return None

        products_map = {
            str((product or {}).get('id') or ''): product
            for product in (context.get('recommended_products') or [])
            if (product or {}).get('id')
        }
        products = [products_map.get(product_id) for product_id in selected_ids]
        products = [product for product in products if product]
        if not products and selected_ids:
            products = [
                CatalogService.get_product_by_id(product_id, session.organization)
                for product_id in selected_ids[:5]
            ]
            products = [product for product in products if product]

        shipping_profile = context.get('shipping_profile') or {}
        if not shipping_profile:
            shipping_profile = {
                'country_code': 'CO',
                'city_label': 'Ciudad',
                'require_city': True,
                'require_postal_code': False,
                'require_reference': True,
                'blocked_zones': [],
                'address_example': 'Ej: Calle 10 # 23-45, Apto 302',
            }

        compact_form = current_checkout.get('compact_checkout_form') or {}
        if not isinstance(compact_form, dict):
            compact_form = {}
        selected_payment_method = str(compact_form.get('payment_method') or '').strip()
        payment_profile = context.get('payment_profile') or {}
        payment_options = [item for item in (payment_profile.get('methods') or []) if isinstance(item, dict)]
        payment_option_ids = [str((item or {}).get('id') or '').strip() for item in payment_options if str((item or {}).get('id') or '').strip()]

        cart_items = []
        total = 0.0
        requires_shipping = False
        for product in products[:5]:
            price = float(product.get('price_min') or 0)
            total += price
            requires_shipping = requires_shipping or bool(product.get('requires_shipping'))
            cart_items.append({
                'product_id': str(product.get('id') or ''),
                'title': product.get('title', ''),
                'qty': 1,
                'unit_price': price,
                'subtotal': price,
                'currency': 'COP',
            })

        if not cart_items:
            return None

        discount_total = 0.0
        total_after_discount = total
        applied_promotions = []
        try:
            from apps.ecommerce.promotion_engine import PromotionEngine

            pricing = PromotionEngine.evaluate_cart(
                organization=session.organization,
                lines=[
                    {
                        'product_id': item.get('product_id'),
                        'qty': item.get('qty'),
                        'unit_price': item.get('unit_price'),
                        'category': next(
                            (
                                str(product.get('category') or '')
                                for product in products
                                if str(product.get('id') or '') == str(item.get('product_id') or '')
                            ),
                            '',
                        ),
                    }
                    for item in cart_items
                ],
                shipping_amount=0,
            )
            discount_total = float(pricing.get('discount_total') or 0)
            total_after_discount = float(pricing.get('total') or total)
            applied_promotions = [item for item in (pricing.get('applied_promotions') or []) if isinstance(item, dict)]
        except Exception:
            discount_total = 0.0
            total_after_discount = total
            applied_promotions = []

        fields = [
            {'key': 'full_name', 'label': 'Nombre completo', 'required': True, 'placeholder': 'Nombre y apellido', 'input_type': 'text'},
            {'key': 'phone', 'label': 'Telefono', 'required': True, 'placeholder': 'Ej: +57 300 000 0000', 'input_type': 'tel'},
            {'key': 'email', 'label': 'Email (opcional)', 'required': False, 'placeholder': 'tu@email.com', 'input_type': 'email'},
        ]
        required_fields = ['full_name', 'phone']
        if payment_option_ids:
            required_fields.append('payment_method')
            if not selected_payment_method:
                selected_payment_method = payment_option_ids[0]
            compact_form['payment_method'] = selected_payment_method

        if requires_shipping:
            fields.append({
                'key': 'address_line1',
                'label': 'Direccion',
                'required': True,
                'placeholder': shipping_profile.get('address_example') or 'Direccion principal',
                'input_type': 'text',
            })
            required_fields.append('address_line1')
            if shipping_profile.get('require_city', True):
                fields.append({
                    'key': 'city',
                    'label': shipping_profile.get('city_label') or 'Ciudad',
                    'required': True,
                    'placeholder': 'Ciudad de entrega',
                    'input_type': 'text',
                })
                required_fields.append('city')
            fields.append({'key': 'address_line2', 'label': 'Complemento', 'required': False, 'placeholder': 'Apto, torre, interior (opcional)', 'input_type': 'text'})
            if shipping_profile.get('require_postal_code'):
                fields.append({'key': 'postal_code', 'label': 'Codigo postal', 'required': True, 'placeholder': 'Codigo postal', 'input_type': 'text'})
                required_fields.append('postal_code')
            if shipping_profile.get('require_reference', True):
                fields.append({'key': 'reference', 'label': 'Referencia', 'required': True, 'placeholder': 'Punto de referencia', 'input_type': 'text'})
                required_fields.append('reference')

        return {
            'type': 'checkout_compact',
            'title': 'Confirma tu pedido',
            'submit_label': 'Confirmar pedido',
            'currency': 'COP',
            'cart_items': cart_items,
            'total': round(total, 2),
            'discount_total': round(discount_total, 2),
            'total_after_discount': round(total_after_discount, 2),
            'applied_promotions': applied_promotions[:3],
            'country_code': shipping_profile.get('country_code') or 'CO',
            'blocked_zones': shipping_profile.get('blocked_zones') or [],
            'fields': fields,
            'initial_values': compact_form,
            'required_fields': required_fields,
            'payment_options': payment_options,
        }

    def _build_shipping_form_payload(self, context: dict, *, session: SalesSession, action: dict) -> dict | None:
        if context.get('force_stage') == 'considering':
            return None
        if session.stage != 'checkout' and not action.get('checkout_step'):
            return None

        products = context.get('recommended_products') or []
        if not products:
            return None
        if products and not any(bool(product.get('requires_shipping')) for product in products):
            return None

        shipping_profile = context.get('shipping_profile') or {}
        if not shipping_profile:
            shipping_profile = {
                'country_code': 'CO',
                'city_label': 'Ciudad',
                'require_city': True,
                'require_postal_code': False,
                'require_reference': True,
                'blocked_zones': [],
                'address_example': 'Ej: Calle 10 # 23-45, Apto 302',
            }

        current_checkout = dict(session.checkout_data or {})
        incoming_checkout = context.get('checkout_data') or {}
        if incoming_checkout:
            current_checkout.update(incoming_checkout)
        shipping_form = dict(current_checkout.get('shipping_form') or {})

        required_fields = ['full_name', 'phone', 'address_line1']
        if shipping_profile.get('require_city', True):
            required_fields.append('city')
        if shipping_profile.get('require_postal_code'):
            required_fields.append('postal_code')
        if shipping_profile.get('require_reference', True):
            required_fields.append('reference')

        is_complete = all(str(shipping_form.get(field, '')).strip() for field in required_fields)
        if is_complete:
            return None

        fields = [
            {'key': 'full_name', 'label': 'Nombre completo', 'required': True, 'placeholder': 'Nombre y apellido', 'input_type': 'text'},
            {'key': 'phone', 'label': 'Telefono', 'required': True, 'placeholder': 'Ej: +57 300 000 0000', 'input_type': 'tel'},
            {'key': 'address_line1', 'label': 'Direccion', 'required': True, 'placeholder': shipping_profile.get('address_example') or 'Direccion principal', 'input_type': 'text'},
        ]
        if shipping_profile.get('require_city', True):
            fields.append({'key': 'city', 'label': shipping_profile.get('city_label') or 'Ciudad', 'required': True, 'placeholder': 'Ciudad de entrega', 'input_type': 'text'})
        fields.append({'key': 'address_line2', 'label': 'Complemento', 'required': False, 'placeholder': 'Apto, torre, interior (opcional)', 'input_type': 'text'})
        if shipping_profile.get('require_postal_code'):
            fields.append({'key': 'postal_code', 'label': 'Codigo postal', 'required': True, 'placeholder': 'Codigo postal', 'input_type': 'text'})
        if shipping_profile.get('require_reference', True):
            fields.append({'key': 'reference', 'label': 'Referencia', 'required': True, 'placeholder': 'Punto de referencia', 'input_type': 'text'})

        return {
            'type': 'checkout_shipping_form',
            'title': 'Completa tus datos de envio',
            'submit_label': 'Enviar datos',
            'country_code': shipping_profile.get('country_code') or 'CO',
            'blocked_zones': shipping_profile.get('blocked_zones') or [],
            'fields': fields,
            'initial_values': shipping_form,
            'required_fields': required_fields,
        }

    def _apply_policy_guards(
        self,
        *,
        action: dict,
        session: SalesSession,
        context: dict,
        situation: str,
        shipping_submission: dict,
        checkout_submission: dict,
    ) -> dict:
        selected_ids = [str(item) for item in (session.selected_products or []) if str(item).strip()]
        selected_ids.extend([
            str(item) for item in (context.get('selected_product_ids') or [])
            if str(item).strip()
        ])
        has_selected_products = bool(selected_ids)

        policy = SalesPolicyEngine.enforce(
            action=action,
            session_stage=str(session.stage or ''),
            situation=str(situation or ''),
            has_selected_products=has_selected_products,
            has_shipping_submission=bool(shipping_submission),
            has_checkout_submission=bool(checkout_submission),
        )
        forced_stage = str(policy.get('force_stage') or '').strip()
        if forced_stage:
            context['force_stage'] = forced_stage
        return dict(policy.get('action') or action)

    @staticmethod
    def _merge_session_signals(*, context: dict, signals: dict) -> None:
        if not signals:
            return

        signal_checkout = signals.get('checkout_data')
        if isinstance(signal_checkout, dict):
            existing_checkout = context.get('checkout_data')
            if isinstance(existing_checkout, dict):
                merged_checkout = dict(existing_checkout)
                merged_checkout.update(signal_checkout)
                context['checkout_data'] = merged_checkout
            elif signal_checkout:
                context['checkout_data'] = dict(signal_checkout)

        for key, value in signals.items():
            if key == 'checkout_data':
                continue
            context[key] = value

    def _safe_fallback(self) -> str:
        """
        Return safe fallback when execution fails.

        Returns:
            Safe generic reply
        """
        return 'Te ayudo con gusto. Ã‚Â¿Buscas productos, precio o completar una compra?'
