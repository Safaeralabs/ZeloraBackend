"""
Sales Agent v2 modules.
Decision-engine-first sales conversation system.
"""

from .brand import BrandVoice
from .followup import FollowUpEngine
from .session import SessionManager
from .situation import SituationDetector
from .decision import DecisionEngine, AgentAction
from .catalog import CatalogService
from .product_query import ProductQueryInterpreter
from .kb import KBService
from .examples import ExampleBank
from .customer_history import CustomerHistoryService
from .contact_memory import ContactMemoryService
from .promo import PromoEngine
from .recommendations import RecommendationEngine
from .generator import ResponseGenerator
from .validator import ResponseValidator
from .handoff import HandoffHandler

__all__ = [
    'BrandVoice',
    'FollowUpEngine',
    'SessionManager',
    'SituationDetector',
    'DecisionEngine',
    'AgentAction',
    'CatalogService',
    'ProductQueryInterpreter',
    'KBService',
    'ExampleBank',
    'CustomerHistoryService',
    'ContactMemoryService',
    'PromoEngine',
    'RecommendationEngine',
    'ResponseGenerator',
    'ResponseValidator',
    'HandoffHandler',
]
