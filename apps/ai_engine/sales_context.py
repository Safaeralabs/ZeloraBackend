"""
Sales context loading: build SalesContext from organization configuration.

All inter-app imports (ecommerce, knowledge_base, channels_config) are deferred
inside function bodies to avoid circular dependencies.
"""
from __future__ import annotations

from typing import Any

import structlog

from .sales_models import (
    STAGE_FOLLOW_UP_NEEDED,
    BrandProfile,
    BusinessContext,
    BuyerProfile,
    CommerceRules,
    SalesContext,
    SalesPlaybook,
    _has_real_identifier,
)

logger = structlog.get_logger(__name__)


def _policy_text(value: Any) -> str:
    return ' '.join(str(value or '').split()).strip()


def _policy_tags(article) -> set[str]:
    return {str(tag).strip().lower() for tag in (getattr(article, 'tags', None) or []) if str(tag).strip()}


def _policy_haystack(article) -> str:
    return ' '.join(
        filter(
            None,
            [
                str(getattr(article, 'title', '') or ''),
                str(getattr(article, 'category', '') or ''),
                str(getattr(article, 'content', '') or ''),
            ],
        )
    ).lower()


def _extract_labeled_value(content: str, labels: list[str]) -> str:
    import re

    source = str(content or '')
    for label in labels:
        match = re.search(rf'(?im)^\s*{re.escape(label)}\s*:\s*(.+)$', source)
        if match:
            return _policy_text(match.group(1))
    return ''


def _extract_number(value: str) -> int | None:
    import re

    match = re.search(r'(\d+)', str(value or ''))
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _split_policy_items(value: str) -> list[str]:
    import re

    text = _policy_text(value)
    if not text:
        return []
    parts = re.split(r'[,\n;]+', text)
    return [item.strip(' .') for item in parts if item.strip(' .')]


def _extract_kb_policy_overrides(organization) -> dict[str, Any]:
    try:
        from apps.knowledge_base.models import KBArticle

        articles = list(
            KBArticle.objects.filter(
                organization=organization,
                is_active=True,
                status='published',
                purpose='policy',
            ).only('title', 'content', 'category', 'tags').order_by('-updated_at')[:20]
        )
    except Exception as exc:
        logger.warning('sales_context_kb_policy_overrides_error', error=str(exc))
        return {}

    overrides: dict[str, Any] = {}
    for article in articles:
        tags = _policy_tags(article)
        haystack = _policy_haystack(article)
        content = str(getattr(article, 'content', '') or '')
        compact_content = _policy_text(content)

        is_shipping = 'shipping' in tags or any(term in haystack for term in ('envio', 'envíos', 'envios', 'entrega'))
        is_returns = 'returns' in tags or any(term in haystack for term in ('devolucion', 'devoluciones', 'cambio', 'cambios'))
        is_discounts = 'discounts' in tags or any(term in haystack for term in ('descuento', 'descuentos', 'promo', 'promocion', 'promociones'))
        is_restrictions = 'guardrails' in tags or any(term in haystack for term in ('claims', 'promesas', 'prohibid', 'restric'))

        if is_shipping:
            overrides.setdefault('shipping_policy', compact_content)
            overrides.setdefault('shipping_coverage', _extract_labeled_value(content, ['Cobertura']))
            overrides.setdefault('shipping_avg_days', _extract_labeled_value(content, ['Tiempos estimados', 'Tiempo estimado']))
            overrides.setdefault('delivery_promise_rule', _extract_labeled_value(content, ['Condiciones importantes', 'Condiciones']))

        if is_returns:
            overrides.setdefault('return_policy_summary', compact_content)
            window_days = _extract_number(_extract_labeled_value(content, ['Plazo']))
            if window_days is not None:
                overrides.setdefault('returns_window_days', window_days)

        if is_discounts:
            overrides.setdefault('discount_policy', compact_content)
            forbidden = _extract_labeled_value(content, ['Lo que no se puede prometer'])
            if forbidden:
                overrides.setdefault('forbidden_promises', _split_policy_items(forbidden))

        if is_restrictions:
            claims = _extract_labeled_value(content, ['Claims prohibidos'])
            promises = _extract_labeled_value(content, ['Promesas prohibidas', 'Lo que no se puede prometer'])
            if claims:
                overrides.setdefault('forbidden_claims', _split_policy_items(claims))
            if promises:
                overrides.setdefault('forbidden_promises', _split_policy_items(promises))

    return overrides


def _load_sales_context(organization) -> SalesContext:
    try:
        from apps.channels_config.models import ChannelConfig
        from apps.channels_config.settings_schema import normalise_settings

        org_id = getattr(organization, 'id', None)
        if not _has_real_identifier(org_id):
            return SalesContext(
                business=BusinessContext(
                    org_name=getattr(organization, 'name', ''),
                    org_slug=getattr(organization, 'slug', ''),
                )
            )

        config = ChannelConfig.objects.filter(organization=organization, channel='onboarding').only('settings').first()
        app_config = ChannelConfig.objects.filter(organization=organization, channel='app').only('settings').first()
        web_config = ChannelConfig.objects.filter(organization=organization, channel='web').only('settings').first()
        app_settings = (app_config.settings if app_config else {}) or {}
        web_settings = (web_config.settings if web_config else {}) or {}

        s = normalise_settings((config.settings if config else {}) or {})
        op = s['org_profile']
        sa = s['sales_agent']
        brand_cfg = op.get('brand') or {}
        playbook_cfg = sa.get('playbook') or {}
        rules_cfg = sa.get('commerce_rules') or {}
        buyer_model_cfg = sa.get('buyer_model') or {}
        kb_policy_overrides = _extract_kb_policy_overrides(organization)

        logo_url = ''
        try:
            logo = getattr(organization, 'logo', None)
            if logo and getattr(logo, 'url', ''):
                logo_url = logo.url
        except Exception:
            logo_url = ''

        payment_methods = op.get('payment_methods') or ['transferencia bancaria', 'efectivo']
        business = BusinessContext(
            org_name=getattr(organization, 'name', ''),
            org_id=str(getattr(organization, 'id', '') or ''),
            org_slug=getattr(organization, 'slug', ''),
            what_you_sell=op.get('what_you_sell') or '',
            who_you_sell_to=op.get('who_you_sell_to') or '',
            website=getattr(organization, 'website', '') or op.get('website') or '',
            industry=getattr(organization, 'industry', '') or op.get('industry') or '',
            country=getattr(organization, 'country', '') or op.get('country') or '',
            brand_tone=brand_cfg.get('tone_of_voice') or 'amigable',
            payment_methods=payment_methods,
            shipping_coverage=kb_policy_overrides.get('shipping_coverage') or sa.get('shipping_coverage') or 'consultar cobertura',
            shipping_avg_days=kb_policy_overrides.get('shipping_avg_days') or sa.get('shipping_avg_days') or '2-5 dias habiles',
            min_order_units=int(sa.get('min_order_units') or 1),
            max_units_auto_approve=int(sa.get('max_units_auto_approve') or 10),
            commercial_policies=[
                item for item in [
                    kb_policy_overrides.get('discount_policy') or rules_cfg.get('discount_policy'),
                    kb_policy_overrides.get('negotiation_policy') or rules_cfg.get('negotiation_policy'),
                    kb_policy_overrides.get('inventory_promise_rule') or rules_cfg.get('inventory_promise_rule'),
                    kb_policy_overrides.get('delivery_promise_rule') or rules_cfg.get('delivery_promise_rule'),
                ] if item
            ],
            forbidden_actions=(
                kb_policy_overrides.get('forbidden_promises')
                or kb_policy_overrides.get('forbidden_claims')
                or rules_cfg.get('forbidden_promises')
                or rules_cfg.get('forbidden_claims')
                or BusinessContext().forbidden_actions
            ),
            has_returns_policy=bool(_policy_text(kb_policy_overrides.get('return_policy_summary') or rules_cfg.get('return_policy_summary'))),
            returns_window_days=int(kb_policy_overrides.get('returns_window_days') or sa.get('returns_window_days') or 15),
            shipping_policy=kb_policy_overrides.get('shipping_policy') or sa.get('shipping_policy') or '',
            agent_persona=sa.get('persona') or '',
            greeting_message=sa.get('greeting_message') or '',
            competitor_response=sa.get('competitor_response') or playbook_cfg.get('competitor_response') or '',
            response_language=sa.get('response_language') or 'auto',
            max_response_length=sa.get('max_response_length') or 'standard',
            mission=sa.get('mission_statement') or '',
        )
        brand = BrandProfile(
            brand_name=getattr(organization, 'name', ''),
            tone_of_voice=brand_cfg.get('tone_of_voice') or 'cercano',
            formality_level=brand_cfg.get('formality_level') or 'balanced',
            brand_personality=brand_cfg.get('brand_personality') or '',
            value_proposition=brand_cfg.get('value_proposition') or '',
            logo_url=logo_url,
            primary_color=app_settings.get('primary_color') or web_settings.get('brand_color') or '',
            accent_color=app_settings.get('accent_color') or '',
            visual_style=app_settings.get('surface_style') or web_settings.get('position') or '',
            key_differentiators=brand_cfg.get('key_differentiators') or [],
            preferred_closing_style=brand_cfg.get('preferred_closing_style') or 'directo',
            urgency_style=brand_cfg.get('urgency_style') or 'soft',
            recommended_phrases=brand_cfg.get('recommended_phrases') or [],
            avoid_phrases=brand_cfg.get('avoid_phrases') or [],
            customer_style_notes=brand_cfg.get('customer_style_notes') or '',
        )
        playbook = SalesPlaybook(
            opening_style=playbook_cfg.get('opening_style') or '',
            recommendation_style=playbook_cfg.get('recommendation_style') or '',
            objection_style=playbook_cfg.get('objection_style') or '',
            closing_style=playbook_cfg.get('closing_style') or '',
            follow_up_style=playbook_cfg.get('follow_up_style') or '',
            upsell_style=playbook_cfg.get('upsell_style') or '',
            escalate_conditions=playbook_cfg.get('escalate_conditions') or [],
            handoff_mode=sa.get('handoff_mode') or 'balanceado',
            competitor_response=sa.get('competitor_response') or playbook_cfg.get('competitor_response') or '',
        )
        rules = CommerceRules(
            discount_policy=kb_policy_overrides.get('discount_policy') or rules_cfg.get('discount_policy') or '',
            negotiation_policy=kb_policy_overrides.get('negotiation_policy') or rules_cfg.get('negotiation_policy') or '',
            inventory_promise_rule=kb_policy_overrides.get('inventory_promise_rule') or rules_cfg.get('inventory_promise_rule') or '',
            delivery_promise_rule=kb_policy_overrides.get('delivery_promise_rule') or rules_cfg.get('delivery_promise_rule') or '',
            return_policy_summary=kb_policy_overrides.get('return_policy_summary') or rules_cfg.get('return_policy_summary') or '',
            forbidden_claims=kb_policy_overrides.get('forbidden_claims') or rules_cfg.get('forbidden_claims') or [],
            forbidden_promises=kb_policy_overrides.get('forbidden_promises') or rules_cfg.get('forbidden_promises') or [],
        )
        # Build a unified agent_preferences dict from the sales_agent block
        agent_preferences = {
            'enabled': sa.get('enabled', True),
            'handoff_mode': sa.get('handoff_mode') or 'balanceado',
            'followup_mode': sa.get('followup_mode') or 'suave',
            'max_followups': sa.get('max_followups') or 3,
            'recommendation_depth': sa.get('recommendation_depth') or 3,
            'max_response_length': sa.get('max_response_length') or 'standard',
            'model_name': sa.get('model_name') or 'gpt-4.1-nano',
            'autonomy_level': sa.get('autonomy_level') or 'full',
        }
        return SalesContext(
            agent_name=sa.get('name') or 'Sales Agent',
            business=business,
            brand=brand,
            playbook=playbook,
            commerce_rules=rules,
            catalog_snapshot=_load_catalog_snapshot(organization),
            knowledge_snapshot=_load_knowledge_snapshot(organization),
            buyer_model=buyer_model_cfg,
            activation_checklist={},
            agent_preferences=agent_preferences,
        )
    except Exception as exc:
        logger.warning('sales_agent_context_load_error', error=str(exc))
        return SalesContext(business=BusinessContext(org_name=getattr(organization, 'name', ''), org_slug=getattr(organization, 'slug', '')))


def _load_catalog_snapshot(organization) -> list[dict[str, Any]]:
    try:
        from apps.ecommerce.models import Product, ProductVariant

        products = list(
            Product.objects.filter(
                organization=organization,
                is_active=True,
                status='active',
            ).order_by('category', 'title').values(
                'id', 'title', 'brand', 'description', 'category',
                'offer_type', 'price_type', 'service_mode',
                'requires_booking', 'requires_shipping',
                'service_duration_minutes', 'capacity',
                'fulfillment_notes', 'tags',
            )[:60]
        )
        product_ids = [item['id'] for item in products if item.get('id')]
        variants_by_product: dict[Any, list[dict[str, Any]]] = {}
        if product_ids:
            variants = ProductVariant.objects.filter(product_id__in=product_ids).values(
                'product_id', 'sku', 'name', 'price',
                'stock', 'reserved', 'duration_minutes', 'capacity', 'metadata',
            )
            for variant in variants:
                variants_by_product.setdefault(variant.get('product_id'), []).append(variant)

        snapshot: list[dict[str, Any]] = []
        for product in products:
            offer_type = product.get('offer_type') or 'physical'
            is_service = offer_type == 'service'

            variant_data = []
            for variant in variants_by_product.get(product.get('id'), []):
                price = float(variant.get('price') or 0)
                stock = int(variant.get('stock') or 0)
                reserved = int(variant.get('reserved') or 0)
                available = max(0, stock - reserved)
                # Services don't deplete stock — treat as available unless stock is
                # explicitly set to a finite negative value by the operator.
                in_stock = True if is_service else available > 0
                v: dict[str, Any] = {
                    'name': variant.get('name', ''),
                    'sku': variant.get('sku', ''),
                    'price': price,
                    'in_stock': in_stock,
                }
                if not is_service:
                    v['available'] = available
                if variant.get('duration_minutes'):
                    v['duration_minutes'] = variant['duration_minutes']
                if variant.get('metadata'):
                    v['metadata'] = variant['metadata']
                variant_data.append(v)

            prices = [v['price'] for v in variant_data if v['price'] > 0]
            entry: dict[str, Any] = {
                'title': product.get('title', ''),
                'brand': product.get('brand') or '',
                'category': product.get('category') or '',
                'description': ' '.join((product.get('description') or '').split())[:220],
                'offer_type': offer_type,
                'price_type': product.get('price_type') or 'fixed',
                'service_mode': product.get('service_mode') or 'not_applicable',
                'requires_shipping': bool(product.get('requires_shipping')),
                'requires_booking': bool(product.get('requires_booking')),
                'any_in_stock': True if is_service else any(v['in_stock'] for v in variant_data),
                'variants': variant_data,
                'tags': product.get('tags') or [],
            }
            if prices:
                entry['min_price'] = min(prices)
                entry['max_price'] = max(prices)
            if product.get('service_duration_minutes'):
                entry['service_duration_minutes'] = product['service_duration_minutes']
            if product.get('capacity'):
                entry['capacity'] = product['capacity']
            if product.get('fulfillment_notes'):
                entry['fulfillment_notes'] = ' '.join(product['fulfillment_notes'].split())[:160]
            snapshot.append(entry)
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
        ).order_by('purpose', 'category', 'title')[:20]
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


def _create_followup_task(conversation, organization, stage: str, message_text: str, buyer: BuyerProfile) -> None:
    try:
        from django.utils import timezone

        from apps.ai_engine.models import AITask
        from apps.channels_config.models import ChannelConfig
        from apps.channels_config.settings_schema import normalise_settings

        if conversation is None:
            return

        settings = {}
        org_id = getattr(organization, 'id', None)
        if _has_real_identifier(org_id):
            config = ChannelConfig.objects.filter(organization=organization, channel='onboarding').only('settings').first()
            settings = (config.settings if config else {}) or {}

        s = normalise_settings(settings)
        sa = s['sales_agent']
        followup_mode = sa.get('followup_mode', 'suave')
        normalized_followup_mode = {
            'suave': 'soft',
            'soft': 'soft',
            'agresivo': 'aggressive',
            'aggressive': 'aggressive',
        }.get(str(followup_mode).lower(), 'soft')
        max_attempts = int(sa.get('max_followups', 3) or 3)
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
