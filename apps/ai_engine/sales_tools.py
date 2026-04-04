"""
Sales Agent tools — read-only access to commerce data.
These are the only data sources the Sales Agent is allowed to query.
No write operations. No pricing modifications. No inventory updates.
"""
from __future__ import annotations

import structlog
from django.db.models import Q

logger = structlog.get_logger(__name__)


def lookup_products(organization, query: str, limit: int = 5) -> list[dict]:
    """
    Search active products in the organization's catalog by query text.
    Matches against title, description, category, brand and tags.
    """
    try:
        from apps.ecommerce.models import Product

        words = [w for w in query.lower().split() if len(w) > 2][:5]
        if not words:
            products = Product.objects.filter(
                organization=organization, is_active=True, status='active'
            ).prefetch_related('variants')[:limit]
        else:
            q_filter = Q()
            for w in words:
                q_filter |= (
                    Q(title__icontains=w)
                    | Q(description__icontains=w)
                    | Q(category__icontains=w)
                    | Q(brand__icontains=w)
                )
            products = Product.objects.filter(
                organization=organization, is_active=True, status='active'
            ).filter(q_filter).prefetch_related('variants')[:limit]

        return [_serialize_product(p) for p in products]

    except Exception as exc:
        logger.warning('sales_tool_lookup_products_error', error=str(exc))
        return []


def check_stock(organization, product_id: str) -> dict:
    """
    Return available stock for all variants of a product.
    available = stock - reserved
    """
    try:
        from apps.ecommerce.models import ProductVariant

        variants = ProductVariant.objects.filter(product__organization=organization, product_id=product_id)
        result = []
        for v in variants:
            available = v.stock - v.reserved
            result.append({
                'variant_id': str(v.id),
                'sku': v.sku,
                'name': v.name,
                'stock': v.stock,
                'reserved': v.reserved,
                'available': available,
                'price': str(v.price),
                'in_stock': available > 0,
            })
        total_available = sum(r['available'] for r in result)
        return {
            'product_id': product_id,
            'variants': result,
            'total_available': total_available,
            'any_in_stock': total_available > 0,
        }

    except Exception as exc:
        logger.warning('sales_tool_check_stock_error', error=str(exc))
        return {'product_id': product_id, 'any_in_stock': None, 'variants': []}


def get_active_promotions(organization) -> list[dict]:
    """
    Return active promotions for the organization.
    Reads from onboarding/channel settings until a dedicated promotions model exists.
    """
    try:
        from apps.channels_config.models import ChannelConfig

        config = ChannelConfig.objects.filter(
            organization=organization,
            channel='onboarding',
        ).only('settings').first()
        settings = (config.settings if config else {}) or {}
        promos = settings.get('active_promotions', [])
        if not promos:
            promos = (settings.get('commerce_rules') or {}).get('active_promotions', [])
        return promos if isinstance(promos, list) else []
    except Exception as exc:
        logger.warning('sales_tool_get_active_promotions_error', error=str(exc))
        return []


def get_order_history(organization, contact) -> list[dict]:
    """
    Return the last 5 orders for a contact (read-only, for context).
    """
    try:
        from apps.ecommerce.models import Order
        orders = Order.objects.filter(
            organization=organization, contact=contact
        ).order_by('-created_at')[:5]
        return [
            {
                'id': str(o.id),
                'order_kind': o.order_kind,
                'status': o.status,
                'total': str(o.total),
                'currency': o.currency,
                'created_at': o.created_at.isoformat(),
            }
            for o in orders
        ]
    except Exception:
        return []


def _serialize_product(product) -> dict:
    variants = []
    for v in product.variants.all():
        variants.append({
            'id': str(v.id),
            'sku': v.sku,
            'name': v.name,
            'price': str(v.price),
            'available': max(0, v.stock - v.reserved),
            'in_stock': (v.stock - v.reserved) > 0,
        })

    min_price = None
    if variants:
        prices = [float(v['price']) for v in variants if float(v['price']) > 0]
        if prices:
            min_price = min(prices)

    return {
        'id': str(product.id),
        'title': product.title,
        'brand': product.brand,
        'category': product.category,
        'description': product.description[:300] if product.description else '',
        'offer_type': product.offer_type,
        'price_type': product.price_type,
        'requires_shipping': product.requires_shipping,
        'requires_booking': product.requires_booking,
        'min_price': min_price,
        'variants': variants,
        'any_in_stock': any(v['in_stock'] for v in variants),
        'tags': product.tags or [],
        'promotion': (product.attributes or {}).get('promotion', {}),
    }
