from __future__ import annotations

import structlog

from .decision_object import RouterDecision
from .schemas import IntentClassification, NormalizedEvent, PolicyDecision, RiskAssessment


class AuditLogger:
    def __init__(self) -> None:
        self.logger = structlog.get_logger('apps.ai_router')

    def log_router_decision(
        self,
        *,
        event: NormalizedEvent,
        risk: RiskAssessment,
        intent: IntentClassification,
        policy: PolicyDecision,
        decision: RouterDecision,
    ) -> None:
        self.logger.info(
            'ai_router_decision',
            tenant_id=event.tenant_id,
            conversation_id=event.conversation_id,
            channel=event.channel.value,
            normalized_input=event.to_dict(),
            risk_result=risk.to_dict(),
            intent_result=intent.to_dict(),
            policy_result=policy.to_dict(),
            decision=decision.to_dict(),
        )
