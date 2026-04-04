"""
Sales Agent: adaptive, business-constrained sales closer for Vendly.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import quote
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


class SalesAgent:
    def run(self, *, message_text: str, conversation, organization, router_decision=None) -> SalesAgentResult:
        from .sales_tools import check_stock, get_active_promotions, get_order_history, lookup_products

        text = message_text.lower()
        sales_ctx = _load_sales_context(organization)
        if sales_ctx.agent_preferences.get('enabled', True) is False:
            return SalesAgentResult(
                stage=STAGE_DISCOVERING,
                confidence=1.0,
                decision=DECISION_ESCALATE,
                recommended_actions=[SalesAction('escalate_to_human', {'reason': 'sales_agent_disabled'})],
                reply_text='Te paso con un asesor humano para continuar desde aqui.',
                handoff=HandoffDecision(needed=True, reason='sales_agent_disabled'),
            )
        out_of_scope = _guard_general_scope_request(message_text, sales_ctx)
        if out_of_scope:
            return SalesAgentResult(
                stage=STAGE_DISCOVERING,
                confidence=0.96,
                decision=DECISION_DISCARD,
                recommended_actions=[],
                reply_text=out_of_scope['reply'],
                handoff=HandoffDecision(needed=False),
                buyer_profile=BuyerProfile(),
                context_used={
                    'out_of_scope': True,
                    'out_of_scope_kind': out_of_scope['kind'],
                    'out_of_scope_reason': out_of_scope['reason'],
                    'brand_scope_enforced': True,
                },
            )
        # ── DB-driven flows (any organization) ────────────────────────────────
        try:
            from apps.flows.engine import FlowEngine
            _engine = FlowEngine()
            _channel = getattr(conversation, 'canal', 'web') or 'web'
            _db_result = _engine.advance(
                conversation=conversation,
                message_text=message_text,
                sales_ctx=sales_ctx,
            )
            if _db_result is None:
                _db_result = _engine.find_and_activate(
                    conversation=conversation,
                    message_text=message_text,
                    channel=_channel,
                    sales_ctx=sales_ctx,
                )
            if _db_result is not None and not _db_result.delegate_to_ai:
                _flow_stage = STAGE_HUMAN_HANDOFF if _db_result.handoff else (
                    STAGE_CLOSED_WON if _db_result.completed else STAGE_DISCOVERING
                )
                return SalesAgentResult(
                    stage=_flow_stage,
                    confidence=0.97,
                    decision=DECISION_ESCALATE if _db_result.handoff else DECISION_ASSIST_AND_ADVANCE,
                    recommended_actions=[
                        SalesAction('flow_progress', {
                            'flow_id': _db_result.flow_id,
                            'flow_name': _db_result.flow_name,
                            'node': _db_result.current_node_id,
                            'completed': _db_result.completed,
                        })
                    ],
                    reply_text=_apply_brand_voice(
                        _db_result.reply_text, sales_ctx.brand, sales_ctx.playbook, _flow_stage
                    ) if _db_result.reply_text else _db_result.reply_text,
                    handoff=HandoffDecision(needed=_db_result.handoff, reason=_db_result.handoff_reason),
                    buyer_profile=BuyerProfile(),
                    context_used={
                        'db_flow_active': True,
                        'flow_name': _db_result.flow_name,
                        'flow_id': _db_result.flow_id,
                        'flow_completed': _db_result.completed,
                        'flow_variables': _db_result.variables,
                    },
                )
        except Exception as _flow_exc:
            logger.warning('db_flow_engine_error', error=str(_flow_exc))

        # ── Legacy hardcoded flows (Comfaguajira only) ─────────────────────
        qualification_flow = _handle_affiliation_qualification_flow(
            message_text=message_text,
            conversation=conversation,
            sales_ctx=sales_ctx,
        )
        if qualification_flow:
            return qualification_flow
        service_flow = _handle_comfaguajira_service_flow(
            message_text=message_text,
            conversation=conversation,
            sales_ctx=sales_ctx,
        )
        if service_flow:
            return service_flow
        buyer = _profile_buyer(text, sales_ctx.buyer_model)
        stage, confidence = _classify_stage(text, sales_ctx.buyer_model)
        close_signals = _detect_close_signals(text)
        handoff = _check_handoff(text, buyer, sales_ctx.business, sales_ctx.playbook)

        if handoff.needed:
            return SalesAgentResult(
                stage=stage,
                confidence=confidence,
                decision=DECISION_ESCALATE,
                recommended_actions=[SalesAction('escalate_to_human', {'reason': handoff.reason})],
                reply_text=_apply_brand_voice(
                    'Voy a conectarte con un asesor de ventas que puede ayudarte mejor con esta solicitud.',
                    sales_ctx.brand,
                    sales_ctx.playbook,
                    stage,
                ),
                handoff=handoff,
                buyer_profile=buyer,
            )

        products = lookup_products(organization, message_text)
        promotions = get_active_promotions(organization)
        contact = getattr(conversation, 'contact', None)
        order_history = get_order_history(organization, contact) if contact else []
        stock_info = None
        if products and stage in (STAGE_INTENT_TO_BUY, STAGE_CHECKOUT_BLOCKED):
            stock_info = check_stock(organization, products[0]['id'])

        reply_text = _generate_reply(
            message_text=message_text,
            stage=stage,
            buyer=buyer,
            products=products,
            stock_info=stock_info,
            promotions=promotions,
            sales_ctx=sales_ctx,
            router_decision=router_decision,
            conversation=conversation,
        )
        reply_text = _enforce_reply_scope(
            message_text=message_text,
            reply_text=reply_text,
            sales_ctx=sales_ctx,
            stage=stage,
        )
        reply_text = _strengthen_closing_reply(
            reply_text=reply_text,
            stage=stage,
            close_signals=close_signals,
            products=products,
            sales_ctx=sales_ctx,
        )
        actions = _build_actions(stage, message_text, products, promotions, buyer, sales_ctx.business, sales_ctx, close_signals)

        if sales_ctx.agent_preferences.get('followup_mode', 'suave') != 'apagado' and stage in (STAGE_FOLLOW_UP_NEEDED, STAGE_CONSIDERING):
            _create_followup_task(conversation, organization, stage, message_text, buyer)

        return SalesAgentResult(
            stage=stage,
            confidence=confidence,
            decision=_derive_decision(stage, products, buyer),
            recommended_actions=actions,
            reply_text=reply_text,
            handoff=HandoffDecision(needed=False),
            buyer_profile=buyer,
            products_shown=products[:3],
            context_used={
                'products_found': len(products),
                'catalog_items_loaded': len(sales_ctx.catalog_snapshot),
                'knowledge_items_loaded': len(sales_ctx.knowledge_snapshot),
                'promotions_active': len(promotions),
                'has_order_history': bool(order_history),
                'stock_checked': stock_info is not None,
                'buyer_priority': buyer.priority,
                'buyer_urgency': buyer.urgency,
                'buyer_objection': buyer.objection,
                'close_signals': close_signals,
                'closing_ready': bool(close_signals) and stage in (STAGE_INTENT_TO_BUY, STAGE_CHECKOUT_BLOCKED),
                'brand_tone': sales_ctx.brand.tone_of_voice,
                'brand_formality': sales_ctx.brand.formality_level,
                'brand_closing_style': sales_ctx.brand.preferred_closing_style,
                'playbook_loaded': bool(sales_ctx.playbook.closing_style or sales_ctx.playbook.opening_style),
                'business_constraints_applied': True,
            },
        )


def _infer_objection_reason(text: str) -> str | None:
    """Use gpt-4o-mini to classify the buyer objection in a single token response."""
    try:
        import os
        from openai import OpenAI

        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            return None

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            temperature=0,
            max_tokens=10,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'Classify the buyer objection in this message as exactly one of: '
                        'price, shipping, availability, trust, quality, urgency, none. '
                        'Respond with only the single word.'
                    ),
                },
                {'role': 'user', 'content': text[:400]},
            ],
        )
        label = response.choices[0].message.content.strip().lower()
        if label in ('price', 'shipping', 'availability', 'trust', 'quality', 'urgency'):
            return label
        return None
    except Exception:
        return None


def _profile_buyer(text: str, buyer_model: dict[str, Any] | None = None) -> BuyerProfile:
    priority = 'unknown'
    if any(token in text for token in ('barato', 'economico', 'precio bajo', 'mas barato', 'descuento')):
        priority = 'price'
    elif any(token in text for token in ('calidad', 'resistente', 'durable', 'premium', 'el mejor')):
        priority = 'quality'
    elif any(token in text for token in ('urgente', 'rapido', 'hoy mismo', 'ya', 'inmediato', 'express')):
        priority = 'speed'

    quantity = 'single'
    if any(token in text for token in ('mayorista', 'distribucion', 'al por mayor', 'wholesale')):
        quantity = 'bulk'
    elif any(token in text for token in ('varios', 'algunas', 'pocos', 'pares')):
        quantity = 'multiple'
    else:
        match = re.search(r'\b(\d+)\s*(?:unidades?|piezas?|articulos?|items?|pares?|cajas?|paquetes?)\b', text)
        if match and int(match.group(1)) > 3:
            quantity = 'multiple'

    urgency = 'exploring'
    if any(token in text for token in ('hoy', 'ya', 'ahora', 'urgente', 'inmediato', 'cuanto antes')):
        urgency = 'immediate'
    elif any(token in text for token in ('esta semana', 'pronto', 'proximo', 'en dias')):
        urgency = 'this_week'

    objection = None
    # Fast heuristic first; fall back to gpt-4o-mini micro-call when ambiguous
    if any(token in text for token in ('muy caro', 'es caro', 'costoso', 'precio alto', 'sale caro')):
        objection = 'price'
    elif any(token in text for token in ('envio caro', 'no llega', 'shipping', 'cobertura')):
        objection = 'shipping'
    elif any(token in text for token in ('sin stock', 'agotado', 'no disponible')):
        objection = 'availability'
    elif any(token in text for token in ('confiable', 'garantia', 'son de fiar')):
        objection = 'trust'
    elif isinstance(buyer_model, dict):
        for item in buyer_model.get('common_objections', []):
            if isinstance(item, str) and item.strip() and item.lower() in text:
                objection = item.strip().lower()
                break
    if objection is None:
        objection = _infer_objection_reason(text)

    style = 'exploratory'
    if any(token in text for token in ('quiero', 'compro', 'necesito', 'dame', 'enviame', 'mandame')):
        style = 'direct'
    elif any(token in text for token in ('comparar', 'diferencia', 'cual', 'entre', 'opciones')):
        style = 'comparative'

    return BuyerProfile(priority=priority, quantity=quantity, urgency=urgency, objection=objection, style=style)


def _classify_stage(text: str, buyer_model: dict[str, Any] | None = None) -> tuple[str, float]:
    if isinstance(buyer_model, dict):
        for signal in buyer_model.get('bulk_buyer_signals', []):
            if isinstance(signal, str) and signal.lower() in text:
                return STAGE_INTENT_TO_BUY, 0.86
        for signal in buyer_model.get('purchase_signals', []):
            if isinstance(signal, str) and signal.lower() in text:
                return STAGE_INTENT_TO_BUY, 0.90
        for signal in buyer_model.get('low_intent_signals', []):
            if isinstance(signal, str) and signal.lower() in text:
                return STAGE_FOLLOW_UP_NEEDED, 0.72

    for stage, signals in _STAGE_SIGNALS.items():
        if any(signal in text for signal in signals):
            return stage, 0.88 if stage == STAGE_INTENT_TO_BUY else 0.80
    return STAGE_DISCOVERING, 0.60


def _check_handoff(text: str, buyer: BuyerProfile, biz_ctx: BusinessContext, playbook: SalesPlaybook) -> HandoffDecision:
    handoff_mode = getattr(playbook, 'handoff_mode', 'balanceado')
    for signal in _NEGOTIATION_SIGNALS:
        if signal in text:
            return HandoffDecision(needed=True, reason=f'negotiation_request:{signal}')
    for signal in playbook.escalate_conditions:
        if isinstance(signal, str) and signal.strip() and signal.lower() in text:
            return HandoffDecision(needed=True, reason=f'playbook_escalation:{signal}')
    if handoff_mode == 'temprano' and buyer.objection in {'trust', 'availability'}:
        return HandoffDecision(needed=True, reason=f'early_handoff:{buyer.objection}')
    if buyer.quantity == 'bulk':
        return HandoffDecision(needed=True, reason='bulk_order_requires_human_approval')
    match = re.search(r'\b(\d+)\s*(?:unidades?|piezas?|articulos?|items?|pares?|cajas?|paquetes?|docenas?)\b', text)
    if match and int(match.group(1)) > biz_ctx.max_units_auto_approve:
        return HandoffDecision(needed=True, reason=f'order_quantity_exceeds_auto_limit_{biz_ctx.max_units_auto_approve}')
    return HandoffDecision(needed=False)


def _load_sales_context(organization) -> SalesContext:
    try:
        from apps.channels_config.models import ChannelConfig

        org_id = getattr(organization, 'id', None)
        if not _has_real_identifier(org_id):
            return SalesContext(
                business=BusinessContext(
                    org_name=getattr(organization, 'name', ''),
                    org_slug=getattr(organization, 'slug', ''),
                )
            )

        config = ChannelConfig.objects.filter(organization=organization, channel='onboarding').only('settings').first()
        settings = (config.settings if config else {}) or {}
        app_config = ChannelConfig.objects.filter(organization=organization, channel='app').only('settings').first()
        web_config = ChannelConfig.objects.filter(organization=organization, channel='web').only('settings').first()
        app_settings = (app_config.settings if app_config else {}) or {}
        web_settings = (web_config.settings if web_config else {}) or {}
        sales_agent_profile = settings.get('sales_agent_profile', {}) or {}
        brand_cfg = sales_agent_profile.get('brand_profile') or settings.get('brand_profile', {}) or {}
        playbook_cfg = sales_agent_profile.get('sales_playbook') or settings.get('sales_playbook', {}) or {}
        rules_cfg = sales_agent_profile.get('commerce_rules') or settings.get('commerce_rules', {}) or {}
        buyer_model_cfg = sales_agent_profile.get('buyer_model') or settings.get('buyer_model', {}) or {}
        ai_preferences = settings.get('ai_preferences', {}) or {}
        sales_agent_preferences = ai_preferences.get('sales_agent', {}) or {}
        logo_url = ''
        try:
            logo = getattr(organization, 'logo', None)
            if logo and getattr(logo, 'url', ''):
                logo_url = logo.url
        except Exception:
            logo_url = ''

        business = BusinessContext(
            org_name=getattr(organization, 'name', ''),
            org_id=str(getattr(organization, 'id', '') or ''),
            org_slug=getattr(organization, 'slug', ''),
            what_you_sell=sales_agent_profile.get('what_you_sell') or settings.get('what_you_sell', ''),
            who_you_sell_to=sales_agent_profile.get('who_you_sell_to') or settings.get('who_you_sell_to', ''),
            website=getattr(organization, 'website', '') or settings.get('website', ''),
            industry=getattr(organization, 'industry', '') or settings.get('industry', ''),
            country=getattr(organization, 'country', '') or settings.get('country', ''),
            brand_tone=brand_cfg.get('tone_of_voice', 'amigable') or 'amigable',
            payment_methods=settings.get('payment_methods', ['transferencia bancaria', 'efectivo']),
            shipping_coverage=settings.get('shipping_coverage', 'consultar cobertura'),
            shipping_avg_days=settings.get('shipping_avg_days', '2-5 dias habiles'),
            min_order_units=int(settings.get('min_order_units', 1)),
            max_units_auto_approve=int(settings.get('max_units_auto_approve', 10)),
            commercial_policies=[
                item for item in [
                    rules_cfg.get('discount_policy', ''),
                    rules_cfg.get('negotiation_policy', ''),
                    rules_cfg.get('inventory_promise_rule', ''),
                    rules_cfg.get('delivery_promise_rule', ''),
                ] if item
            ],
            forbidden_actions=(
                rules_cfg.get('forbidden_promises')
                or rules_cfg.get('forbidden_claims')
                or BusinessContext().forbidden_actions
            ),
            has_returns_policy=bool(rules_cfg.get('return_policy_summary', '').strip()),
            returns_window_days=int(settings.get('returns_window_days', 15)),
            shipping_policy=sales_agent_profile.get('shipping_policy') or rules_cfg.get('shipping_policy', ''),
            agent_persona=sales_agent_profile.get('agent_persona') or settings.get('agent_persona', ''),
            greeting_message=sales_agent_profile.get('greeting_message') or settings.get('greeting_message', ''),
            competitor_response=sales_agent_profile.get('competitor_response') or playbook_cfg.get('competitor_response', ''),
            response_language=sales_agent_profile.get('response_language') or settings.get('response_language', 'auto'),
            max_response_length=sales_agent_preferences.get('max_response_length', 'standard') or 'standard',
            mission=sales_agent_profile.get('mission_statement') or settings.get('mission', '') or settings.get('brand_mission', ''),
        )
        brand = BrandProfile(
            brand_name=getattr(organization, 'name', ''),
            tone_of_voice=brand_cfg.get('tone_of_voice', 'cercano') or 'cercano',
            formality_level=brand_cfg.get('formality_level', 'balanced') or 'balanced',
            brand_personality=brand_cfg.get('brand_personality', ''),
            value_proposition=brand_cfg.get('value_proposition', ''),
            logo_url=logo_url,
            primary_color=app_settings.get('primary_color') or web_settings.get('brand_color', ''),
            accent_color=app_settings.get('accent_color', ''),
            visual_style=app_settings.get('surface_style') or web_settings.get('position', ''),
            key_differentiators=brand_cfg.get('key_differentiators', []) or [],
            preferred_closing_style=brand_cfg.get('preferred_closing_style', 'directo') or 'directo',
            urgency_style=brand_cfg.get('urgency_style', 'soft') or 'soft',
            recommended_phrases=brand_cfg.get('recommended_phrases', []) or [],
            avoid_phrases=brand_cfg.get('avoid_phrases', []) or [],
            customer_style_notes=brand_cfg.get('customer_style_notes', '') or '',
        )
        playbook = SalesPlaybook(
            opening_style=playbook_cfg.get('opening_style', ''),
            recommendation_style=playbook_cfg.get('recommendation_style', ''),
            objection_style=playbook_cfg.get('objection_style', ''),
            closing_style=playbook_cfg.get('closing_style', ''),
            follow_up_style=playbook_cfg.get('follow_up_style', ''),
            upsell_style=playbook_cfg.get('upsell_style', ''),
            escalate_conditions=playbook_cfg.get('escalate_conditions', []) or [],
            handoff_mode=sales_agent_preferences.get('handoff_mode', 'balanceado') or 'balanceado',
            competitor_response=sales_agent_profile.get('competitor_response') or playbook_cfg.get('competitor_response', ''),
        )
        rules = CommerceRules(
            discount_policy=rules_cfg.get('discount_policy', ''),
            negotiation_policy=rules_cfg.get('negotiation_policy', ''),
            inventory_promise_rule=rules_cfg.get('inventory_promise_rule', ''),
            delivery_promise_rule=rules_cfg.get('delivery_promise_rule', ''),
            return_policy_summary=rules_cfg.get('return_policy_summary', ''),
            forbidden_claims=rules_cfg.get('forbidden_claims', []) or [],
            forbidden_promises=rules_cfg.get('forbidden_promises', []) or [],
        )
        return SalesContext(
            agent_name=settings.get('sales_agent_name', 'Sales Agent') or 'Sales Agent',
            business=business,
            brand=brand,
            playbook=playbook,
            commerce_rules=rules,
            catalog_snapshot=_load_catalog_snapshot(organization),
            knowledge_snapshot=_load_knowledge_snapshot(organization),
            buyer_model=buyer_model_cfg,
            activation_checklist=settings.get('activation_checklist', {}) or {},
            agent_preferences=sales_agent_preferences,
        )
    except Exception as exc:
        logger.warning('sales_agent_context_load_error', error=str(exc))
        return SalesContext(business=BusinessContext(org_name=getattr(organization, 'name', ''), org_slug=getattr(organization, 'slug', '')))


def _build_actions(
    stage: str,
    message_text: str,
    products: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
    buyer: BuyerProfile,
    biz_ctx: BusinessContext,
    sales_ctx: SalesContext | None = None,
    close_signals: list[str] | None = None,
) -> list[SalesAction]:
    actions: list[SalesAction] = []
    prefs = (sales_ctx.agent_preferences if sales_ctx else {}) or {}
    recommendation_depth = max(1, min(int(prefs.get('recommendation_depth', 3) or 3), 3))
    followup_mode = prefs.get('followup_mode', 'suave')
    topics = _detect_topics(message_text.lower())
    if topics:
        actions.append(SalesAction('answer_question', {'topics': topics}))
    if products and stage in (STAGE_DISCOVERING, STAGE_CONSIDERING, STAGE_INTENT_TO_BUY):
        actions.append(SalesAction('suggest_product', {'product_ids': [item['id'] for item in products[:recommendation_depth]]}))
    if promotions:
        actions.append(SalesAction('show_promotion', {'promotions': promotions[:2]}))
    if followup_mode != 'apagado' and stage in (STAGE_FOLLOW_UP_NEEDED, STAGE_CONSIDERING):
        actions.append(SalesAction('create_followup_task', {
            'priority': 'high' if buyer.urgency == 'this_week' else 'medium',
            'reason': f'stage:{stage},buyer_priority:{buyer.priority}',
        }))
    if stage == STAGE_CHECKOUT_BLOCKED:
        actions.append(SalesAction('remove_friction', {'stage': stage, 'objection': buyer.objection}))
    if close_signals:
        actions.append(SalesAction('close_sale', {'signals': close_signals[:4]}))
        if any(signal in close_signals for signal in ('payment_intent', 'next_step_intent')):
            actions.append(SalesAction('offer_payment_options', {'payment_methods': biz_ctx.payment_methods}))
        if any(signal in close_signals for signal in ('explicit_buy_intent', 'availability_check')):
            actions.append(SalesAction('propose_order_creation', {'max_units_auto_approve': biz_ctx.max_units_auto_approve}))
    if buyer.quantity == 'bulk' or biz_ctx.min_order_units > 1:
        actions.append(SalesAction('respect_business_rules', {'min_order_units': biz_ctx.min_order_units}))
    return actions


def _load_catalog_snapshot(organization) -> list[dict[str, Any]]:
    try:
        from django.db import connection

        from apps.ecommerce.models import Product, ProductVariant

        with connection.cursor() as cursor:
            product_columns = {row[1] for row in cursor.execute('PRAGMA table_info(products)').fetchall()}
            variant_columns = {row[1] for row in cursor.execute('PRAGMA table_info(product_variants)').fetchall()}

        product_fields = [
            field
            for field in ['id', 'title', 'brand', 'description', 'category', 'status', 'tags', 'is_active']
            if field in product_columns
        ]
        variant_fields = [
            field
            for field in ['id', 'product_id', 'sku', 'name', 'price', 'stock', 'reserved']
            if field in variant_columns
        ]

        products = list(
            Product.objects.filter(
                organization=organization,
                is_active=True,
                status='active',
            ).order_by('title').values(*product_fields)[:8]
        )
        product_ids = [item['id'] for item in products if item.get('id')]
        variants_by_product: dict[Any, list[dict[str, Any]]] = {}
        if product_ids:
            variants = ProductVariant.objects.filter(product_id__in=product_ids).values(*variant_fields)
            for variant in variants:
                variants_by_product.setdefault(variant.get('product_id'), []).append(variant)

        snapshot: list[dict[str, Any]] = []
        for product in products:
            variant_data = []
            for variant in variants_by_product.get(product.get('id'), [])[:4]:
                price = float(variant.get('price') or 0)
                available = max(0, int(variant.get('stock') or 0) - int(variant.get('reserved') or 0))
                variant_data.append({
                    'name': variant.get('name', ''),
                    'sku': variant.get('sku', ''),
                    'price': price,
                    'available': available,
                    'in_stock': available > 0,
                })

            prices = [item['price'] for item in variant_data if item['price'] > 0]
            snapshot.append({
                'title': product.get('title', ''),
                'brand': product.get('brand', ''),
                'category': product.get('category', ''),
                'description': ' '.join((product.get('description') or '').split())[:220],
                'offer_type': 'physical',
                'price_type': 'fixed',
                'requires_shipping': True,
                'requires_booking': False,
                'min_price': min(prices) if prices else None,
                'any_in_stock': any(item['in_stock'] for item in variant_data),
                'variants': variant_data,
                'tags': product.get('tags') or [],
            })
        return snapshot
    except Exception as exc:
        logger.warning('sales_agent_catalog_snapshot_error', error=str(exc))
        return []


def _load_knowledge_snapshot(organization) -> list[dict[str, Any]]:
    try:
        from apps.knowledge_base.models import KBArticle, KBDocument

        items: list[dict[str, Any]] = []
        articles = KBArticle.objects.filter(
            organization=organization,
            is_active=True,
            status='published',
        ).order_by('-updated_at')[:6]
        for article in articles:
            items.append({
                'type': 'article',
                'title': article.title,
                'category': article.category,
                'tags': article.tags or [],
                'content': ' '.join(article.content.split())[:320],
            })

        documents = KBDocument.objects.filter(
            organization=organization,
            is_active=True,
            processing_status='ready',
        ).order_by('-updated_at')[:4]
        for document in documents:
            items.append({
                'type': 'document',
                'title': document.filename,
                'category': '',
                'tags': [],
                'content': ' '.join((document.extracted_text or '').split())[:320],
            })
        return items
    except Exception as exc:
        logger.warning('sales_agent_knowledge_snapshot_error', error=str(exc))
        return []


def _detect_topics(text: str) -> list[str]:
    topics: list[str] = []
    if any(token in text for token in ('precio', 'costo', 'cuanto', 'vale', 'price')):
        topics.append('price')
    if any(token in text for token in ('envio', 'delivery', 'llega', 'entrega', 'shipping', 'demora')):
        topics.append('shipping')
    if any(token in text for token in ('pago', 'pagar', 'tarjeta', 'transferencia', 'payment', 'efectivo', 'pse')):
        topics.append('payment')
    if any(token in text for token in ('stock', 'disponible', 'disponibilidad', 'hay', 'tienen', 'agotado')):
        topics.append('stock')
    return topics


def _detect_close_signals(text: str) -> list[str]:
    signals: list[str] = []
    if any(token in text for token in ('quiero comprar', 'lo quiero', 'quiero pedir', 'me lo llevo', 'quiero ese', 'quiero este')):
        signals.append('explicit_buy_intent')
    if any(token in text for token in ('como pago', 'metodos de pago', 'formas de pago', 'transferencia', 'efectivo', 'pse', 'tarjeta')):
        signals.append('payment_intent')
    if any(token in text for token in ('disponible', 'tienen', 'hay', 'en stock', 'queda')):
        signals.append('availability_check')
    if any(token in text for token in ('cuando llega', 'envio', 'entrega', 'demora', 'tiempo de entrega')):
        signals.append('delivery_check')
    if any(token in text for token in ('como sigo', 'siguiente paso', 'que hago', 'como lo pido', 'como cerramos', 'como aparto')):
        signals.append('next_step_intent')
    return signals


def _derive_decision(stage: str, products: list[dict[str, Any]], buyer: BuyerProfile) -> str:
    if stage == STAGE_INTENT_TO_BUY:
        return DECISION_ASSIST_AND_ADVANCE
    if stage == STAGE_CONSIDERING:
        return DECISION_RECOMMEND
    if stage == STAGE_FOLLOW_UP_NEEDED:
        return DECISION_FOLLOW_UP
    if stage == STAGE_LOST:
        return DECISION_DISCARD
    if stage == STAGE_DISCOVERING and buyer.style == 'direct':
        return DECISION_QUALIFY
    if products:
        return DECISION_RECOMMEND
    return DECISION_ASSIST_AND_ADVANCE


def _generate_reply(
    *,
    message_text: str,
    stage: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    stock_info: dict[str, Any] | None,
    promotions: list[dict[str, Any]],
    sales_ctx: SalesContext,
    router_decision,
    conversation=None,
) -> str:
    from django.conf import settings as django_settings

    out_of_scope_reply = _guard_out_of_scope_brand_query(message_text, sales_ctx)
    if out_of_scope_reply:
        return out_of_scope_reply

    if getattr(django_settings, 'ENABLE_REAL_AI', False) and getattr(django_settings, 'OPENAI_API_KEY', ''):
        reply = _llm_reply(
            message_text=message_text,
            stage=stage,
            buyer=buyer,
            products=products,
            stock_info=stock_info,
            promotions=promotions,
            sales_ctx=sales_ctx,
            router_decision=router_decision,
            settings=django_settings,
            conversation=conversation,
        )
        if reply:
            normalized = _avoid_consecutive_repeat(
                reply=reply,
                conversation=conversation,
                message_text=message_text,
                stage=stage,
                buyer=buyer,
                products=products,
            )
            with_products = _append_product_links(normalized, products, sales_ctx.business.org_slug)
            return _append_payment_links(with_products, sales_ctx.business.payment_methods, sales_ctx.business.org_slug)

    normalized = _avoid_consecutive_repeat(
        reply=_heuristic_reply(
        message_text=message_text,
        stage=stage,
        buyer=buyer,
        products=products,
        stock_info=stock_info,
        promotions=promotions,
        sales_ctx=sales_ctx,
        ),
        conversation=conversation,
        message_text=message_text,
        stage=stage,
        buyer=buyer,
        products=products,
    )
    with_products = _append_product_links(normalized, products, sales_ctx.business.org_slug)
    return _append_payment_links(with_products, sales_ctx.business.payment_methods, sales_ctx.business.org_slug)


def _enforce_reply_scope(*, message_text: str, reply_text: str, sales_ctx: SalesContext, stage: str) -> str:
    reply = ' '.join((reply_text or '').split()).strip()
    if not reply:
        return reply

    scope_terms = _build_scope_terms(sales_ctx)
    suspicious_general_patterns = (
        'es una region',
        'es una región',
        'conocida por',
        'hogar del',
        'destinos turisticos',
        'destinos turísticos',
        'paisajes',
        'capital de',
        'presidente',
        'gobierno',
        'historia de',
    )
    if any(pattern in reply.lower() for pattern in suspicious_general_patterns):
        if not any(term in reply.lower() for term in scope_terms):
            brand_name = sales_ctx.brand.brand_name or sales_ctx.business.org_name or 'la organizacion'
            what_you_sell = sales_ctx.business.what_you_sell or 'sus servicios y procesos'
            safe_reply = (
                f'Solo te puedo ayudar con {brand_name}, {what_you_sell}, politicas, requisitos y atencion de la organizacion. '
                'Si quieres, dime tu duda concreta y te ayudo dentro de ese contexto.'
            )
            return _apply_brand_voice(safe_reply, sales_ctx.brand, sales_ctx.playbook, stage)
    return reply


def _strengthen_closing_reply(
    *,
    reply_text: str,
    stage: str,
    close_signals: list[str],
    products: list[dict[str, Any]],
    sales_ctx: SalesContext,
) -> str:
    reply = ' '.join((reply_text or '').split()).strip()
    if not reply or stage not in (STAGE_INTENT_TO_BUY, STAGE_CHECKOUT_BLOCKED):
        return reply
    if not close_signals:
        return reply

    lowered = reply.lower()
    if any(token in lowered for token in ('prefieres', 'te lo dejo', 'lo dejamos listo', 'cerramos', 'te ayudo a dejarlo listo')):
        return reply

    product_title = products[0]['title'] if products else 'la opcion'
    payment_methods = sales_ctx.business.payment_methods or ['transferencia bancaria', 'efectivo']
    payment_label = ' o '.join(payment_methods[:2])

    if 'payment_intent' in close_signals:
        cta = f'Si te cuadra {product_title}, lo dejamos listo hoy. ¿Prefieres pagar por {payment_label}?'
    elif 'availability_check' in close_signals or 'delivery_check' in close_signals:
        cta = f'Si te sirve {product_title}, te ayudo a dejar el pedido listo hoy. ¿Lo armamos?'
    else:
        cta = f'Si esta es la opcion que te encaja, te ayudo a cerrarlo ahora mismo. ¿Te la dejo lista?'

    if reply.endswith('?'):
        return reply
    return f'{reply} {cta}'.strip()


def _guard_out_of_scope_request(message_text: str, sales_ctx: SalesContext) -> dict[str, str] | None:
    brand_block = _guard_out_of_scope_brand_query(message_text, sales_ctx)
    if brand_block:
        return {
            'kind': 'other_brand',
            'reason': 'asked_about_other_company_or_brand',
            'reply': brand_block,
        }

    text = ' '.join((message_text or '').lower().split())
    if not text:
        return None

    unrelated_signals = (
        'clima', 'tiempo hoy', 'pronostico', 'pronóstico', 'llover', 'lluvia',
        'presidente', 'alcalde', 'gobierno', 'politica', 'política', 'elecciones',
        'partido', 'futbol', 'fútbol', 'gol', 'campeon', 'campeón', 'liga',
        'capital de', 'pais de', 'país de', 'historia de', 'quien descubrio', 'quién descubrió',
        'traduceme', 'tradúceme', 'traduce esto', 'resuelve', 'ecuacion', 'ecuación',
        'programacion', 'programación', 'codigo', 'código', 'python', 'javascript',
        'horoscopo', 'horóscopo', 'tarot', 'receta', 'cocinar',
    )
    if not any(signal in text for signal in unrelated_signals):
        return None

    try:
        scope_terms = _build_scope_terms(sales_ctx)
    except Exception:
        scope_terms = set()
    if any(term in text for term in scope_terms):
        return None

    brand_name = sales_ctx.brand.brand_name or sales_ctx.business.org_name or 'la marca'
    what_you_sell = sales_ctx.business.what_you_sell or 'nuestros productos'
    reply = (
        f'Aqui solo te puedo ayudar con {brand_name}, {what_you_sell}, disponibilidad, politicas y compra por chat. '
        'Si quieres, te recomiendo una opcion o resolvemos una duda del producto.'
    )
    return {
        'kind': 'unrelated_topic',
        'reason': 'asked_about_topic_outside_business_scope',
        'reply': _apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
    }


def _guard_general_scope_request(message_text: str, sales_ctx: SalesContext) -> dict[str, str] | None:
    text = ' '.join((message_text or '').lower().split())
    if not text:
        return None

    try:
        scope_terms = _build_scope_terms(sales_ctx)
    except Exception:
        scope_terms = set()
    business_anchor_terms = scope_terms | {
        'producto', 'productos', 'servicio', 'servicios', 'precio', 'precios', 'pago', 'pagos',
        'disponible', 'disponibilidad', 'compra', 'comprar', 'pedido', 'pedidos', 'envio', 'envios',
        'entrega', 'politica', 'politicas', 'horario', 'horarios', 'stock', 'talla', 'tallas',
        'asesor', 'asesoria', 'promocion', 'promociones', 'catalogo', 'afiliacion', 'afiliaciones',
        'subsidio', 'subsidios', 'certificado', 'certificados', 'beneficiario', 'beneficiarios',
        'tramite', 'tramites',
    }
    asks_for_general_info = any(
        signal in text for signal in (
            'hablame de ', 'háblame de ', 'hablame sobre ', 'háblame sobre ',
            'cuentame de ', 'cuéntame de ', 'cuentame sobre ', 'cuéntame sobre ',
            'dime algo de ', 'dime algo sobre ', 'que sabes de ', 'qué sabes de ',
            'informacion de ', 'información de ', 'quiero saber de ',
        )
    )
    if asks_for_general_info and not any(term in text for term in business_anchor_terms):
        brand_name = sales_ctx.brand.brand_name or sales_ctx.business.org_name or 'la marca'
        what_you_sell = sales_ctx.business.what_you_sell or 'nuestros productos y servicios'
        reply = (
            f'Solo te puedo ayudar con temas de {brand_name}: {what_you_sell}, procesos, politicas y atencion de la organizacion. '
            'Si quieres, dime tu duda concreta y te ayudo dentro de ese contexto.'
        )
        return {
            'kind': 'unrelated_topic',
            'reason': 'asked_for_general_information_outside_business_scope',
            'reply': _apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
        }

    return _guard_out_of_scope_request(message_text, sales_ctx)


def _handle_affiliation_qualification_flow(*, message_text: str, conversation, sales_ctx: SalesContext) -> SalesAgentResult | None:
    if not _is_comfaguajira_scope(sales_ctx):
        return None

    metadata = {**(getattr(conversation, 'metadata', None) or {})}
    qualification = {**(metadata.get('qualification') or {})}
    active_flow = {**(metadata.get('active_flow') or {})}
    text = ' '.join((message_text or '').lower().split())

    if qualification.get('affiliate_status') and (
        qualification.get('affiliate_status') in {'particular', 'empresa_afiliada'}
        or qualification.get('affiliate_category')
        or qualification.get('affiliate_status') == 'afiliado_desconocido'
    ):
        return None

    if not active_flow and not _should_trigger_affiliation_flow(text):
        return None

    if not active_flow:
        pending_service = _detect_comfaguajira_service(text)
        flow_state = {
            'name': 'comfaguajira_affiliation',
            'step': 'ask_affiliation',
            'status': 'active',
            'data': {'pending_service': pending_service} if pending_service else {},
        }
        _persist_conversation_flow_state(conversation, metadata, flow_state, qualification)
        reply = (
            'Antes de darte el valor exacto o recomendarte el servicio correcto, necesito validar algo rapido: '
            'eres afiliado a Comfaguajira, empresa afiliada o particular?'
        )
        return SalesAgentResult(
            stage=STAGE_DISCOVERING,
            confidence=0.97,
            decision=DECISION_QUALIFY,
            recommended_actions=[SalesAction('collect_affiliation_status', {'flow': 'comfaguajira_affiliation'})],
            reply_text=_apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
            handoff=HandoffDecision(needed=False),
            buyer_profile=BuyerProfile(),
            context_used={'active_flow': 'comfaguajira_affiliation', 'flow_step': 'ask_affiliation'},
        )

    if active_flow.get('name') != 'comfaguajira_affiliation':
        return None

    step = active_flow.get('step') or 'ask_affiliation'
    flow_data = {**(active_flow.get('data') or {})}

    if step == 'ask_affiliation':
        parsed_status = _parse_affiliation_status(text)
        if not parsed_status:
            reply = (
                'Para orientarte bien necesito saber si eres afiliado, empresa afiliada o particular. '
                'Con eso te doy la ruta y tarifa mas cercana.'
            )
            return SalesAgentResult(
                stage=STAGE_DISCOVERING,
                confidence=0.95,
                decision=DECISION_QUALIFY,
                recommended_actions=[SalesAction('collect_affiliation_status', {'flow': 'comfaguajira_affiliation'})],
                reply_text=_apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
                handoff=HandoffDecision(needed=False),
                buyer_profile=BuyerProfile(),
                context_used={'active_flow': 'comfaguajira_affiliation', 'flow_step': 'ask_affiliation'},
            )

        if parsed_status == 'afiliado':
            flow_data['affiliate_status'] = 'afiliado'
            active_flow.update({'step': 'ask_category', 'status': 'active', 'data': flow_data})
            _persist_conversation_flow_state(conversation, metadata, active_flow, qualification)
            reply = 'Perfecto. Para darte el valor o subsidio correcto, sabes si tu categoria es A, B o C?'
            return SalesAgentResult(
                stage=STAGE_DISCOVERING,
                confidence=0.97,
                decision=DECISION_QUALIFY,
                recommended_actions=[SalesAction('collect_affiliate_category', {'flow': 'comfaguajira_affiliation'})],
                reply_text=_apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
                handoff=HandoffDecision(needed=False),
                buyer_profile=BuyerProfile(),
                context_used={'active_flow': 'comfaguajira_affiliation', 'flow_step': 'ask_category'},
            )

        qualification['affiliate_status'] = parsed_status
        if parsed_status == 'particular':
            qualification['affiliate_category'] = 'no_aplica'
        if parsed_status == 'empresa_afiliada':
            qualification['company_status'] = 'por_validar_aportes'
            qualification['affiliate_category'] = 'no_aplica'
        pending_service = flow_data.get('pending_service')
        if pending_service:
            next_flow = _begin_service_flow_state(pending_service, qualification)
            _persist_conversation_flow_state(conversation, metadata, next_flow, qualification)
            return SalesAgentResult(
                stage=STAGE_DISCOVERING,
                confidence=0.97,
                decision=DECISION_QUALIFY,
                recommended_actions=[SalesAction('start_service_flow', {'flow': next_flow['name']})],
                reply_text=_apply_brand_voice(_service_flow_prompt(next_flow), sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
                handoff=HandoffDecision(needed=False),
                buyer_profile=BuyerProfile(),
                context_used={'active_flow': next_flow['name'], 'flow_step': next_flow['step']},
            )
        active_flow.update({'step': 'done', 'status': 'completed', 'data': flow_data})
        _persist_conversation_flow_state(conversation, metadata, active_flow, qualification)
        reply = _qualification_completion_reply(parsed_status)
        return SalesAgentResult(
            stage=STAGE_DISCOVERING,
            confidence=0.97,
            decision=DECISION_QUALIFY,
            recommended_actions=[SalesAction('qualification_completed', {'flow': 'comfaguajira_affiliation'})],
            reply_text=_apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
            handoff=HandoffDecision(needed=False),
            buyer_profile=BuyerProfile(),
            context_used={'active_flow': 'comfaguajira_affiliation', 'flow_step': 'completed'},
        )

    if step == 'ask_category':
        parsed_category = _parse_affiliate_category(text)
        if not parsed_category:
            reply = (
                'Si la conoces, dime si eres categoria A, B o C. '
                'Si no la recuerdas, dime "no se" y te oriento igual con la validacion.'
            )
            return SalesAgentResult(
                stage=STAGE_DISCOVERING,
                confidence=0.95,
                decision=DECISION_QUALIFY,
                recommended_actions=[SalesAction('collect_affiliate_category', {'flow': 'comfaguajira_affiliation'})],
                reply_text=_apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
                handoff=HandoffDecision(needed=False),
                buyer_profile=BuyerProfile(),
                context_used={'active_flow': 'comfaguajira_affiliation', 'flow_step': 'ask_category'},
            )

        qualification['affiliate_status'] = 'afiliado' if parsed_category != 'desconocida' else 'afiliado_desconocido'
        qualification['affiliate_category'] = parsed_category
        completed_data = {**flow_data, 'affiliate_category': parsed_category}
        pending_service = completed_data.get('pending_service')
        if pending_service:
            next_flow = _begin_service_flow_state(pending_service, qualification)
            _persist_conversation_flow_state(conversation, metadata, next_flow, qualification)
            return SalesAgentResult(
                stage=STAGE_DISCOVERING,
                confidence=0.97,
                decision=DECISION_QUALIFY,
                recommended_actions=[SalesAction('start_service_flow', {'flow': next_flow['name']})],
                reply_text=_apply_brand_voice(_service_flow_prompt(next_flow), sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
                handoff=HandoffDecision(needed=False),
                buyer_profile=BuyerProfile(),
                context_used={'active_flow': next_flow['name'], 'flow_step': next_flow['step']},
            )
        active_flow.update({'step': 'done', 'status': 'completed', 'data': completed_data})
        _persist_conversation_flow_state(conversation, metadata, active_flow, qualification)
        reply = (
            'Perfecto, ya tengo esa validacion. Ahora si, cuentame que servicio necesitas y te lo explico con la tarifa o condicion mas cercana a tu caso.'
        )
        return SalesAgentResult(
            stage=STAGE_DISCOVERING,
            confidence=0.97,
            decision=DECISION_QUALIFY,
            recommended_actions=[SalesAction('qualification_completed', {'flow': 'comfaguajira_affiliation'})],
            reply_text=_apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
            handoff=HandoffDecision(needed=False),
            buyer_profile=BuyerProfile(),
            context_used={'active_flow': 'comfaguajira_affiliation', 'flow_step': 'completed'},
        )

    return None


def _handle_comfaguajira_service_flow(*, message_text: str, conversation, sales_ctx: SalesContext) -> SalesAgentResult | None:
    if not _is_comfaguajira_scope(sales_ctx):
        return None

    metadata = {**(getattr(conversation, 'metadata', None) or {})}
    qualification = {**(metadata.get('qualification') or {})}
    active_flow = {**(metadata.get('active_flow') or {})}
    text = ' '.join((message_text or '').lower().split())
    service_flows = {
        'comfaguajira_nutrition_quote',
        'comfaguajira_education_quote',
        'comfaguajira_space_booking',
        'comfaguajira_theater_booking',
    }

    if active_flow.get('name') in service_flows and active_flow.get('status') != 'completed':
        flow_state = {**active_flow, 'data': {**(active_flow.get('data') or {})}}
    else:
        if not _qualification_ready(qualification):
            return None
        service_key = _detect_comfaguajira_service(text)
        if not service_key:
            return None
        flow_state = _begin_service_flow_state(service_key, qualification)
        _persist_conversation_flow_state(conversation, metadata, flow_state, qualification)
        return SalesAgentResult(
            stage=STAGE_DISCOVERING,
            confidence=0.96,
            decision=DECISION_QUALIFY,
            recommended_actions=[SalesAction('start_service_flow', {'flow': flow_state['name']})],
            reply_text=_apply_brand_voice(_service_flow_prompt(flow_state), sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
            handoff=HandoffDecision(needed=False),
            buyer_profile=BuyerProfile(),
            context_used={'active_flow': flow_state['name'], 'flow_step': flow_state['step']},
        )

    updated_state, reply = _advance_service_flow(flow_state, text, qualification)
    if not reply:
        return None
    _persist_conversation_flow_state(conversation, metadata, updated_state, qualification)
    return SalesAgentResult(
        stage=STAGE_DISCOVERING if updated_state.get('status') != 'completed' else STAGE_CONSIDERING,
        confidence=0.97,
        decision=DECISION_QUALIFY if updated_state.get('status') != 'completed' else DECISION_RECOMMEND,
        recommended_actions=[SalesAction('service_flow_progress', {'flow': updated_state['name'], 'step': updated_state['step']})],
        reply_text=_apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
        handoff=HandoffDecision(needed=False),
        buyer_profile=BuyerProfile(),
        context_used={'active_flow': updated_state['name'], 'flow_step': updated_state['step'], 'flow_status': updated_state.get('status')},
    )


def _is_comfaguajira_scope(sales_ctx: SalesContext) -> bool:
    org_slug = (sales_ctx.business.org_slug or '').lower()
    brand_name = (sales_ctx.brand.brand_name or sales_ctx.business.org_name or '').lower()
    return 'comfaguajira' in org_slug or 'comfaguajira' in brand_name


def _qualification_ready(qualification: dict[str, Any]) -> bool:
    status = qualification.get('affiliate_status')
    category = qualification.get('affiliate_category')
    return bool(status and (status in {'particular', 'empresa_afiliada', 'afiliado_desconocido'} or category))


def _detect_comfaguajira_service(text: str) -> str | None:
    if any(token in text for token in ('teatro', 'akuaipaa', 'evento cultural', 'evento empresarial', 'evento comercial')):
        return 'theater'
    if any(token in text for token in ('auditorio', 'aula', 'patio de tertulias', 'alquiler de espacio', 'alquilar espacio', 'espacio', 'espacios')):
        return 'space'
    if any(token in text for token in ('crecer sano', 'nutricion', 'nutricion', 'formula lactea', 'fórmula láctea', 'consulta nutricional', 'formula')):
        return 'nutrition'
    if any(token in text for token in ('educacion', 'educación', 'curso', 'diplomado', 'tecnico', 'técnico', 'seminario', 'colegio')):
        return 'education'
    return None


def _begin_service_flow_state(service_key: str, qualification: dict[str, Any]) -> dict[str, Any]:
    if service_key == 'theater':
        return {'name': 'comfaguajira_theater_booking', 'step': 'ask_event_type', 'status': 'active', 'data': {'service_key': service_key, 'qualification': qualification}}
    if service_key == 'space':
        return {'name': 'comfaguajira_space_booking', 'step': 'ask_space_type', 'status': 'active', 'data': {'service_key': service_key, 'qualification': qualification}}
    if service_key == 'nutrition':
        return {'name': 'comfaguajira_nutrition_quote', 'step': 'ask_child_age', 'status': 'active', 'data': {'service_key': service_key, 'qualification': qualification}}
    return {'name': 'comfaguajira_education_quote', 'step': 'ask_education_line', 'status': 'active', 'data': {'service_key': service_key, 'qualification': qualification}}


def _service_flow_prompt(flow_state: dict[str, Any]) -> str:
    prompts = {
        'comfaguajira_theater_booking': 'Perfecto. Para cotizar el Teatro Akuaipaa, dime que tipo de evento vas a realizar: educativo, cultural, empresarial o comercial.',
        'comfaguajira_space_booking': 'Perfecto. Para orientarte con el alquiler, dime que espacio necesitas: aula, auditorio o patio de tertulias.',
        'comfaguajira_nutrition_quote': 'Perfecto. Para revisar Crecer Sano, que edad tiene el nino o la nina?',
        'comfaguajira_education_quote': 'Perfecto. Para orientarte mejor, dime si buscas educacion informal, tecnica o formal.',
    }
    return prompts.get(flow_state.get('name', ''), 'Perfecto. Cuentame un poco mas y te oriento.')


def _advance_service_flow(flow_state: dict[str, Any], text: str, qualification: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    name = flow_state.get('name')
    data = {**(flow_state.get('data') or {})}
    step = flow_state.get('step')

    if name == 'comfaguajira_theater_booking':
        if step == 'ask_event_type':
            event_type = _parse_theater_event_type(text)
            if not event_type:
                return flow_state, 'Para orientarte bien con el teatro, dime si el evento es educativo, cultural, empresarial o comercial.'
            data['event_type'] = event_type
            return {**flow_state, 'step': 'ask_schedule', 'data': data}, 'Listo. Ese evento lo vas a necesitar en horario diurno o nocturno?'
        if step == 'ask_schedule':
            schedule = _parse_schedule(text)
            if not schedule:
                return flow_state, 'Dime si lo necesitas en horario diurno o nocturno y te sigo ubicando el valor.'
            data['schedule'] = schedule
            return {**flow_state, 'step': 'ask_duration', 'data': data}, 'Perfecto. Cuanto tiempo necesitas: 4, 6 u 8 horas?'
        if step == 'ask_duration':
            duration = _parse_hours_choice(text, [4, 6, 8])
            if not duration:
                return flow_state, 'Para cerrarte la orientacion del teatro, dime si lo necesitas por 4, 6 u 8 horas.'
            data['duration_hours'] = duration
            return (
                {**flow_state, 'step': 'done', 'status': 'completed', 'data': data},
                _build_theater_quote_reply(data, qualification),
            )

    if name == 'comfaguajira_space_booking':
        if step == 'ask_space_type':
            space_type = _parse_space_type(text)
            if not space_type:
                return flow_state, 'Para cotizarte bien el espacio, dime si buscas aula, auditorio o patio de tertulias.'
            data['space_type'] = space_type
            return {**flow_state, 'step': 'ask_duration', 'data': data}, 'Perfecto. Lo necesitas por 4 u 8 horas?'
        if step == 'ask_duration':
            duration = _parse_hours_choice(text, [4, 8])
            if not duration:
                return flow_state, 'Dime si el espacio lo necesitas por 4 u 8 horas y te doy la referencia.'
            data['duration_hours'] = duration
            return (
                {**flow_state, 'step': 'done', 'status': 'completed', 'data': data},
                _build_space_quote_reply(data, qualification),
            )

    if name == 'comfaguajira_nutrition_quote':
        if step == 'ask_child_age':
            age = _parse_child_age(text)
            if age is None:
                return flow_state, 'Para Crecer Sano necesito saber la edad del nino o la nina, aunque sea aproximada.'
            data['child_age_months'] = age
            return {**flow_state, 'step': 'ask_interest', 'data': data}, 'Gracias. Buscas consulta nutricional, formulas lacteas o ambos?'
        if step == 'ask_interest':
            interest = _parse_nutrition_interest(text)
            if not interest:
                return flow_state, 'Dime si te interesa consulta, formulas lacteas o ambos y te doy la orientacion mas cercana.'
            data['interest'] = interest
            return (
                {**flow_state, 'step': 'done', 'status': 'completed', 'data': data},
                _build_nutrition_quote_reply(data, qualification),
            )

    if name == 'comfaguajira_education_quote':
        if step == 'ask_education_line':
            education_line = _parse_education_line(text)
            if not education_line:
                return flow_state, 'Para aterrizarlo bien, dime si buscas educacion informal, tecnica o formal.'
            data['education_line'] = education_line
            return {**flow_state, 'step': 'ask_education_need', 'data': data}, 'Perfecto. Ahora dime el programa, nivel o la duracion que te interesa.'
        if step == 'ask_education_need':
            need = text.strip()
            if len(need) < 3:
                return flow_state, 'Necesito un poco mas de detalle: por ejemplo curso de 20 horas, tecnico laboral o colegio.'
            data['education_need'] = need
            return (
                {**flow_state, 'step': 'done', 'status': 'completed', 'data': data},
                _build_education_quote_reply(data, qualification),
            )

    return flow_state, None


def _parse_theater_event_type(text: str) -> str | None:
    if 'educat' in text:
        return 'educativo'
    if 'cultural' in text:
        return 'cultural'
    if 'empresar' in text:
        return 'empresarial'
    if 'comercial' in text:
        return 'comercial'
    return None


def _parse_schedule(text: str) -> str | None:
    if 'nocturn' in text or 'noche' in text:
        return 'nocturno'
    if 'diurn' in text or 'dia' in text or 'día' in text:
        return 'diurno'
    return None


def _parse_hours_choice(text: str, allowed: list[int]) -> int | None:
    for hours in allowed:
        if f'{hours} horas' in text or f'{hours} hora' in text or re.search(rf'\b{hours}\b', text):
            return hours
    return None


def _parse_space_type(text: str) -> str | None:
    if 'aula' in text:
        return 'aula'
    if 'auditorio' in text:
        return 'auditorio'
    if 'patio' in text:
        return 'patio de tertulias'
    return None


def _parse_child_age(text: str) -> int | None:
    match = re.search(r'(\d{1,2})', text)
    if not match:
        return None
    value = int(match.group(1))
    if any(token in text for token in ('mes', 'meses')):
        return value
    if any(token in text for token in ('ano', 'años', 'anos', 'año')):
        return value * 12
    return value * 12 if value <= 14 else None


def _parse_nutrition_interest(text: str) -> str | None:
    has_consulta = 'consulta' in text
    has_formula = 'formula' in text or 'fórmula' in text
    if has_consulta and has_formula:
        return 'ambos'
    if has_consulta:
        return 'consulta'
    if has_formula:
        return 'formula'
    if 'ambos' in text:
        return 'ambos'
    return None


def _parse_education_line(text: str) -> str | None:
    if any(token in text for token in ('informal', 'curso', 'seminario', 'diplomado', 'congreso', 'taller')):
        return 'informal'
    if any(token in text for token in ('tecnica', 'técnica', 'tecnico', 'técnico', 'laboral')):
        return 'tecnica'
    if any(token in text for token in ('formal', 'colegio', 'preescolar', 'primaria', 'secundaria')):
        return 'formal'
    return None


def _build_theater_quote_reply(data: dict[str, Any], qualification: dict[str, Any]) -> str:
    duration = data.get('duration_hours')
    schedule = data.get('schedule')
    ranges = {
        4: {'diurno': (1057400, 1057400), 'nocturno': (1905000, 1905000), 'general': (1057400, 1905000)},
        6: {'general': (1744800, 3142000)},
        8: {'general': (2114800, 3808000)},
    }
    lower, upper = ranges.get(duration, {}).get(schedule) or ranges.get(duration, {}).get('general', (0, 0))
    qualification_hint = _qualification_hint(qualification)
    range_text = f'desde ${lower:,.0f} hasta ${upper:,.0f}' if lower != upper else f'${lower:,.0f}'
    return (
        f'Perfecto. Para el Teatro Akuaipaa en {duration} horas, la referencia que te puedo dar es {range_text}. '
        f'Aplica para evento {data.get("event_type")} y puede moverse por horario, fines de semana y tu condicion como {qualification_hint}. '
        'La reserva pide 50% de anticipo, no se permiten alimentos y el tiempo adicional se cobra. Si quieres, te ayudo con el siguiente paso o con una fecha tentativa.'
    )


def _build_space_quote_reply(data: dict[str, Any], qualification: dict[str, Any]) -> str:
    duration = data.get('duration_hours')
    range_map = {4: (62000, 441000), 8: (124000, 883000)}
    lower, upper = range_map.get(duration, (0, 0))
    qualification_hint = _qualification_hint(qualification)
    return (
        f'Para {data.get("space_type")} por {duration} horas, la referencia actual va desde ${lower:,.0f} hasta ${upper:,.0f}. '
        f'El valor final depende del espacio exacto y de si aplicas como {qualification_hint}. Incluye aire, sillas, tablero, marcadores, vigilancia e IVA. '
        'Si es tarifa afiliada, pueden pedir cedula; si es empresa afiliada, debe estar al dia en aportes.'
    )


def _build_nutrition_quote_reply(data: dict[str, Any], qualification: dict[str, Any]) -> str:
    category = (qualification.get('affiliate_category') or '').upper()
    subsidized = category in {'A', 'B'}
    interest = data.get('interest')
    parts: list[str] = []
    if interest in {'consulta', 'ambos'}:
        parts.append('la consulta nutricional queda en $13,000' if subsidized else 'la consulta nutricional tiene referencia de $35,324')
    if interest in {'formula', 'ambos'}:
        if subsidized:
            parts.append('las formulas lacteas pueden tener subsidio hasta del 75%, con precios desde $32,900')
        else:
            parts.append('las formulas lacteas manejan valores desde $32,900 hasta mas de $300,000 segun producto')
    age_months = data.get('child_age_months')
    age_label = f'{age_months} meses' if age_months and age_months < 24 else f'{round((age_months or 0) / 12, 1)} anos'
    return (
        f'Perfecto. Para Crecer Sano y una edad aproximada de {age_label}, te orientaria asi: '
        + '; '.join(parts)
        + '. Este programa aplica para ninos de 6 meses a 14 anos. Si quieres, te indico que dato te pedirian para dejarlo encaminado.'
    )


def _build_education_quote_reply(data: dict[str, Any], qualification: dict[str, Any]) -> str:
    line = data.get('education_line')
    need = (data.get('education_need') or '').lower()
    category = (qualification.get('affiliate_category') or '').upper()
    if line == 'formal':
        return (
            'En educacion formal, la matricula se mueve desde $393,400 hasta $897,000 y la pension mensual desde $112,000 hasta $364,000. '
            f'La tarifa final depende del nivel y de tu categoria actual{f" {category}" if category else ""}. Si me dices si es preescolar, primaria o secundaria, te la cierro mas.'
        )
    if line == 'tecnica':
        if any(token in need for token in ('semestre', 'semestral')):
            return 'Para tecnicos laborales, el semestre arranca desde $182,400 en categoria A. Tambien puede manejarse pago trimestral desde $91,200. Ten presente que puede haber inscripcion, certificados y derecho a grado.'
        return (
            'En formacion laboral, el valor depende del programa y modalidad. Como referencia: tecnicos laborales desde $182,400 por semestre en categoria A, '
            'diplomados tecnicos de 80 horas desde $129,500 y de 120 horas desde $183,100. Ademas pueden aplicar inscripcion, certificados y derecho a grado.'
        )
    informal_map = {
        1: 'Taller de 1 hora: desde $0 para categorias A y B, y $10,300 para C',
        4: 'Taller de 4 horas: desde $25,200',
        8: 'Seminario de 8 horas: desde $41,300',
        20: 'Curso de 20 horas: desde $98,800',
        40: 'Curso de 40 horas: desde $180,600',
        60: 'Curso productivo de 60 horas: desde $226,800',
        80: 'Diplomado o curso productivo de 80 horas: desde $283,400 o $586,500 segun modalidad',
        120: 'Diplomado de 120 horas: desde $862,000',
        230: 'Diplomado de 230 horas: desde $1,425,400',
    }
    detected_hours = _parse_hours_choice(need, list(informal_map.keys()))
    if detected_hours and detected_hours in informal_map:
        return informal_map[detected_hours] + '. Normalmente incluye docente, salon y en algunos casos refrigerio.'
    return (
        'En educacion informal el valor cambia por duracion y categoria. Por ejemplo, un curso de 20 horas arranca en $98,800, uno de 40 horas en $180,600 y un diplomado de 80 horas desde $586,500. '
        'Si me dices cuantas horas o que tipo de formacion buscas, te lo cierro mejor.'
    )


def _qualification_hint(qualification: dict[str, Any]) -> str:
    status = qualification.get('affiliate_status')
    category = qualification.get('affiliate_category')
    if status == 'empresa_afiliada':
        return 'empresa afiliada'
    if status == 'particular':
        return 'particular'
    if category and category not in {'no_aplica', 'desconocida'}:
        return f'afiliado categoria {category}'
    if status == 'afiliado_desconocido':
        return 'afiliado por validar categoria'
    return 'tu tipo de usuario'


def _should_trigger_affiliation_flow(text: str) -> bool:
    trigger_terms = (
        'precio', 'cuanto cuesta', 'cuánto cuesta', 'valor', 'tarifa', 'subsidio',
        'credito', 'crédito', 'nutricion', 'nutrición', 'educacion', 'educación',
        'colegio', 'teatro', 'espacio', 'espacios', 'alquiler', 'afiliado',
        'categoria', 'categoría', 'inscripcion', 'inscripción', 'certificado',
        'quiero', 'necesito', 'me interesa',
    )
    return any(term in text for term in trigger_terms)


def _parse_affiliation_status(text: str) -> str | None:
    if any(token in text for token in ('empresa afiliada', 'somos empresa', 'empresa', 'empresarial')):
        return 'empresa_afiliada'
    if any(token in text for token in ('particular', 'no afiliado', 'no soy afiliado', 'no estoy afiliado', 'no pertenezco')):
        return 'particular'
    if any(token in text for token in ('si soy afiliado', 'soy afiliado', 'afiliado', 'estoy afiliado')):
        return 'afiliado'
    if any(token in text for token in ('no se', 'no sé', 'no estoy seguro')):
        return 'afiliado_desconocido'
    return None


def _parse_affiliate_category(text: str) -> str | None:
    if any(token in text for token in ('categoria a', 'categoría a', 'cat a', 'soy a')):
        if 'categoria b' not in text and 'categoria c' not in text:
            return 'A'
    if any(token in text for token in ('categoria b', 'categoría b', 'cat b', 'soy b')):
        return 'B'
    if any(token in text for token in ('categoria c', 'categoría c', 'cat c', 'soy c')):
        return 'C'
    if any(token in text for token in ('no se', 'no sé', 'no la se', 'no la sé', 'no recuerdo')):
        return 'desconocida'
    return None


def _qualification_completion_reply(parsed_status: str) -> str:
    if parsed_status == 'empresa_afiliada':
        return 'Perfecto. Tomo que es para empresa afiliada. En algunos servicios toca validar que la empresa este al dia en aportes, pero ya te puedo orientar mejor. Que servicio necesitas?'
    if parsed_status == 'particular':
        return 'Perfecto. Tomo que es para particular. Te ayudo con el servicio y te aclaro desde ya cuando una tarifa subsidiada aplica solo para afiliados. Que servicio necesitas?'
    return 'Perfecto. Si no tienes clara tu afiliacion o categoria, te orientare con la regla general y te dire cuando haga falta validarla. Que servicio necesitas?'


def _persist_conversation_flow_state(conversation, metadata: dict[str, Any], active_flow: dict[str, Any], qualification: dict[str, Any]) -> None:
    metadata = {**metadata}
    metadata['active_flow'] = active_flow
    metadata['qualification'] = qualification
    conversation.metadata = metadata
    conversation.save(update_fields=['metadata', 'updated_at'])

    contact = getattr(conversation, 'contact', None)
    if contact:
        contact.metadata = {
            **(contact.metadata or {}),
            'qualification': qualification,
        }
        contact.save(update_fields=['metadata', 'updated_at'])


def _parse_affiliate_category(text: str) -> str | None:
    normalized = re.sub(r'[^a-záéíóúüñ0-9\s]', ' ', (text or '').lower()).strip()
    if normalized in {'a', 'categoria a', 'cat a', 'soy a'}:
        return 'A'
    if normalized in {'b', 'categoria b', 'cat b', 'soy b'}:
        return 'B'
    if normalized in {'c', 'categoria c', 'cat c', 'soy c'}:
        return 'C'
    if any(token in normalized for token in ('categoria a', 'cat a', 'soy a')):
        if 'categoria b' not in normalized and 'categoria c' not in normalized:
            return 'A'
    if any(token in normalized for token in ('categoria b', 'cat b', 'soy b')):
        return 'B'
    if any(token in normalized for token in ('categoria c', 'cat c', 'soy c')):
        return 'C'
    if any(token in normalized for token in ('no se', 'no la se', 'no recuerdo')):
        return 'desconocida'
    return None


def _persist_conversation_flow_state(conversation, metadata: dict[str, Any], active_flow: dict[str, Any], qualification: dict[str, Any]) -> None:
    metadata = {**metadata}
    if active_flow and active_flow.get('status') != 'completed':
        metadata['active_flow'] = active_flow
    else:
        metadata.pop('active_flow', None)
    metadata['qualification'] = qualification
    conversation.metadata = metadata
    conversation.save(update_fields=['metadata', 'updated_at'])

    contact = getattr(conversation, 'contact', None)
    if contact:
        contact.metadata = {
            **(contact.metadata or {}),
            'qualification': qualification,
        }
        contact.save(update_fields=['metadata', 'updated_at'])


def _guard_out_of_scope_brand_query(message_text: str, sales_ctx: SalesContext) -> str | None:
    text = ' '.join((message_text or '').lower().split())
    if not text:
        return None

    asks_for_identity = any(
        signal in text for signal in (
            'que es ',
            'qué es ',
            'quien es ',
            'quién es ',
            'que hace ',
            'qué hace ',
            'informacion de ',
            'información de ',
            'hablame de ',
            'háblame de ',
            'cuentame de ',
            'cuéntame de ',
        )
    )
    if not asks_for_identity:
        return None

    allowed_terms = _build_scope_terms(sales_ctx)

    referenced_terms = {
        token.strip()
        for token in re.split(r'[^a-z0-9áéíóúñ]+', text)
        if len(token.strip()) >= 4
    }
    ignored_terms = {
        'que', 'qué', 'quien', 'quién', 'hace', 'sobre', 'marca', 'tienda', 'producto',
        'productos', 'info', 'informacion', 'información', 'hablame', 'háblame', 'cuentame',
        'cuéntame', 'como', 'cómo', 'para', 'esta', 'este', 'tienen',
    }
    candidate_terms = referenced_terms - ignored_terms
    external_terms = [term for term in candidate_terms if term not in allowed_terms]
    if not external_terms:
        return None

    brand_name = sales_ctx.brand.brand_name or sales_ctx.business.org_name or 'la marca'
    what_you_sell = sales_ctx.business.what_you_sell or 'nuestros productos'
    reply = (
        f'Solo te puedo ayudar con informacion de {brand_name} y de {what_you_sell}. '
        f'Si quieres, te cuento sobre un producto, disponibilidad o cual te conviene mas dentro de {brand_name}.'
    )
    return _apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING)


def _build_scope_terms(sales_ctx: SalesContext) -> set[str]:
    allowed_terms = {
        chunk.strip()
        for raw in (
            sales_ctx.brand.brand_name,
            sales_ctx.business.org_name,
            sales_ctx.business.what_you_sell,
            sales_ctx.business.who_you_sell_to,
            sales_ctx.business.industry,
            sales_ctx.business.mission,
        )
        for chunk in re.split(r'[^a-z0-9áéíóúñ]+', (raw or '').lower())
        if len(chunk.strip()) >= 4
    }
    for product in sales_ctx.catalog_snapshot[:8]:
        for raw in (product.get('title', ''), product.get('brand', ''), product.get('category', '')):
            for chunk in re.split(r'[^a-z0-9áéíóúñ]+', (raw or '').lower()):
                if len(chunk.strip()) >= 4:
                    allowed_terms.add(chunk.strip())
    for item in sales_ctx.knowledge_snapshot[:8]:
        for raw in (item.get('title', ''), item.get('category', '')):
            for chunk in re.split(r'[^a-z0-9áéíóúñ]+', (raw or '').lower()):
                if len(chunk.strip()) >= 4:
                    allowed_terms.add(chunk.strip())
    return allowed_terms


def _llm_reply(
    *,
    message_text: str,
    stage: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    stock_info: dict[str, Any] | None,
    promotions: list[dict[str, Any]],
    sales_ctx: SalesContext,
    router_decision,
    settings,
    conversation,
) -> str | None:
    try:
        import openai

        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        model = getattr(settings, 'OPENAI_SALES_MODEL', getattr(settings, 'OPENAI_MODEL', 'gpt-4o'))
        if router_decision and router_decision.model_name:
            model = router_decision.model_name

        import time as _time
        t0 = _time.monotonic()
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': _build_system_prompt(sales_ctx)},
                {'role': 'system', 'content': _build_context_block(
                    stage=stage,
                    buyer=buyer,
                    products=products,
                    stock_info=stock_info,
                    promotions=promotions,
                    sales_ctx=sales_ctx,
                    conversation=conversation,
                )},
                {'role': 'user', 'content': message_text},
            ],
            max_tokens=180,
            temperature=0.6,
        )
        latency_ms = int((_time.monotonic() - t0) * 1000)
        try:
            from apps.ai_engine.usage_tracker import track
            usage = completion.usage
            track(
                organization_id=str(sales_ctx.business.org_id),
                feature='sales_agent',
                model=model,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
            )
        except Exception:
            pass
        return completion.choices[0].message.content or None
    except Exception as exc:
        logger.warning('sales_agent_llm_error', error=str(exc))
        return None


def _heuristic_reply(
    *,
    message_text: str,
    stage: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    stock_info: dict[str, Any] | None,
    promotions: list[dict[str, Any]],
    sales_ctx: SalesContext,
) -> str:
    text = message_text.lower()
    biz_ctx = sales_ctx.business
    brand_ctx = sales_ctx.brand
    playbook = sales_ctx.playbook
    rules = sales_ctx.commerce_rules
    product_lines = _build_product_lines(products, sales_ctx.business.org_slug)

    # Purchase-intent stages take priority over generic objection handling.
    # A price question in INTENT_TO_BUY is a purchase signal, not a price objection.
    # A payment failure in CHECKOUT_BLOCKED is more specific than any inferred objection.
    if stage == STAGE_INTENT_TO_BUY:
        reply = _reply_intent_to_buy(text, buyer, products, product_lines, stock_info, biz_ctx)
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)
    if stage == STAGE_CHECKOUT_BLOCKED:
        reply = f'Entiendo que hubo un inconveniente al pagar. Puedes intentar con {", ".join(biz_ctx.payment_methods[:2])}. Si me dices que paso, te ayudo a destrabar la compra.'
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)

    if buyer.objection == 'price':
        reply = (
            f'Tenemos una promocion activa que puede ayudarte: {promotions[0]}. Si quieres, te digo si encaja con lo que buscas.'
            if promotions else
            'Entiendo que el precio importa. Si me dices para que lo necesitas, te recomiendo la opcion con mejor balance entre valor y precio.'
        )
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)

    if buyer.objection == 'shipping':
        reply = f'El envio cubre {biz_ctx.shipping_coverage} con tiempo estimado de {biz_ctx.shipping_avg_days}. Si te encaja ese tiempo, te ayudo a elegir la mejor opcion disponible.'
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)

    if buyer.objection == 'availability':
        reply = (
            'Ese producto esta agotado ahora mismo. Puedo proponerte una alternativa disponible para que no pierdas tiempo.'
            if stock_info and not stock_info.get('any_in_stock')
            else 'Puedo ayudarte a validar el stock exacto, pero necesito saber que producto o variante te interesa.'
        )
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)

    if buyer.objection == 'trust':
        reply = 'Trabajamos con informacion verificada.'
        if rules.return_policy_summary:
            reply += f' {rules.return_policy_summary}.'
        elif biz_ctx.has_returns_policy:
            reply += f' Tienes {biz_ctx.returns_window_days} dias para devolucion si aplica.'
        reply += ' Si quieres, te recomiendo la opcion mas segura para tu caso.'
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)

    if stage == STAGE_CONSIDERING:
        reply = _reply_considering(buyer, products, product_lines)
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)
    if stage == STAGE_FOLLOW_UP_NEEDED:
        reply = _reply_follow_up_needed(buyer, products, promotions)
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)
    if stage == STAGE_DISCOVERING:
        reply = _reply_discovering(buyer, products, product_lines)
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)
    return _apply_brand_voice('Cuantame que necesitas y te ayudo a decidir la mejor opcion para comprar.', brand_ctx, playbook, stage)


def _reply_intent_to_buy(
    text: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    product_lines: str,
    stock_info: dict[str, Any] | None,
    biz_ctx: BusinessContext,
) -> str:
    if any(token in text for token in ('precio', 'cuanto', 'vale', 'cuesta')):
        if products and products[0].get('min_price'):
            product = products[0]
            stock_msg = ' Hay disponibilidad ahora.' if product.get('any_in_stock') else ' Estoy revisando disponibilidad.'
            suffix = ' Si te cuadra, lo dejamos listo hoy?' if buyer.urgency == 'immediate' else ' Si quieres, te cuento si esta te conviene o si hay otra mejor.'
            return f'{product["title"]} esta desde ${product["min_price"]:,.0f}.{stock_msg}{suffix}'
        return 'Te ayudo con el precio. Dime que producto o uso tienes en mente y te recomiendo algo puntual.'
    if any(token in text for token in ('envio', 'llega', 'entrega', 'demora', 'delivery')):
        close = ' Si te sirve ese tiempo, lo dejamos pedido hoy?' if buyer.urgency == 'immediate' else ' Si quieres, revisamos que opcion te conviene mas segun entrega.'
        return f'Hacemos envios a {biz_ctx.shipping_coverage}, con tiempo estimado de {biz_ctx.shipping_avg_days}.{close}'
    if any(token in text for token in ('pago', 'pagar', 'tarjeta', 'transferencia', 'efectivo')):
        return f'Aceptamos {", ".join(biz_ctx.payment_methods)}. Si ya tienes una opcion elegida, te guio con el siguiente paso.'
    if any(token in text for token in ('stock', 'disponible', 'hay', 'tienen')):
        if stock_info:
            return 'Si, tenemos disponibilidad. Si quieres, avanzamos con la opcion que mejor te encaje.' if stock_info.get('any_in_stock') else 'Ese producto esta agotado actualmente. Puedo proponerte otra opcion disponible si te sirve.'
        if products:
            return f'{products[0]["title"]} esta disponible. Para recomendarte bien, dime cuantas unidades necesitas.'
        return 'Te ayudo a validar disponibilidad, pero necesito saber de cual producto se trata.'
    if product_lines:
        return f'Estas son las opciones disponibles:{product_lines} {"Si una te encaja, avanzamos hoy?" if buyer.urgency == "immediate" else "Cual se acerca mas a lo que buscas?"}'
    return 'Perfecto. Si me dices para que lo quieres o que presupuesto tienes, te propongo algo concreto.'


def _reply_considering(buyer: BuyerProfile, products: list[dict[str, Any]], product_lines: str) -> str:
    if len(products) >= 2:
        first = products[0]
        second = products[1]
        first_price = f'${first["min_price"]:,.0f}' if first.get('min_price') else 'precio a consultar'
        second_price = f'${second["min_price"]:,.0f}' if second.get('min_price') else 'precio a consultar'
        recommendation = first['title'] if buyer.priority == 'price' else second['title']
        return (
            f'{first["title"]}: {first_price}. {second["title"]}: {second_price}. '
            f'Si priorizas {"precio" if buyer.priority == "price" else "calidad"}, yo me iria por {recommendation}. Si quieres, te digo rapido por que.'
        )
    if product_lines:
        return f'Aqui tienes las opciones:{product_lines} Que te pesa mas para decidir: precio, calidad o entrega?'
    return 'Cuentame que estas comparando y te ayudo a elegir sin darte vueltas.'


def _reply_follow_up_needed(
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
) -> str:
    if products:
        primary = products[0]
        price_label = f' por ${primary["min_price"]:,.0f}' if primary.get('min_price') else ''
        promo_line = ''
        if promotions:
            promo_line = f' Ademas, ahora mismo tenemos {promotions[0]}.'
        if buyer.priority == 'price':
            return (
                f'Tranquilo, te dejo ubicada la opcion que mejor balance tiene en precio: {primary["title"]}{price_label}.{promo_line} '
            'Dime solo una cosa: prefieres irte por algo mas economico o por algo que te dure mas?'
        )
        if buyer.urgency in ('immediate', 'this_week'):
            return (
                f'Todo bien. Para no hacerte perder tiempo, la opcion que veo mas alineada es {primary["title"]}{price_label}.{promo_line} '
                'Si quieres, te confirmo en un mensaje corto si esta te conviene o si es mejor irse por otra.'
            )
        return (
            f'Claro. Por ahora la opcion que mejor encaja es {primary["title"]}{price_label}.{promo_line} '
            'Si te sirve, resolvemos lo principal: buscas algo mas economico o algo mas durable?'
        )
    return (
        'Sin problema. Dime que te frena mas para decidir: precio, entrega o no tener claro cual te conviene. '
        'Con eso te respondo puntual y sin darte vueltas.'
    )


def _reply_discovering(buyer: BuyerProfile, products: list[dict[str, Any]], product_lines: str) -> str:
    if buyer.style == 'direct' and products:
        return f'Encontre estas opciones:{product_lines} Si quieres, te digo cual te conviene mas segun lo que buscas.'
    if products:
        return f'Tenemos estas opciones disponibles:{product_lines} Es para ti, para regalo o para algo puntual?'
    return 'Hola, que andas buscando? Si me dices para que lo quieres, te recomiendo algo concreto.'


def _avoid_consecutive_repeat(
    *,
    reply: str,
    conversation,
    message_text: str,
    stage: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
) -> str:
    normalized_reply = ' '.join((reply or '').split()).strip().lower()
    if not normalized_reply or conversation is None:
        return reply

    try:
        recent_messages = list(conversation.messages.order_by('-timestamp')[:4])
    except Exception:
        return reply

    last_bot = next((item for item in recent_messages if getattr(item, 'role', '') == 'bot' and getattr(item, 'content', '')), None)
    last_user = next((item for item in recent_messages if getattr(item, 'role', '') == 'user' and getattr(item, 'content', '')), None)
    last_bot_text = ' '.join((getattr(last_bot, 'content', '') or '').split()).strip().lower()
    current_user_text = ' '.join((message_text or '').split()).strip().lower()
    last_user_text = ' '.join((getattr(last_user, 'content', '') or '').split()).strip().lower()

    if normalized_reply != last_bot_text:
        return reply

    if current_user_text in {'es para mi', 'para mi', 'es mío', 'es mio'} and products:
        first = products[0]
        return (
            f'Perfecto. Entonces te ubico rapido: de lo que te mostre, {first["title"]} pinta bien para uso personal. '
            'Te va mejor que te guie por set, talla o color?'
        )

    if current_user_text and current_user_text == last_user_text:
        if products:
            first = products[0]
            return (
                f'Te sigo por aqui sin repetir todo: si quieres, arrancamos por {first["title"]}. '
                'Dime que quieres definir primero y te respondo puntual.'
            )
        return 'Te sigo por aqui. Dime que quieres definir primero y te respondo puntual.'

    if stage == STAGE_DISCOVERING and products:
        first = products[0]
        return f'Perfecto. Si quieres, arrancamos por {first["title"]}. Dime si te importa mas talla, color o precio.'

    return reply


def _product_link(product: dict[str, Any], org_slug: str) -> str:
    product_id = product.get('id')
    title = product.get('title', '')
    if not product_id or not org_slug or not title:
        return title
    return f'[{title}](/shop/{org_slug}/{product_id})'


def _build_product_lines(products: list[dict[str, Any]], org_slug: str = '') -> str:
    if not products:
        return ''
    lines = []
    for product in products[:3]:
        line = f'\n- {_product_link(product, org_slug)}'
        if product.get('min_price'):
            line += f' - ${product["min_price"]:,.0f}'
        line += ' disponible' if product.get('any_in_stock') else ' sin stock'
        lines.append(line)
    return ''.join(lines)


def _append_product_links(reply: str, products: list[dict[str, Any]], org_slug: str) -> str:
    if not reply or not products or not org_slug:
        return reply
    if '/shop/' in reply:
        return reply
    updated_reply = reply
    replacements = 0

    for product in products[:2]:
        title = (product.get('title') or '').strip()
        link = _product_link(product, org_slug)
        if not title or not link:
            continue
        pattern = re.compile(rf'(\*\*|__)?\s*{re.escape(title)}\s*(\*\*|__)?', re.IGNORECASE)
        updated_reply, count = pattern.subn(link, updated_reply, count=1)
        replacements += count

    if replacements > 0:
        updated_reply = re.sub(r'(\*\*|__)\s*(\[[^\]]+\]\(/shop/[^)]+\))\s*(\*\*|__)', r'\2', updated_reply)
        return updated_reply

    first_link = _product_link(products[0], org_slug)
    if not first_link:
        return reply
    return f'{reply} Puedes ver {first_link}.'


def _payment_option_link(method: str, org_slug: str) -> str:
    normalized_method = (method or '').strip()
    if not normalized_method or not org_slug:
        return normalized_method
    prompt = f'Quiero pagar por {normalized_method}. Guiame con el siguiente paso.'
    return f'[{normalized_method}](/{org_slug}/?prefill={quote(prompt)})'


def _append_payment_links(reply: str, payment_methods: list[str], org_slug: str) -> str:
    if not reply or not payment_methods or not org_slug:
        return reply

    updated_reply = reply
    replacements = 0
    normalized_methods = [method for method in payment_methods[:3] if isinstance(method, str) and method.strip()]

    for method in normalized_methods:
        link = _payment_option_link(method, org_slug)
        pattern = re.compile(re.escape(method), re.IGNORECASE)
        updated_reply, count = pattern.subn(link, updated_reply, count=1)
        replacements += count

    if replacements > 0:
        return updated_reply

    if any(token in reply.lower() for token in ('pago', 'pagar', 'metodo', 'metodo de pago', 'método', 'método de pago')):
        chips = ' o '.join(_payment_option_link(method, org_slug) for method in normalized_methods[:2])
        return f'{reply} Puedes elegir {chips}.'

    return reply


def _build_system_prompt(sales_ctx: SalesContext) -> str:
    business = sales_ctx.business
    brand = sales_ctx.brand
    playbook = sales_ctx.playbook
    rules = sales_ctx.commerce_rules
    buyer_model = sales_ctx.buyer_model or {}
    prefs = sales_ctx.agent_preferences or {}
    prefs = sales_ctx.agent_preferences or {}
    forbidden = ', '.join((rules.forbidden_promises or business.forbidden_actions)[:4]) or 'ninguna definida'
    recommended_phrases = ', '.join(brand.recommended_phrases[:4]) or 'ninguna definida'
    avoid_phrases = ', '.join(brand.avoid_phrases[:4]) or 'ninguna definida'
    ideal_buyers = ', '.join((buyer_model.get('ideal_buyers') or [])[:4]) or 'no definidos'
    common_objections = ', '.join((buyer_model.get('common_objections') or [])[:5]) or 'no definidas'
    purchase_signals = ', '.join((buyer_model.get('purchase_signals') or [])[:5]) or 'no definidas'
    low_intent_signals = ', '.join((buyer_model.get('low_intent_signals') or [])[:5]) or 'no definidas'
    # Response length instruction
    _length_instruction = {
        'brief': 'Responde SIEMPRE en 1 frase, maximo 2. Sin listas, sin parrafos.',
        'standard': 'Por defecto responde en 1 o 2 frases cortas. Usa 3 solo si es estrictamente necesario.',
        'detailed': 'Puedes dar respuestas mas completas cuando el cliente necesite informacion detallada, pero sigue siendo conciso.',
    }.get(business.max_response_length, 'Por defecto responde en 1 o 2 frases cortas.')

    # Language instruction
    _lang_instruction = {
        'es': 'Responde SIEMPRE en español, independientemente del idioma del cliente.',
        'en': 'Always respond in English, regardless of the customer language.',
        'auto': 'Responde en el idioma del cliente.',
    }.get(business.response_language, 'Responde en el idioma del cliente.')

    # Persona line
    _persona_line = (
        f'Tu persona: {business.agent_persona}.\n' if business.agent_persona
        else f'Eres un asesor comercial experto de {brand.brand_name or business.org_name}.\n'
    )

    # Competitor handling
    _competitor_line = (
        f'Cuando el cliente mencione competidores: {playbook.competitor_response}.\n'
        if playbook.competitor_response
        else (
            f'Nunca des informacion sobre otra empresa, otra marca, otro negocio o '
            f'otra organizacion distinta de {brand.brand_name or business.org_name}. '
            'Si te preguntan por otra empresa, dilo claramente y redirige.\n'
        )
    )

    # Greeting
    _greeting_line = (
        f'Si es el inicio de la conversacion (sin historial previo), saluda con: "{business.greeting_message}"\n'
        if business.greeting_message else ''
    )

    return (
        f'{_persona_line}'
        f'Trabajas para la marca {brand.brand_name or business.org_name or "la empresa"}.\n'
        'Tu objetivo principal no es solo responder: es ayudar al cliente a tomar una decision de compra.\n'
        'Debes comportarte como un vendedor experto: entiende la necesidad, pregunta cuando falte informacion, recomienda productos adecuados, resuelve dudas y objeciones y guia la conversacion hacia la compra.\n'
        'Nunca respondas de forma pasiva, fria o generica.\n'
        'Cada respuesta debe empujar la conversacion hacia una decision concreta.\n'
        'Si el cliente se enfria o dice que luego vuelve, haz seguimiento comercial suave: resume la mejor opcion y cierra con una sola pregunta util.\n'
        'Nunca seas abusivo ni spam. No presiones con urgencia falsa.\n'
        'Solo puedes usar informacion real del negocio. Nunca inventes precios, stock, politicas, tiempos de envio ni promociones.\n'
        f'{_length_instruction}\n'
        f'{_lang_instruction}\n'
        'No metas varias ideas densas en un mismo mensaje. Da una recomendacion concreta y una sola pregunta util.\n'
        'Debes absorber y respetar la identidad de marca, el playbook comercial, el buyer model, las reglas comerciales, el catalogo y la knowledge base en cada respuesta.\n'
        f'{_competitor_line}'
        'Si hay conflicto entre sonar natural y seguir la marca, prioriza sonar natural sin salirte del tono y reglas de la marca.\n'
        'Usa frases recomendadas solo si encajan de forma natural. Evita por completo las frases a evitar y cualquier claim prohibido.\n'
        f'{_greeting_line}'
        f'Nombre de marca: {brand.brand_name or business.org_name or "no definido"}.\n'
        f'Nombre del agente: {sales_ctx.agent_name or "Sales Agent"}.\n'
        f'Que vende la marca: {business.what_you_sell or "no definido"}.\n'
        f'Tipo de clientes: {business.who_you_sell_to or "no definido"}.\n'
        f'Mision de marca: {business.mission or "no definida"}.\n'
        f'Industria: {business.industry or "no definida"}. Pais: {business.country or "no definido"}. Web: {business.website or "no definida"}.\n'
        f'Tono de marca: {brand.tone_of_voice}. Formalidad: {brand.formality_level}. Personalidad: {brand.brand_personality or "no definida"}.\n'
        f'{"Estilo de escritura de los clientes (aprende a sonar como ellos): " + brand.customer_style_notes + chr(10) if brand.customer_style_notes else ""}'
        f'Propuesta de valor: {brand.value_proposition or "no definida"}.\n'
        f'Diferenciales clave: {", ".join(brand.key_differentiators[:4]) or "no definidos"}.\n'
        f'Estilo de cierre: {brand.preferred_closing_style}. Intensidad comercial permitida: {brand.urgency_style}.\n'
        f'Frases recomendadas: {recommended_phrases}.\n'
        f'Frases a evitar: {avoid_phrases}.\n'
        f'Metodos de pago aceptados: {", ".join(business.payment_methods) or "no definidos"}.\n'
        f'Politica de envios: {business.shipping_policy or business.shipping_coverage}.\n'
        f'Playbook apertura: {playbook.opening_style or "no definido"}.\n'
        f'Playbook recomendacion: {playbook.recommendation_style or "no definido"}.\n'
        f'Playbook objeciones: {playbook.objection_style or "no definido"}.\n'
        f'Playbook cierre: {playbook.closing_style or "no definido"}.\n'
        f'Playbook follow-up: {playbook.follow_up_style or "no definido"}.\n'
        f'Playbook upsell: {playbook.upsell_style or "no definido"}.\n'
        f'Autonomia del agente: {prefs.get("autonomy_level", "semi_autonomo")} | followup={prefs.get("followup_mode", "suave")} | escalado={prefs.get("handoff_mode", "balanceado")}.\n'
        f'Compradores ideales: {ideal_buyers}.\n'
        f'Objeciones comunes: {common_objections}.\n'
        f'Senales de compra: {purchase_signals}.\n'
        f'Senales de bajo interes: {low_intent_signals}.\n'
        f'Regla de descuentos: {rules.discount_policy or "no definida"}.\n'
        f'Regla de negociacion: {rules.negotiation_policy or "no definida"}.\n'
        f'Regla de inventario: {rules.inventory_promise_rule or "no definida"}.\n'
        f'Regla de entrega: {rules.delivery_promise_rule or "no definida"}.\n'
        f'Resumen de devoluciones: {rules.return_policy_summary or "no definida"}.\n'
        f'Acciones prohibidas: {forbidden}.'
    )


def _build_context_block(
    *,
    stage: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    stock_info: dict[str, Any] | None,
    promotions: list[dict[str, Any]],
    sales_ctx: SalesContext,
    conversation,
) -> str:
    business = sales_ctx.business
    brand = sales_ctx.brand
    playbook = sales_ctx.playbook
    rules = sales_ctx.commerce_rules
    buyer_model = sales_ctx.buyer_model or {}
    prefs = sales_ctx.agent_preferences or {}
    history = _build_conversation_history(conversation)
    knowledge = _lookup_relevant_knowledge(conversation, business, products, sales_ctx, stage=stage)
    conversation_state = _map_stage_to_conversation_state(stage)
    qualification = ((getattr(conversation, 'metadata', None) or {}).get('qualification') or {})
    qualification_summary = (
        f"tipo={qualification.get('affiliate_status', 'sin_validar')}, "
        f"categoria={qualification.get('affiliate_category', 'sin_validar')}, "
        f"empresa_al_dia={qualification.get('company_status', 'sin_validar')}"
    )
    active_flow = ((getattr(conversation, 'metadata', None) or {}).get('active_flow') or {})
    flow_summary = (
        f"nombre={active_flow.get('name', 'sin_flujo')}, "
        f"paso={active_flow.get('step', 'sin_paso')}, "
        f"estado={active_flow.get('status', 'sin_estado')}, "
        f"datos={active_flow.get('data', {})}"
    )
    catalog_snapshot = _build_catalog_snapshot_block(sales_ctx.catalog_snapshot)
    full_knowledge_snapshot = _build_knowledge_snapshot_block(sales_ctx.knowledge_snapshot)
    product_lines = ['Sin productos encontrados para esta consulta.']
    if products:
        product_lines = []
        for product in products[:4]:
            stock_label = 'en stock' if product.get('any_in_stock') else 'sin stock'
            price_label = f'${product["min_price"]:,.0f}' if product.get('min_price') else 'precio a consultar'
            product_lines.append(f'- {product["title"]} | {price_label} | {stock_label}')
    promotion_lines = '\n'.join(f'- {promo}' for promo in promotions[:2]) if promotions else 'Sin promociones activas.'
    stock_line = f'Stock validado: {stock_info.get("total_available")}' if stock_info else 'Stock no consultado.'
    return (
        '\n--- CONTEXTO ---\n'
        f'conversation_state: {conversation_state}\n'
        f'marca: {brand.brand_name or business.org_name or "no definida"}\n'
        f'nombre_del_agente: {sales_ctx.agent_name or "Sales Agent"}\n'
        f'que_vende_la_marca: {business.what_you_sell or "no definido"}\n'
        f'tipo_de_clientes: {business.who_you_sell_to or "no definido"}\n'
        f'mision: {business.mission or "no definida"}\n'
        f'identidad_visual: primary={brand.primary_color or "n/d"}, accent={brand.accent_color or "n/d"}, style={brand.visual_style or "n/d"}, logo={brand.logo_url or "n/d"}\n'
        f'Pagos: {", ".join(business.payment_methods)}\n'
        f'Envios: {business.shipping_coverage} ({business.shipping_avg_days})\n'
        f'Politicas: {", ".join(business.commercial_policies[:3]) or "estandar"}\n'
        f'Calificacion operativa: {qualification_summary}\n'
        f'Flujo estructurado: {flow_summary}\n'
        f'Politica descuentos: {rules.discount_policy or "no definida"}\n'
        f'Politica negociacion: {rules.negotiation_policy or "no definida"}\n'
        f'Regla inventario: {rules.inventory_promise_rule or "no definida"}\n'
        f'Regla entrega: {rules.delivery_promise_rule or "no definida"}\n'
        f'Regla devoluciones: {rules.return_policy_summary or "no definida"}\n'
        f'Comprador: prioridad={buyer.priority}, urgencia={buyer.urgency}, estilo={buyer.style}, objecion={buyer.objection or "ninguna"}, etapa={stage}\n'
        f'Regla de seguimiento: modo={prefs.get("followup_mode", "suave")} | max_followups={prefs.get("max_followups", 1)} | autonomia={prefs.get("autonomy_level", "semi_autonomo")} | recommendation_depth={prefs.get("recommendation_depth", 2)} | escalado={prefs.get("handoff_mode", "balanceado")}.\n'
        f'Marca: tono={brand.tone_of_voice}, formalidad={brand.formality_level}, personalidad={brand.brand_personality or "n/d"}, propuesta={brand.value_proposition or "n/d"}\n'
        f'Diferenciales marca: {", ".join(brand.key_differentiators[:4]) or "ninguno"}\n'
        f'Frases recomendadas: {", ".join(brand.recommended_phrases[:4]) or "ninguna"}\n'
        f'Frases a evitar: {", ".join(brand.avoid_phrases[:4]) or "ninguna"}\n'
        f'Playbook activo: apertura={playbook.opening_style or "n/d"} | recomendacion={playbook.recommendation_style or "n/d"} | objeciones={playbook.objection_style or "n/d"} | cierre={playbook.closing_style or "n/d"} | follow_up={playbook.follow_up_style or "n/d"} | upsell={playbook.upsell_style or "n/d"}\n'
        f'Buyer model: ideales={", ".join((buyer_model.get("ideal_buyers") or [])[:4]) or "n/d"} | objeciones={", ".join((buyer_model.get("common_objections") or [])[:4]) or "n/d"} | compra={", ".join((buyer_model.get("purchase_signals") or [])[:4]) or "n/d"} | bajo_interes={", ".join((buyer_model.get("low_intent_signals") or [])[:4]) or "n/d"}\n'
        f'Catalogo activo:\n{catalog_snapshot}\n'
        f'Knowledge base completa resumida:\n{full_knowledge_snapshot}\n'
        f'Historial reciente:\n{history}\n'
        f'Knowledge relevante:\n{knowledge}\n'
        + '\n'.join(product_lines) + '\n'
        + promotion_lines + '\n'
        + stock_line + '\n--- FIN CONTEXTO ---\n'
    )


def _map_stage_to_conversation_state(stage: str) -> str:
    if stage == STAGE_INTENT_TO_BUY:
        return 'listo_para_comprar'
    if stage in (STAGE_CONSIDERING, STAGE_CHECKOUT_BLOCKED):
        return 'interesado'
    return 'explorando'


def _build_catalog_snapshot_block(catalog_snapshot: list[dict[str, Any]]) -> str:
    if not catalog_snapshot:
        return 'Sin catalogo activo disponible.'

    lines: list[str] = []
    for item in catalog_snapshot[:6]:
        price = f'${item["min_price"]:,.0f}' if item.get('min_price') else 'precio a consultar'
        stock = 'disponible' if item.get('any_in_stock') else 'sin stock'
        category = item.get('category') or 'sin categoria'
        lines.append(f'- {item["title"]} | {category} | {price} | {stock}')
    return '\n'.join(lines)


def _build_knowledge_snapshot_block(knowledge_snapshot: list[dict[str, Any]]) -> str:
    if not knowledge_snapshot:
        return 'Sin knowledge base publicada.'

    lines: list[str] = []
    for item in knowledge_snapshot[:8]:
        item_type = item.get('type', 'item')
        category = item.get('category') or 'general'
        content = item.get('content', '')
        lines.append(f'- [{item_type}] {item.get("title", "sin titulo")} | {category} | {content}')
    return '\n'.join(lines)


def _build_conversation_history(conversation) -> str:
    try:
        if conversation is None:
            return 'Sin historial.'
        history = conversation.messages.order_by('-timestamp')[:6]
        items = []
        for item in reversed(list(history)):
            role = 'cliente' if item.role == 'user' else 'marca'
            content = ' '.join((item.content or '').split())
            if not content:
                continue
            items.append(f'- {role}: {content[:220]}')
        return '\n'.join(items) if items else 'Sin historial.'
    except Exception:
        return 'Sin historial.'


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_query(text: str) -> list[float] | None:
    """Get OpenAI embedding for query text."""
    try:
        import os
        from openai import OpenAI

        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            return None
        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(model='text-embedding-3-small', input=text[:512])
        return response.data[0].embedding
    except Exception:
        return None


# Maps conversation stage → KB purposes to prioritize (fetched first, injected top of context)
_STAGE_PURPOSE_MAP: dict[str, list[str]] = {
    STAGE_CHECKOUT_BLOCKED:  ['objection', 'policy'],
    STAGE_CONSIDERING:       ['product_context', 'faq'],
    STAGE_INTENT_TO_BUY:     ['closing', 'policy'],
    STAGE_FOLLOW_UP_NEEDED:  ['closing', 'brand_voice'],
    STAGE_LOST:              ['objection', 'closing'],
    STAGE_CLOSED_LOST:       ['objection'],
    STAGE_CLOSED_WON:        ['closing', 'brand_voice'],
    STAGE_HUMAN_HANDOFF:     ['policy'],
    STAGE_DISCOVERING:       ['faq', 'brand_voice'],
}
# Always added unless already satisfied by stage-specific results
_BASELINE_PURPOSES = ['faq', 'brand_voice']


def _lookup_relevant_knowledge(
    conversation,
    business: BusinessContext,
    products: list[dict[str, Any]],
    sales_ctx: SalesContext | None = None,
    stage: str = STAGE_DISCOVERING,
) -> str:
    try:
        from apps.knowledge_base.models import KBArticle, KBDocument

        org = getattr(conversation, 'organization', None)
        if org is None:
            return 'Sin conocimiento adicional.'

        base_qs = KBArticle.objects.filter(organization=org, is_active=True, status='published')

        # --- Stage-aware purpose retrieval ---
        priority_purposes = _STAGE_PURPOSE_MAP.get(stage, _BASELINE_PURPOSES)
        # Always ensure faq is present as baseline
        all_purposes = list(dict.fromkeys(priority_purposes + _BASELINE_PURPOSES))

        purpose_articles: list[Any] = []
        seen_ids: set = set()

        # Fetch up to 2 articles per purpose, in priority order
        for purpose in all_purposes:
            if len(purpose_articles) >= 4:
                break
            qs = base_qs.filter(purpose=purpose).only('id', 'title', 'content', 'purpose', 'embedding_vector').order_by('-updated_at')[:4]
            for art in qs:
                if art.id not in seen_ids:
                    purpose_articles.append(art)
                    seen_ids.add(art.id)
                    if len(purpose_articles) >= 4:
                        break

        # --- Semantic re-ranking via cosine similarity ---
        # Build query text from last customer message + products
        query_parts: list[str] = []
        try:
            last_user_msg = conversation.messages.filter(role='user').order_by('-timestamp').first()
            if last_user_msg and last_user_msg.content:
                query_parts.append(last_user_msg.content[:120])
        except Exception:
            pass
        for product in products[:2]:
            t = product.get('title', '')
            if t:
                query_parts.append(t[:60])
        if business.what_you_sell:
            query_parts.append(business.what_you_sell[:60])
        query_text = ' '.join(query_parts).strip() or 'productos y servicios'

        # Broaden pool with general articles if purpose-filtered set is small
        if len(purpose_articles) < 3:
            extra = list(
                base_qs.exclude(id__in=seen_ids)
                .only('id', 'title', 'content', 'purpose', 'embedding_vector')
                .order_by('-updated_at')[:20]
            )
            purpose_articles.extend(extra)

        query_vec = _embed_query(query_text)
        articles_with_emb = [a for a in purpose_articles if a.embedding_vector]

        if query_vec and articles_with_emb:
            scored = [
                (a, _cosine_similarity(query_vec, a.embedding_vector))
                for a in articles_with_emb
            ]
            scored.sort(key=lambda t: t[1], reverse=True)
            top_articles = [a for a, score in scored[:4] if score > 0.20]
            # Add purpose-priority articles that didn't make cosine cut (low text but on-purpose)
            for art in purpose_articles[:2]:
                if art not in top_articles:
                    top_articles.insert(0, art)
            top_articles = top_articles[:4]
        else:
            # Fallback: keyword icontains on general pool
            terms = [w for w in query_text.lower().split() if len(w) > 3][:6]
            if terms:
                from django.db.models import Q
                kb_filter = Q()
                for term in terms:
                    kb_filter |= Q(title__icontains=term) | Q(content__icontains=term)
                top_articles = list(base_qs.filter(kb_filter).order_by('-updated_at')[:4])
            else:
                top_articles = purpose_articles[:3]

        snippets: list[str] = []
        for article in top_articles:
            purpose_label = f'[{article.purpose}] ' if getattr(article, 'purpose', '') else ''
            snippets.append(f'- {purpose_label}{article.title}: {" ".join(article.content.split())[:220]}')

        # --- Documents (keyword match) ---
        document_queryset = KBDocument.objects.filter(organization=org, is_active=True, processing_status='ready')
        terms = [w for w in query_text.lower().split() if len(w) > 3][:6]
        if terms:
            from django.db.models import Q
            doc_filter = Q()
            for term in terms:
                doc_filter |= Q(filename__icontains=term) | Q(extracted_text__icontains=term)
            documents = document_queryset.filter(doc_filter).order_by('-updated_at')[:2]
        else:
            documents = document_queryset.order_by('-updated_at')[:2]

        for document in documents:
            excerpt = ' '.join((document.extracted_text or '').split())[:220]
            if excerpt:
                snippets.append(f'- [doc] {document.filename}: {excerpt}')

        if snippets:
            return '\n'.join(snippets)

        if sales_ctx and sales_ctx.knowledge_snapshot:
            return _build_knowledge_snapshot_block(sales_ctx.knowledge_snapshot[:4])
        return 'Sin conocimiento adicional.'
    except Exception:
        if sales_ctx and sales_ctx.knowledge_snapshot:
            return _build_knowledge_snapshot_block(sales_ctx.knowledge_snapshot[:4])
        return 'Sin conocimiento adicional.'


def _apply_brand_voice(text: str, brand_ctx: BrandProfile, playbook: SalesPlaybook, stage: str) -> str:
    cleaned = ' '.join((text or '').split())
    for phrase in brand_ctx.avoid_phrases:
        if isinstance(phrase, str) and phrase.strip():
            cleaned = cleaned.replace(phrase.strip(), '')
    prefix = ''
    if stage == STAGE_DISCOVERING and playbook.opening_style:
        prefix = playbook.opening_style.strip()
    elif stage == STAGE_CONSIDERING and playbook.recommendation_style:
        prefix = playbook.recommendation_style.strip()
    elif stage == STAGE_FOLLOW_UP_NEEDED and playbook.follow_up_style:
        prefix = playbook.follow_up_style.strip()
    elif stage in (STAGE_INTENT_TO_BUY, STAGE_CHECKOUT_BLOCKED) and playbook.closing_style:
        prefix = playbook.closing_style.strip()
    elif brand_ctx.recommended_phrases:
        prefix = brand_ctx.recommended_phrases[0].strip()
    if prefix and len(prefix.split()) <= 6 and prefix.lower() not in cleaned.lower():
        cleaned = f'{prefix} {cleaned}'.strip()
    if brand_ctx.formality_level == 'formal':
        cleaned = cleaned.replace('Lo tomamos?', 'Desea avanzar con la compra?')
        cleaned = cleaned.replace('Lo pedimos?', 'Desea que avancemos con el pedido?')
    elif brand_ctx.formality_level == 'casual':
        cleaned = cleaned.replace('Desea avanzar con la compra?', 'Te animas a pedirlo?')
    if brand_ctx.urgency_style == 'soft':
        cleaned = cleaned.replace('hoy mismo', 'pronto')
    elif brand_ctx.urgency_style == 'strong' and stage == STAGE_INTENT_TO_BUY and '?' in cleaned and 'hoy' not in cleaned.lower():
        cleaned = cleaned[:-1] + ' hoy?'
    return _humanize_sales_reply(cleaned.strip(), stage, brand_ctx.formality_level)


def _humanize_sales_reply(text: str, stage: str, formality_level: str) -> str:
    cleaned = ' '.join((text or '').split()).strip()
    replacements = {
        'Con gusto te ayudo con el precio.': 'Te ayudo con el precio.',
        'Con gusto': '',
        'Estoy aqui para ayudarte.': '',
        'la mejor opcion para tu caso': 'la opcion que mejor te encaje',
        'la mejor opcion': 'la opcion que mejor te encaje',
        'Si quieres, te digo': 'Si quieres, te cuento',
        'Si quieres, te ayudo a': 'Si quieres, vemos',
        'Si quieres, revisamos': 'Si quieres, vemos',
        'Si me dices para que lo necesitas': 'Si me dices para que lo quieres',
        'Cuentame': 'Cuentame',
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)

    cleaned = cleaned.replace('  ', ' ').replace(' .', '.').strip()
    cleaned = cleaned.replace('?.', '?').replace('..', '.')

    if formality_level != 'formal':
        cleaned = cleaned.replace('Desea avanzar con la compra?', 'Quieres que avancemos?')
        cleaned = cleaned.replace('Desea que avancemos con el pedido?', 'Quieres que lo dejemos avanzado?')
        cleaned = cleaned.replace('Te animas a pedirlo?', 'Quieres que lo dejemos listo?')

    if stage == STAGE_DISCOVERING:
        cleaned = cleaned.replace('Hola. Que producto estas buscando?', 'Hola, que andas buscando?')
        cleaned = cleaned.replace('Lo buscas para uso personal, regalo o para algo mas especifico?', 'Es para ti, para regalo o para algo puntual?')

    if stage == STAGE_FOLLOW_UP_NEEDED:
        cleaned = cleaned.replace('Antes de dejarlo ahi,', '')
        cleaned = cleaned.replace('Por ahora la opcion que mejor encaja es', 'Yo por ahora me iria por')
        cleaned = cleaned.replace('la opcion que veo mas alineada es', 'yo me iria por')

    cleaned = cleaned.strip(' .')
    if cleaned and cleaned[-1] not in '.!?':
        cleaned += '.'
    return cleaned


def _create_followup_task(conversation, organization, stage: str, message_text: str, buyer: BuyerProfile) -> None:
    try:
        from django.utils import timezone

        from apps.ai_engine.models import AITask
        from apps.channels_config.models import ChannelConfig

        if conversation is None:
            return

        settings = {}
        org_id = getattr(organization, 'id', None)
        if _has_real_identifier(org_id):
            config = ChannelConfig.objects.filter(organization=organization, channel='onboarding').only('settings').first()
            settings = (config.settings if config else {}) or {}
        sales_prefs = ((settings.get('ai_preferences') or {}).get('sales_agent') or {})
        followup_mode = sales_prefs.get('followup_mode', 'suave')
        normalized_followup_mode = {
            'suave': 'soft',
            'soft': 'soft',
            'agresivo': 'aggressive',
            'aggressive': 'aggressive',
        }.get(str(followup_mode).lower(), 'soft')
        max_attempts = int(sales_prefs.get('max_followups', 2) or 2)
        if followup_mode == 'apagado' or max_attempts <= 0:
            return

        cooldown_hours = 24 if stage == STAGE_FOLLOW_UP_NEEDED else 12
        recent_threshold = timezone.now() - timezone.timedelta(hours=cooldown_hours)
        existing_qs = AITask.objects.filter(
            organization=organization,
            task_type='sales_followup',
            created_at__gte=recent_threshold,
            input_data__conversation_id=str(conversation.id),
        )
        if existing_qs.exists():
            return

        total_attempts_raw = AITask.objects.filter(
            organization=organization,
            task_type='sales_followup',
            input_data__conversation_id=str(conversation.id),
        ).count()
        total_attempts = total_attempts_raw if isinstance(total_attempts_raw, int) else 0
        if total_attempts >= max_attempts:
            return

        priority = 'high' if buyer.urgency in ('immediate', 'this_week') else 'medium'
        AITask.objects.create(
            organization=organization,
            name=f'Seguimiento comercial - {stage}',
            description=(
                f'Lead en etapa "{stage}". Prioridad comprador: {buyer.priority}. '
                f'Urgencia: {buyer.urgency}. Mensaje: {message_text[:200]}'
            ),
            task_type='sales_followup',
            priority=priority,
            input_data={
                'conversation_id': str(conversation.id),
                'stage': stage,
                'buyer_profile': buyer.to_dict(),
                'contact_id': str(conversation.contact_id) if conversation.contact_id else None,
                'cadence': normalized_followup_mode,
                'max_attempts': max_attempts,
                'cooldown_hours': cooldown_hours,
            },
        )
    except Exception as exc:
        logger.warning('sales_agent_followup_task_error', error=str(exc))
