"""
Sales Agent: adaptive, business-constrained sales closer for Vendly.
"""
from __future__ import annotations

import re
from typing import Any

import structlog

from .sales_models import (
    STAGE_CHECKOUT_BLOCKED,
    STAGE_CLOSED_LOST,
    STAGE_CLOSED_WON,
    STAGE_CONSIDERING,
    STAGE_DISCOVERING,
    STAGE_FOLLOW_UP_NEEDED,
    STAGE_HUMAN_HANDOFF,
    STAGE_INTENT_TO_BUY,
    STAGE_LOST,
    DECISION_ASSIST_AND_ADVANCE,
    DECISION_DISCARD,
    DECISION_ESCALATE,
    DECISION_FOLLOW_UP,
    DECISION_RECOMMEND,
    DECISION_QUALIFY,
    _NEGOTIATION_SIGNALS,
    _STAGE_SIGNALS,
    BuyerProfile,
    BusinessContext,
    BrandProfile,
    CommerceRules,
    SalesContext,
    SalesPlaybook,
    SalesAction,
    HandoffDecision,
    SalesAgentResult,
)
from .sales_context import _load_sales_context, _create_followup_task, _extract_kb_policy_overrides
from .sales_scope import (
    _guard_general_scope_request,
    _guard_out_of_scope_request,
    _enforce_reply_scope,
    _strengthen_closing_reply,
)
from .sales_reply import (
    _generate_reply,
    _apply_brand_voice,
    _build_context_block,
    _build_system_prompt,
    _heuristic_reply,
    _humanize_sales_reply,
    _guard_out_of_scope_brand_query,
    _avoid_consecutive_repeat,
)
from .sales_kb import _lookup_relevant_knowledge

logger = structlog.get_logger(__name__)


class SalesAgent:
    def run(self, *, message_text: str, conversation, organization, router_decision=None) -> SalesAgentResult:
        from .sales_tools import check_stock, get_active_promotions, get_order_history, lookup_products

        text = message_text.lower()
        sales_ctx = _load_sales_context(organization)

        # P3.1: Load contact memory for cross-conversation context
        contact = getattr(conversation, 'contact', None)
        contact_memory = _load_contact_memory(contact) if contact else {}

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
                # Try intent-based flow lookup first (custom intents from AI Router)
                _router_intent = getattr(router_decision, 'intent', None) if router_decision else None
                if _router_intent:
                    from apps.flows.trigger import find_flow_by_intent
                    _intent_flow = find_flow_by_intent(
                        organization=conversation.organization,
                        intent=_router_intent,
                        channel=_channel,
                    )
                    if _intent_flow:
                        _db_result = _engine._start_flow(
                            conversation=conversation,
                            flow=_intent_flow,
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

        # Legacy hardcoded Comfaguajira flows removed — superseded by DB-driven flows
        stage, confidence = _classify_stage(text, sales_ctx.buyer_model)
        buyer = _profile_buyer(text, sales_ctx.buyer_model, stage=stage)
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

        # P1.3: Score and rank products (top 3) using composite recommendation engine
        # P3.2: Include organization_id for product graph lookup
        from .recommendation import score_and_rank_products
        products = score_and_rank_products(
            products, buyer, stage, promotions, message_text,
            organization_id=str(organization.id),
            prior_product_ids=contact_memory.get('last_products_shown', []) if isinstance(contact_memory, dict) else [],
        )

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
            channel=_channel,  # P2.1 & P2.3: pass channel for adaptation
            contact_memory=contact_memory,  # P3.1: pass contact memory for context
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

        # P3.1: Update contact memory with this turn's data
        _update_contact_memory(contact, organization, buyer, products, stage)

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


def _profile_buyer(text: str, buyer_model: dict[str, Any] | None = None, stage: str = STAGE_DISCOVERING) -> BuyerProfile:
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
    # Only call LLM for objection classification in stages where objections matter
    if objection is None and stage in (STAGE_CONSIDERING, STAGE_CHECKOUT_BLOCKED, STAGE_FOLLOW_UP_NEEDED):
        objection = _infer_objection_reason(text)

    style = 'exploratory'
    if any(token in text for token in ('quiero', 'compro', 'necesito', 'dame', 'enviame', 'mandame')):
        style = 'direct'
    elif any(token in text for token in ('comparar', 'diferencia', 'cual', 'entre', 'opciones')):
        style = 'comparative'

    profile = BuyerProfile(priority=priority, quantity=quantity, urgency=urgency, objection=objection, style=style)

    # P3.1: lightweight memory signals for later persistence
    occasion_hints = _extract_occasion_hints(text)
    if occasion_hints:
        profile._occasion_hints = occasion_hints
    budget_min, budget_max = _extract_budget_range(text)
    if budget_min is not None:
        profile._budget_min = budget_min
    if budget_max is not None:
        profile._budget_max = budget_max

    return profile


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


def _check_handoff(text: str, buyer: BuyerProfile, biz_ctx: BusinessContext, playbook) -> HandoffDecision:
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


def _extract_occasion_hints(text: str) -> list[str]:
    hint_map = {
        'boda': ('boda', 'wedding', 'casamiento', 'matrimonio'),
        'cumpleanos': ('cumple', 'birthday', 'cumpleanos', 'cumpleaños'),
        'trabajo': ('trabajo', 'laboral', 'oficina', 'empresa', 'business'),
        'cena': ('cena', 'dinner', 'restaurante', 'noche'),
        'casual': ('casual', 'relajado', 'fin de semana', 'weekend'),
        'formal': ('formal', 'gala', 'evento', 'elegante'),
        'regalo': ('regalo', 'gift', 'obsequio'),
    }
    hints: list[str] = []
    for key, tokens in hint_map.items():
        if any(token in text for token in tokens):
            hints.append(key)
    return hints


def _extract_budget_range(text: str) -> tuple[float | None, float | None]:
    budget_tokens = ('presupuesto', 'budget', 'hasta', 'max', 'tope', 'entre', 'rango')
    if not any(token in text for token in budget_tokens):
        return None, None

    matches = re.findall(r'(\d+(?:[.,]\d+)?)([kKmM]?)', text)
    values: list[float] = []
    for raw_number, suffix in matches:
        parsed = _parse_amount(raw_number, suffix)
        if parsed is not None and parsed > 0:
            values.append(parsed)
    if not values:
        return None, None

    if len(values) == 1:
        return None, values[0]

    if 'entre' in text or ' a ' in text or '-' in text:
        return min(values), max(values)
    return None, values[0]


def _parse_amount(raw_number: str, suffix: str) -> float | None:
    try:
        cleaned = (raw_number or '').strip()
        if '.' in cleaned and ',' in cleaned:
            cleaned = cleaned.replace('.', '').replace(',', '.')
        elif '.' in cleaned and len(cleaned.split('.')[-1]) == 3:
            cleaned = cleaned.replace('.', '')
        elif ',' in cleaned and len(cleaned.split(',')[-1]) == 3:
            cleaned = cleaned.replace(',', '')
        else:
            cleaned = cleaned.replace(',', '.')

        value = float(cleaned)
        if suffix.lower() == 'k':
            value *= 1000
        elif suffix.lower() == 'm':
            value *= 1_000_000
        return value
    except Exception:
        return None


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


def _load_contact_memory(contact) -> dict[str, Any]:
    """
    P3.1: Load persistent memory for a contact from previous conversations.
    Returns a dict summarizing the contact's preferences, budget, style.
    """
    if not contact:
        return {}

    try:
        from .models import ContactMemory

        memory = ContactMemory.objects.filter(contact=contact).first()
        if not memory:
            return {}

        return {
            'has_prior_interactions': memory.conversation_count > 0,
            'conversation_count': memory.conversation_count,
            'inferred_budget_min': float(memory.inferred_budget_min) if memory.inferred_budget_min else None,
            'inferred_budget_max': float(memory.inferred_budget_max) if memory.inferred_budget_max else None,
            'style_cues': memory.style_cues,
            'occasion_hints': memory.occasion_hints,
            'category_preferences': memory.category_preferences,
            'last_products_shown': memory.last_products_shown[-5:] if memory.last_products_shown else [],
            'last_intent': memory.last_intent,
            'last_objection': memory.last_objection,
            'converted': memory.converted,
        }
    except Exception as exc:
        logger.warning('load_contact_memory_error', error=str(exc))
        return {}


def _update_contact_memory(contact, organization, buyer: BuyerProfile, products: list[dict], stage: str) -> None:
    """
    P3.1: Update persistent memory for a contact after a conversation turn.
    Captures budget hints, style cues, products shown, and intent.
    """
    if not contact:
        return

    try:
        from .models import ContactMemory
        from django.utils import timezone

        memory, created = ContactMemory.objects.get_or_create(
            organization=organization,
            contact=contact,
        )

        # Update intent and objection
        memory.last_intent = stage
        if buyer.objection:
            memory.last_objection = buyer.objection

        # Track products shown (keep last 5)
        product_ids = [p['id'] for p in products[:3]]
        if product_ids:
            existing = memory.last_products_shown or []
            memory.last_products_shown = (product_ids + existing)[:5]
            memory.total_products_viewed += len(product_ids)

        # Update style cues from buyer profile
        memory.style_cues = {
            'priority': buyer.priority,
            'quantity': buyer.quantity,
            'urgency': buyer.urgency,
            'style': buyer.style,
        }

        # Persist inferred budget hints when available
        budget_min = getattr(buyer, '_budget_min', None)
        budget_max = getattr(buyer, '_budget_max', None)
        if budget_min is not None:
            if memory.inferred_budget_min is None:
                memory.inferred_budget_min = budget_min
            else:
                memory.inferred_budget_min = min(float(memory.inferred_budget_min), budget_min)
        if budget_max is not None:
            if memory.inferred_budget_max is None:
                memory.inferred_budget_max = budget_max
            else:
                memory.inferred_budget_max = max(float(memory.inferred_budget_max), budget_max)

        # Track categories (simplified)
        if products:
            cats = list(set(p.get('category', '') for p in products if p.get('category')))
            if cats:
                existing = memory.category_preferences or []
                memory.category_preferences = list(set(cats + existing))[:10]

        # Update occasion hints from message (naive: just flag if found)
        # (More sophisticated extraction would happen during extraction)
        if hasattr(buyer, '_occasion_hints'):
            memory.occasion_hints = list(set(buyer._occasion_hints + (memory.occasion_hints or [])))[:10]

        # Mark converted if this contact has non-cancelled orders
        from apps.ecommerce.models import Order
        if not memory.converted:
            memory.converted = Order.objects.filter(
                organization=organization,
                contact=contact,
            ).exclude(status='cancelled').exists()

        memory.conversation_count += 1
        memory.last_conversation_at = timezone.now()

        memory.save()

    except Exception as exc:
        logger.warning('update_contact_memory_error', error=str(exc))
