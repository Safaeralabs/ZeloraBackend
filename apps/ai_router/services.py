from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .decision_object import RouterDecision
from .schemas import (
    IntentClassification,
    ModelSelection,
    NormalizedEvent,
    PolicyDecision,
    RiskAssessment,
)


class InputProcessorPort(Protocol):
    def normalize(self, raw_event: dict[str, Any]) -> NormalizedEvent:
        ...


class RiskEnginePort(Protocol):
    def assess(self, event: NormalizedEvent) -> RiskAssessment:
        ...


class IntentServicePort(Protocol):
    def classify(self, event: NormalizedEvent, risk: RiskAssessment) -> IntentClassification:
        ...


class PolicyEnginePort(Protocol):
    def evaluate(
        self,
        event: NormalizedEvent,
        risk: RiskAssessment,
        intent: IntentClassification,
    ) -> PolicyDecision:
        ...


class RoutePlannerPort(Protocol):
    def plan(
        self,
        event: NormalizedEvent,
        risk: RiskAssessment,
        intent: IntentClassification,
        policy: PolicyDecision,
    ) -> RouterDecision:
        ...


class ModelSelectorPort(Protocol):
    def select_for_route(
        self,
        *,
        tenant_id: str,
        intent_name: str,
        route_name: str,
    ) -> ModelSelection:
        ...


class AuditLoggerPort(Protocol):
    def log_router_decision(
        self,
        *,
        event: NormalizedEvent,
        risk: RiskAssessment,
        intent: IntentClassification,
        policy: PolicyDecision,
        decision: RouterDecision,
    ) -> None:
        ...


@dataclass(slots=True)
class AIRouterService:
    input_processor: InputProcessorPort
    risk_engine: RiskEnginePort
    intent_service: IntentServicePort
    policy_engine: PolicyEnginePort
    route_planner: RoutePlannerPort
    audit_logger: AuditLoggerPort

    def route(self, raw_event: dict[str, Any]) -> RouterDecision:
        event = self.input_processor.normalize(raw_event)
        risk = self.risk_engine.assess(event)
        intent = self.intent_service.classify(event, risk)
        policy = self.policy_engine.evaluate(event, risk, intent)
        decision = self.route_planner.plan(event, risk, intent, policy)
        self.audit_logger.log_router_decision(
            event=event,
            risk=risk,
            intent=intent,
            policy=policy,
            decision=decision,
        )
        return decision
