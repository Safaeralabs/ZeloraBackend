from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from .schemas import ModelSelection, PolicyDecision, RiskAssessment, RouteType, utc_now


@dataclass(slots=True)
class RouterDecision:
    tenant_id: str
    conversation_id: str | None
    intent: str
    confidence: float
    entities: dict[str, Any]
    sentiment: str
    urgency: str
    risk_level: str
    risk_flags: list[str]
    policy_status: str
    policy_reasons: list[str]
    route: RouteType
    target: str | None
    agent: str | None
    provider: str | None
    model_profile: str
    model_name: str | None
    requires_human_approval: bool
    final_action: str
    fallback_route: str | None = None
    tool_scope: list[str] = field(default_factory=list)
    post_actions: list[dict[str, Any]] = field(default_factory=list)
    decision_id: str = field(default_factory=lambda: f'router_dec_{uuid4().hex}')
    decided_at: str = field(default_factory=lambda: utc_now().isoformat())

    @classmethod
    def from_components(
        cls,
        *,
        tenant_id: str,
        conversation_id: str | None,
        intent: str,
        confidence: float,
        entities: dict[str, Any],
        sentiment: str,
        urgency: str,
        risk: RiskAssessment,
        policy: PolicyDecision,
        route: RouteType,
        target: str | None,
        agent: str | None,
        model_selection: ModelSelection,
        final_action: str,
        fallback_route: str | None = None,
        post_actions: list[dict[str, Any]] | None = None,
    ) -> 'RouterDecision':
        return cls(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            intent=intent,
            confidence=confidence,
            entities=entities,
            sentiment=sentiment,
            urgency=urgency,
            risk_level=risk.level.value,
            risk_flags=risk.flags,
            policy_status=policy.status.value,
            policy_reasons=policy.reasons,
            route=route,
            target=target,
            agent=agent,
            provider=model_selection.provider.value if model_selection.provider else None,
            model_profile=model_selection.profile.value,
            model_name=model_selection.model_name,
            requires_human_approval=policy.requires_human_approval,
            final_action=final_action,
            fallback_route=fallback_route,
            tool_scope=policy.allowed_tools,
            post_actions=post_actions or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
