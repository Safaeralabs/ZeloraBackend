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
    P1.2: Tries semantic search (embeddings + cosine similarity) first, falls back to keyword matching.
    Matches against title, description, category, brand, and P1.1 enriched attributes.
    """
    try:
        from apps.ecommerce.models import Product
        import os

        # P1.2: Try semantic search first if API key and embeddings available
        api_key = os.environ.get('OPENAI_API_KEY', '')
        if api_key:
            from .sales_kb import _embed_query, _cosine_similarity

            query_vec = _embed_query(query)
            if query_vec:
                # Get all products with embeddings for this org
                all_products = Product.objects.filter(
                    organization=organization,
                    is_active=True,
                    status='active'
                ).exclude(embedding_vector=[]).prefetch_related('variants')

                # Score by cosine similarity
                scored = []
                for p in all_products:
                    if p.embedding_vector:
                        score = _cosine_similarity(query_vec, p.embedding_vector)
                        if score > 0.20:  # threshold matching KB
                            scored.append((p, score))

                # Sort by score descending, take top limit
                scored.sort(key=lambda x: x[1], reverse=True)
                products = [p for p, _ in scored[:limit]]

                if products:
                    return [_serialize_product(p) for p in products]
                # Fall through to keyword search if no semantic matches

        # P1.2 Fallback: keyword search (existing logic)
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
                    | Q(subcategory__icontains=w)  # P1.1
                    | Q(style__icontains=w)  # P1.1
                    | Q(color__icontains=w)  # P1.1
                    | Q(material__icontains=w)  # P1.1
                    | Q(formality__icontains=w)  # P1.1
                    | Q(target_audience__icontains=w)  # P1.1
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


def get_active_promotions(organization, product=None) -> list[dict]:
    """
    Return active promotions for the organization.
    P1.1: Now reads from dedicated Promotion model first, with fallback to settings.
    Optionally filters promotions applicable to a specific product.
    """
    try:
        from apps.ecommerce.models import Promotion
        from django.utils import timezone

        now = timezone.now()

        # Query from Promotion model
        qs = Promotion.objects.filter(
            organization=organization,
            is_active=True,
        ).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now),
            Q(ends_at__isnull=True) | Q(ends_at__gte=now),
        )

        # Filter by product if provided
        if product:
            qs = qs.filter(
                Q(applies_to='all_products')
                | Q(applies_to='category', category=product.category)
                | Q(applies_to='specific_products', products=product)
            )

        promos = [
            {
                'id': str(p.id),
                'title': p.title,
                'description': p.description,
                'discount_type': p.discount_type,
                'discount_value': float(p.discount_value),
                'applies_to': p.applies_to,
            }
            for p in qs[:5]
        ]

        if promos:
            return promos

        # Fallback to ChannelConfig settings if no Promotion model results
        from apps.channels_config.models import ChannelConfig

        config = ChannelConfig.objects.filter(
            organization=organization,
            channel='onboarding',
        ).only('settings').first()
        settings = (config.settings if config else {}) or {}
        fallback_promos = settings.get('active_promotions', [])
        if not fallback_promos:
            fallback_promos = (settings.get('commerce_rules') or {}).get('active_promotions', [])
        return fallback_promos if isinstance(fallback_promos, list) else []

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
        'subcategory': product.subcategory,  # P1.1
        'description': product.description[:300] if product.description else '',
        'offer_type': product.offer_type,
        'price_type': product.price_type,
        'requires_shipping': product.requires_shipping,
        'requires_booking': product.requires_booking,
        'min_price': min_price,
        'variants': variants,
        'any_in_stock': any(v['in_stock'] for v in variants),
        'tags': product.tags or [],
        'occasion': product.occasion or [],  # P1.1
        'style': product.style,  # P1.1
        'color': product.color,  # P1.1
        'material': product.material,  # P1.1
        'fit': product.fit,  # P1.1
        'formality': product.formality,  # P1.1
        'target_audience': product.target_audience,  # P1.1
        'is_bestseller': product.is_bestseller,  # P1.1
        'promotion': (product.attributes or {}).get('promotion', {}),  # Legacy fallback
    }
