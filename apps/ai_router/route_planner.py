from __future__ import annotations

import re

from .decision_object import RouterDecision
from .model_selector import ModelSelector
from .schemas import (
    Channel,
    IntentClassification,
    IntentName,
    NormalizedEvent,
    PolicyDecision,
    PolicyStatus,
    PostAction,
    RiskAssessment,
    RouteType,
)


class RoutePlanner:
    def __init__(self, model_selector: ModelSelector | None = None) -> None:
        self.model_selector = model_selector or ModelSelector()

    def plan(
        self,
        event: NormalizedEvent,
        risk: RiskAssessment,
        intent: IntentClassification,
        policy: PolicyDecision,
    ) -> RouterDecision:
        route, target, agent, final_action, post_actions = self._plan_route(event, intent, risk, policy)
        effective_intent = intent.custom_intent_name or intent.intent.value
        model_selection = self.model_selector.select_for_route(
            tenant_id=event.tenant_id,
            intent_name=effective_intent,
            route_name=route.value,
        )
        return RouterDecision.from_components(
            tenant_id=event.tenant_id,
            conversation_id=event.conversation_id,
            intent=effective_intent,
            confidence=intent.confidence,
            entities=intent.entities,
            sentiment=intent.sentiment.value,
            urgency=intent.urgency.value,
            risk=risk,
            policy=policy,
            route=route,
            target=target,
            agent=agent,
            model_selection=model_selection,
            final_action=final_action,
            fallback_route=RouteType.REQUEST_CLARIFICATION.value,
            post_actions=[action.to_dict() for action in post_actions],
        )

    def _plan_route(
        self,
        event: NormalizedEvent,
        intent: IntentClassification,
        risk: RiskAssessment,
        policy: PolicyDecision,
    ) -> tuple[RouteType, str | None, str | None, str, list[PostAction]]:
        active_ai_agent = self._active_ai_agent(event)
        # ── Org custom intents: look up matching DB flow ──────────────────────
        if intent.custom_intent_name:
            return (
                RouteType.TRIGGER_FLOW,
                intent.custom_intent_name,
                None,
                'start_flow',
                [],
            )

        # ── Security: always block first ──────────────────────────────────────
        if policy.status == PolicyStatus.BLOCKED or intent.intent == IntentName.PROMPT_INJECTION_ATTEMPT:
            return (
                RouteType.BLOCK_ACTION,
                'security_review',
                None,
                'block_request',
                [],
            )

        # ── Institutional flows ───────────────────────────────────────────────
        if intent.intent == IntentName.CHECK_SUBSIDY:
            return (
                RouteType.TRIGGER_FLOW,
                'subsidy_consultation_flow',
                None,
                'start_flow',
                [],
            )

        if intent.intent == IntentName.REQUEST_CERTIFICATE:
            return (
                RouteType.TRIGGER_FLOW,
                'certificate_request_flow',
                None,
                'start_flow',
                [],
            )

        if intent.intent == IntentName.BOOK_APPOINTMENT:
            return (
                RouteType.TRIGGER_FLOW,
                'appointment_booking_flow',
                None,
                'start_flow',
                [],
            )

        sales_enabled = self._sales_enabled(event)

        # ── E-commerce: product/price/buy inquiries → sales agent ─────────────
        if intent.intent in (IntentName.BUY_INTENT, IntentName.PRICE_INQUIRY, IntentName.PRODUCT_INQUIRY):
            if sales_enabled:
                return (
                    RouteType.ROUTE_TO_SALES_AGENT,
                    None,
                    'sales_agent',
                    'run_sales_agent',
                    self._stock_check_actions(event, intent),
                )
            return (
                RouteType.DIRECT_AI_REPLY,
                None,
                None,
                'generate_direct_reply',
                [],
            )

        # ── E-commerce: order status and returns ──────────────────────────────
        if intent.intent in (IntentName.ORDER_STATUS, IntentName.RETURN_REQUEST):
            return (
                RouteType.DIRECT_AI_REPLY,
                None,
                None,
                'generate_direct_reply',
                [],
            )

        # ── General FAQ ────────────────────────────────────────────────────────
        if intent.intent == IntentName.GENERAL_FAQ:
            # Mid-sale follow-up questions stay with the sales agent so the
            # conversation (and its session state) doesn't lose the seller.
            if sales_enabled and active_ai_agent == 'sales':
                return (
                    RouteType.ROUTE_TO_SALES_AGENT,
                    None,
                    'sales_agent',
                    'run_sales_agent',
                    [],
                )
            return (
                RouteType.DIRECT_AI_REPLY,
                None,
                None,
                'generate_direct_reply',
                [],
            )

        # ── Human escalation when risk says so ────────────────────────────────
        if risk.require_human_review:
            return (
                RouteType.ESCALATE_TO_HUMAN,
                'human_support_queue',
                None,
                'escalate_to_human',
                [],
            )

        if intent.intent == IntentName.UNKNOWN and event.channel in (Channel.WEB, Channel.APP):
            # In owned digital channels the sales agent IS the storefront:
            # greetings and ambiguous messages open the sale, never a
            # clarification dead-end.
            if sales_enabled:
                return (
                    RouteType.ROUTE_TO_SALES_AGENT,
                    None,
                    'sales_agent',
                    'run_sales_agent',
                    [],
                )
            return (
                RouteType.REQUEST_CLARIFICATION,
                None,
                None,
                'request_more_context',
                [],
            )

        return (
            RouteType.REQUEST_CLARIFICATION,
            None,
            None,
            'request_more_context',
            [],
        )

    @staticmethod
    def _sales_enabled(event: NormalizedEvent) -> bool:
        metadata = getattr(event, 'metadata', None) or {}
        capabilities = metadata.get('agent_capabilities') or {}
        return bool(capabilities.get('sales_enabled', True))

    @staticmethod
    def _stock_check_actions(event: NormalizedEvent, intent: IntentClassification) -> list[PostAction]:
        """Bulk/availability buy intents get a stock-check task for operations."""
        if intent.intent != IntentName.BUY_INTENT:
            return []
        text = (event.message_text or '').lower()
        mentions_quantity = bool(re.search(r'\b\d+\s*(unidades|unidad|units|unit|uds|piezas)\b', text))
        mentions_availability = any(
            token in text
            for token in ('disponibilidad', 'disponible', 'availability', 'in stock', 'stock', 'inventario')
        )
        if not mentions_quantity and not mentions_availability:
            return []
        return [
            PostAction(
                action_type='create_task',
                target='operations_agent',
                payload={
                    'task': 'stock_check',
                    'message_excerpt': (event.message_text or '')[:200],
                },
            )
        ]

    def _active_ai_agent(self, event: NormalizedEvent) -> str | None:
        metadata = getattr(event, 'metadata', None) or {}
        active_agent = metadata.get('active_ai_agent')
        if active_agent in {'general', 'sales', 'marketing', 'operations'}:
            return active_agent
        return None
