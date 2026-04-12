"""
Sales Agent models: dataclasses, constants, and signal maps.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


def _has_real_identifier(value: Any) -> bool:
    return isinstance(value, (str, int, UUID))


STAGE_DISCOVERING = 'discovering'
STAGE_CONSIDERING = 'considering'
STAGE_INTENT_TO_BUY = 'intent_to_buy'
STAGE_CHECKOUT_BLOCKED = 'checkout_blocked'
STAGE_FOLLOW_UP_NEEDED = 'follow_up_needed'
STAGE_LOST = 'lost'
STAGE_CLOSED_WON = 'closed_won'
STAGE_CLOSED_LOST = 'closed_lost'
STAGE_HUMAN_HANDOFF = 'human_handoff'

DECISION_ASSIST_AND_ADVANCE = 'assist_and_advance'
DECISION_RECOMMEND = 'recommend'
DECISION_QUALIFY = 'qualify'
DECISION_ESCALATE = 'escalate'
DECISION_FOLLOW_UP = 'follow_up'
DECISION_DISCARD = 'discard'

_STAGE_SIGNALS: dict[str, list[str]] = {
    STAGE_CHECKOUT_BLOCKED: ['no puedo pagar', 'error al pagar', 'pago rechazado', 'no funciona el pago'],
    STAGE_CONSIDERING: ['comparar', 'diferencia entre', 'cual es mejor', 'cual me recomiendas', 'vs '],
    STAGE_INTENT_TO_BUY: [
        'quiero comprar', 'quiero pedir', 'quiero uno', 'lo quiero', 'cuanto cuesta',
        'precio', 'disponible', 'en stock', 'como pago', 'envio', 'cuando llega',
    ],
    STAGE_FOLLOW_UP_NEEDED: [
        'lo pienso',
        'lo veo',
        'despues',
        'mas adelante',
        'me avisan',
        'te aviso',
        'dejame pensarlo',
        'lo consulto',
        'luego te escribo',
        'mas tarde',
        'ahora no',
    ],
}

_NEGOTIATION_SIGNALS = (
    'negociacion',
    'descuento especial',
    'precio especial',
    'condiciones especiales',
    'acuerdo comercial',
    'factura empresarial',
)


@dataclass
class BuyerProfile:
    priority: str = 'unknown'
    quantity: str = 'single'
    urgency: str = 'exploring'
    objection: str | None = None
    style: str = 'exploratory'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BusinessContext:
    org_name: str = ''
    org_id: str = ''
    org_slug: str = ''
    what_you_sell: str = ''
    who_you_sell_to: str = ''
    mission: str = ''
    website: str = ''
    industry: str = ''
    country: str = ''
    brand_tone: str = 'amigable'
    payment_methods: list[str] = field(default_factory=lambda: ['transferencia bancaria', 'efectivo'])
    shipping_policy: str = ''           # free-text shipping description from brand config
    shipping_coverage: str = 'consultar cobertura'
    shipping_avg_days: str = '2-5 dias habiles'
    min_order_units: int = 1
    max_units_auto_approve: int = 10
    commercial_policies: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=lambda: [
        'ofrecer descuentos no autorizados',
        'confirmar stock sin verificar',
        'prometer tiempos de entrega no validados',
        'modificar precios',
        'cerrar pedidos manualmente',
        'redirigir al usuario a la pagina web como primera respuesta cuando la informacion esta disponible en el chat',
        'decir "llame a nuestro numero" o "acercate a la oficina" sin antes haber dado la informacion disponible por este canal',
    ])
    has_returns_policy: bool = True
    returns_window_days: int = 15
    # Agent persona & behaviour overrides
    agent_persona: str = ''            # e.g. "Vendedora entusiasta, experta en moda urbana"
    greeting_message: str = ''         # first message the agent sends in a new conversation
    competitor_response: str = ''      # how to handle competitor mentions
    response_language: str = 'auto'    # auto | es | en
    max_response_length: str = 'standard'  # brief | standard | detailed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BrandProfile:
    brand_name: str = ''
    tone_of_voice: str = 'cercano'
    formality_level: str = 'balanced'
    brand_personality: str = ''
    value_proposition: str = ''
    logo_url: str = ''
    primary_color: str = ''
    accent_color: str = ''
    visual_style: str = ''
    key_differentiators: list[str] = field(default_factory=list)
    preferred_closing_style: str = 'directo'
    urgency_style: str = 'soft'
    recommended_phrases: list[str] = field(default_factory=list)
    avoid_phrases: list[str] = field(default_factory=list)
    customer_style_notes: str = ''  # learned from how customers actually write

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SalesPlaybook:
    opening_style: str = ''
    recommendation_style: str = ''
    objection_style: str = ''
    closing_style: str = ''
    follow_up_style: str = ''
    upsell_style: str = ''
    escalate_conditions: list[str] = field(default_factory=list)
    handoff_mode: str = 'balanceado'
    competitor_response: str = ''      # what to do/say when customer asks about competitors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CommerceRules:
    discount_policy: str = ''
    negotiation_policy: str = ''
    inventory_promise_rule: str = ''
    delivery_promise_rule: str = ''
    return_policy_summary: str = ''
    forbidden_claims: list[str] = field(default_factory=list)
    forbidden_promises: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SalesContext:
    agent_name: str = 'Sales Agent'
    business: BusinessContext = field(default_factory=BusinessContext)
    brand: BrandProfile = field(default_factory=BrandProfile)
    playbook: SalesPlaybook = field(default_factory=SalesPlaybook)
    commerce_rules: CommerceRules = field(default_factory=CommerceRules)
    catalog_snapshot: list[dict[str, Any]] = field(default_factory=list)
    knowledge_snapshot: list[dict[str, Any]] = field(default_factory=list)
    buyer_model: dict[str, Any] = field(default_factory=dict)
    activation_checklist: dict[str, Any] = field(default_factory=dict)
    agent_preferences: dict[str, Any] = field(default_factory=dict)


@dataclass
class SalesAction:
    action_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HandoffDecision:
    needed: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SalesAgentResult:
    agent: str = 'sales_agent'
    stage: str = STAGE_DISCOVERING
    confidence: float = 0.0
    decision: str = DECISION_ASSIST_AND_ADVANCE
    recommended_actions: list[SalesAction] = field(default_factory=list)
    reply_text: str = ''
    handoff: HandoffDecision = field(default_factory=lambda: HandoffDecision(needed=False))
    buyer_profile: BuyerProfile = field(default_factory=BuyerProfile)
    products_shown: list[dict[str, Any]] = field(default_factory=list)
    context_used: dict[str, Any] = field(default_factory=dict)
    # Enrichment fields
    playbook_used: str = ''
    objection_reason: str = ''
    scope_classification: str = 'in_scope'
    learning_signals: list[str] = field(default_factory=list)
    referenced_products: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'agent': self.agent,
            'stage': self.stage,
            'confidence': self.confidence,
            'decision': self.decision,
            'recommended_actions': [item.to_dict() for item in self.recommended_actions],
            'reply_text': self.reply_text,
            'handoff': self.handoff.to_dict(),
            'buyer_profile': self.buyer_profile.to_dict(),
            'products_shown': self.products_shown,
            'context_used': self.context_used,
            'playbook_used': self.playbook_used,
            'objection_reason': self.objection_reason,
            'scope_classification': self.scope_classification,
            'learning_signals': self.learning_signals,
            'referenced_products': self.referenced_products,
        }


@dataclass
class SalesDecision:
    """P2.1: Decision output from Sales Brain (step 1) before Human Rewrite (step 2)."""
    products_to_show: list[str] = field(default_factory=list)  # Product IDs
    functional_reason: str = ''  # Why these products functionally solve the problem
    aesthetic_reason: str = ''  # Why they aesthetically fit the buyer
    occasion: str = ''  # e.g., "para una boda formal"
    narrative: str = ''  # Short storytelling phrase
    expected_objection: str | None = None  # Anticipated objection
    cta_suggestion: str = ''  # Suggested call-to-action
    strategy: str = 'recommend'  # 'compare' | 'recommend' | 'upsell' | 'bundle'
    raw_reply: str = ''  # Draft reply from Brain before Human Rewrite

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
