"""
Promo Engine — Active promotions matching customer and products.
"""
import logging
from typing import List, Optional
from datetime import datetime, timezone

from apps.ecommerce.models import Promotion

logger = logging.getLogger(__name__)


class PromoEngine:
    """
    Finds and returns active promotions relevant to products or customer context.
    """

    @staticmethod
    def get_active(
        organization,
        products: Optional[List[str]] = None,
        category: Optional[str] = None,
    ) -> List[dict]:
        """
        Get active promotions matching criteria.

        Args:
            organization: Organization to filter by
            products: Optional list of product IDs (UUID strings)
            category: Optional category to match

        Returns:
            List of promotion dicts
        """
        now = datetime.now(timezone.utc)

        # Base filter: org, active, time-valid
        qs = Promotion.objects.filter(
            organization=organization,
            is_active=True,
            starts_at__lte=now,
        ).exclude(ends_at__lt=now)

        promos = []

        # If products specified, find promos matching those products or their categories
        if products:
            product_promos = list(qs.filter(products__id__in=products).distinct())
            promos.extend(product_promos)

            # Also find category-wide promos for those products
            if category:
                category_promos = list(qs.filter(
                    applies_to='category',
                    category__icontains=category,
                ).distinct())
                promos.extend(category_promos)
        elif category:
            promos = list(qs.filter(
                applies_to='category',
                category__icontains=category,
            ))
        else:
            promos = list(qs.filter(applies_to='all_products'))

        # Remove duplicates
        seen_ids = set()
        unique_promos = []
        for promo in promos:
            if promo.id not in seen_ids:
                unique_promos.append(promo)
                seen_ids.add(promo.id)

        return [PromoEngine._enrich_promotion(p) for p in unique_promos[:3]]

    @staticmethod
    def _enrich_promotion(promo: Promotion) -> dict:
        """
        Enrich promotion with details.

        Args:
            promo: Promotion instance

        Returns:
            Dict with promotion data
        """
        return {
            'id': str(promo.id),
            'title': promo.title,
            'description': promo.description or '',
            'discount_type': promo.discount_type,
            'discount_value': float(promo.discount_value),
            'applies_to': promo.applies_to,
            'category': promo.category or None,
            'starts_at': promo.starts_at.isoformat() if promo.starts_at else None,
            'ends_at': promo.ends_at.isoformat() if promo.ends_at else None,
        }

    @staticmethod
    def format_for_llm(promos: List[dict]) -> str:
        """
        Format promotions for inclusion in LLM system prompt.

        Args:
            promos: List of enriched promotion dicts

        Returns:
            Formatted markdown string
        """
        if not promos:
            return ''

        lines = ['## Active Promotions']
        for promo in promos:
            lines.append(f"- **{promo['title']}**: {promo['description']}")
            if promo['discount_type'] == 'percentage':
                lines.append(f"  {promo['discount_value']:.0f}% off")
            elif promo['discount_type'] == 'fixed_amount':
                lines.append(f"  ${promo['discount_value']:.2f} off")
            elif promo['discount_type'] == 'free_shipping':
                lines.append(f"  Free shipping")
            elif promo['discount_type'] == 'bundle':
                lines.append(f"  Bundle offer: ${promo['discount_value']:.2f}")

        return '\n'.join(lines)
