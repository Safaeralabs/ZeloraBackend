from __future__ import annotations

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
        capabilities = self._agent_capabilities(event)
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

        # ── E-commerce: sales agent ───────────────────────────────────────────
        if intent.intent in (IntentName.BUY_INTENT, IntentName.PRICE_INQUIRY, IntentName.PRODUCT_INQUIRY):
            post = []
            if intent.intent == IntentName.BUY_INTENT:
                post = [
                    PostAction(
                        action_type='create_task',
                        target='operations_agent',
                        payload={'task_type': 'stock_check', 'priority': 'high'},
                    )
                ]
            if not capabilities['sales_enabled']:
                return (
                    RouteType.DIRECT_AI_REPLY,
                    None,
                    None,
                    'generate_direct_reply',
                    [],
                )
            return (
                RouteType.ROUTE_TO_SALES_AGENT,
                'sales_pipeline',
                'sales_agent',
                'handoff_to_sales_agent',
                post,
            )

        # ── E-commerce: operations agent ──────────────────────────────────────
        if intent.intent in (IntentName.ORDER_STATUS, IntentName.RETURN_REQUEST):
            urgency = 'high' if intent.intent == IntentName.RETURN_REQUEST else 'normal'
            return (
                RouteType.ROUTE_TO_OPERATIONS_AGENT,
                'operations_pipeline',
                'operations_agent',
                'handoff_to_operations_agent',
                [
                    PostAction(
                        action_type='create_task',
                        target='operations_agent',
                        payload={
                            'task_type': 'order_lookup' if intent.intent == IntentName.ORDER_STATUS else 'return_processing',
                            'priority': urgency,
                            'entities': intent.entities,
                        },
                    )
                ],
            )

        # ── General FAQ: direct AI reply ──────────────────────────────────────
        if intent.intent == IntentName.GENERAL_FAQ:
            if intent.recommended_action == 'route_to_operations_agent':
                return (
                    RouteType.ROUTE_TO_OPERATIONS_AGENT,
                    'operations_pipeline',
                    'operations_agent',
                    'handoff_to_operations_agent',
                    [],
                )
            if active_ai_agent == 'sales' and capabilities['sales_enabled']:
                return (
                    RouteType.ROUTE_TO_SALES_AGENT,
                    'sales_pipeline',
                    'sales_agent',
                    'continue_with_sales_agent',
                    [],
                )
            if capabilities['sales_enabled']:
                return (
                    RouteType.ROUTE_TO_SALES_AGENT,
                    'sales_pipeline',
                    'sales_agent',
                    'handoff_to_sales_agent',
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
            if active_ai_agent == 'sales' and capabilities['sales_enabled']:
                return (
                    RouteType.ROUTE_TO_SALES_AGENT,
                    'sales_pipeline',
                    'sales_agent',
                    'continue_with_sales_agent',
                    [],
                )
            if not capabilities['sales_enabled']:
                return (
                    RouteType.DIRECT_AI_REPLY,
                    None,
                    None,
                    'generate_direct_reply',
                    [],
                )
            return (
                RouteType.ROUTE_TO_SALES_AGENT,
                'sales_pipeline',
                'sales_agent',
                'handoff_to_sales_agent',
                [],
            )

        return (
            RouteType.REQUEST_CLARIFICATION,
            None,
            None,
            'request_more_context',
            [],
        )

    def _agent_capabilities(self, event: NormalizedEvent) -> dict[str, bool]:
        metadata = getattr(event, 'metadata', None) or {}
        raw = metadata.get('agent_capabilities') or {}
        return {
            'sales_enabled': bool(raw.get('sales_enabled', True)),
        }

    def _active_ai_agent(self, event: NormalizedEvent) -> str | None:
        metadata = getattr(event, 'metadata', None) or {}
        active_agent = metadata.get('active_ai_agent')
        if active_agent in {'general', 'sales', 'marketing', 'operations'}:
            return active_agent
        return None
