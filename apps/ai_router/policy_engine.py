from __future__ import annotations

from .schemas import IntentClassification, NormalizedEvent, PolicyDecision, PolicyStatus, RiskAssessment


class PolicyEngine:
    def evaluate(
        self,
        event: NormalizedEvent,
        risk: RiskAssessment,
        intent: IntentClassification,
    ) -> PolicyDecision:
        if risk.level.value == 'critical':
            return PolicyDecision(
                status=PolicyStatus.BLOCKED,
                reasons=['Critical risk events cannot continue through automated routing.'],
                requires_human_approval=False,
                allowed_tools=[],
            )

        if intent.intent.value == 'buy_intent':
            return PolicyDecision(
                status=PolicyStatus.ALLOWED,
                reasons=['Sales qualification is allowed for the current tenant scope.'],
                requires_human_approval=False,
                allowed_tools=['crm_lookup', 'catalog_lookup'],
            )

        return PolicyDecision(
            status=PolicyStatus.ALLOWED,
            reasons=['No policy restriction matched for this tenant-scoped event.'],
            requires_human_approval=False,
            allowed_tools=[],
        )
