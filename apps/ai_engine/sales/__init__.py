"""
Sales Agent v2 modules.
Decision-engine-first sales conversation system.
"""

from .session import SessionManager
from .situation import SituationDetector
from .decision import DecisionEngine, AgentAction
from .catalog import CatalogService
from .kb import KBService
from .promo import PromoEngine
from .recommendations import RecommendationEngine
from .generator import ResponseGenerator
from .validator import ResponseValidator
from .handoff import HandoffHandler

__all__ = [
    'SessionManager',
    'SituationDetector',
    'DecisionEngine',
    'AgentAction',
    'CatalogService',
    'KBService',
    'PromoEngine',
    'RecommendationEngine',
    'ResponseGenerator',
    'ResponseValidator',
    'HandoffHandler',
]
