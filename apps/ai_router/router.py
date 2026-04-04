from __future__ import annotations

from .audit_logger import AuditLogger
from .input_processor import InputProcessor
from .intent_service import IntentService
from .policy_engine import PolicyEngine
from .risk_engine import RiskEngine
from .route_planner import RoutePlanner
from .services import AIRouterService


def build_ai_router_service() -> AIRouterService:
    return AIRouterService(
        input_processor=InputProcessor(),
        risk_engine=RiskEngine(),
        intent_service=IntentService(),
        policy_engine=PolicyEngine(),
        route_planner=RoutePlanner(),
        audit_logger=AuditLogger(),
    )
