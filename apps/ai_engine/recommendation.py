"""
Recommendation engine with composite scoring.

Weights:
  - aesthetic_fit: 0.45 (style, occasion, formality, target_audience)
  - intent_fit: 0.30 (stage-dependent, urgency, stock)
  - commercial_fit: 0.15 (promotions, bestseller, stock status)
  - popularity: 0.10 (popularity_score)

Output: products scored and ranked, top 3 returned with breakdown.
"""
from __future__ import annotations

import re
import structlog
from typing import Any

from .sales_models import BuyerProfile, STAGE_INTENT_TO_BUY, STAGE_CONSIDERING, STAGE_DISCOVERING

logger = structlog.get_logger(__name__)


def _extract_occasion_hints(message_text: str) -> list[str]:
    """Extract occasion keywords from buyer message."""
    occasions = []
    occasion_keywords = {
        'boda': ['boda', 'casamiento', 'matrimonio', 'wedding'],
        'cumpleaños': ['cumpleaños', 'birthday', 'cumple'],
        'trabajo': ['trabajo', 'laboral', 'empresa', 'trabajo', 'negocios', 'business'],
        'cena': ['cena', 'dinner', 'comida', 'almuerzo'],
        'casual': ['casual', 'relajado', 'domingo', 'fin de semana', 'weekend'],
        'formal': ['formal', 'importante', 'evento', 'gala', 'elegante'],
    }
    text_lower = message_text.lower()
    for occasion, keywords in occasion_keywords.items():
        if any(kw in text_lower for kw in keywords):
            occasions.append(occasion)
    return occasions


def _aesthetic_fit(product: dict, buyer: BuyerProfile, occasion_hints: list[str]) -> float:
    """
    Score product aesthetic fit: style, occasion, formality, target_audience match.
    Max: 1.0
    """
    score = 0.0

    # Formality match: +0.3 if product.formality matches buyer priority
    product_formality = product.get('formality', '').lower()
    if buyer.priority == 'quality' and product_formality in ('formal', 'semiformal'):
        score += 0.3

    # Occasion match: +0.3 if product.occasion overlaps with buyer hints
    product_occasions = product.get('occasion', [])
    if occasion_hints and any(occ in occasion_hints for occ in product_occasions):
        score += 0.3

    # Style match: +0.2 if product.style aligns (heuristic)
    product_style = product.get('style', '').lower()
    if buyer.style == 'direct' and product_style in ('casual', 'practical'):
        score += 0.2
    elif buyer.style == 'comparative' and product_style in ('formal', 'elegant'):
        score += 0.15

    # Target audience match: +0.2 if product.target_audience has relevant words
    product_target = product.get('target_audience', '').lower()
    if product_target and any(
        word in product_target for word in ['adult', 'professional', 'women', 'men', 'young']
    ):
        score += 0.2

    return min(score, 1.0)


def _intent_fit(
    product: dict, stage: str, buyer: BuyerProfile, has_variants_in_stock: bool
) -> float:
    """
    Score product fit for buyer's purchase stage and urgency.
    Max: 1.0
    """
    score = 0.0

    # Stage-specific scoring
    if stage == STAGE_INTENT_TO_BUY:
        # Prioritize in-stock products
        if has_variants_in_stock:
            score += 0.4
        else:
            score -= 0.2
    elif stage == STAGE_CONSIDERING:
        # Prioritize bestsellers (social proof for decision-making)
        if product.get('is_bestseller', False):
            score += 0.3
    elif stage == STAGE_DISCOVERING:
        # Penalize products without description
        if not product.get('description', '').strip():
            score -= 0.2
        else:
            score += 0.1

    # Urgency-dependent scoring
    if buyer.urgency == 'immediate' and has_variants_in_stock:
        score += 0.2
    elif buyer.urgency == 'this_week' and has_variants_in_stock:
        score += 0.1

    return min(max(score, 0.0), 1.0)


def _commercial_fit(
    product: dict, promotions: list[dict], has_variants_in_stock: bool
) -> float:
    """
    Score product commercial appeal: promotions, bestseller status, stock.
    Max: 1.0
    """
    score = 0.0

    # Promo applicability: +0.4 if any promo applies to this product
    product_id = product.get('id')
    product_category = product.get('category', '').lower()
    for promo in promotions:
        applies_to = promo.get('applies_to', '')
        if applies_to == 'all_products':
            score += 0.4
            break
        elif applies_to == 'category' and promo.get('category', '').lower() == product_category:
            score += 0.4
            break
        elif applies_to == 'specific_products' and product_id in promo.get('product_ids', []):
            score += 0.4
            break

    # Bestseller bonus: +0.3
    if product.get('is_bestseller', False):
        score += 0.3

    # Stock availability: +0.3 if has variants in stock
    if has_variants_in_stock:
        score += 0.3

    return min(score, 1.0)


def _popularity_score(product: dict) -> float:
    """
    Normalize product popularity to 0–1 scale.
    popularity_score is 0–100 in database.
    """
    raw_score = product.get('popularity_score', 0.0)
    # Normalize to 0-1 (cap at 100)
    return min(raw_score / 100.0, 1.0)


def score_and_rank_products(
    products: list[dict],
    buyer: BuyerProfile,
    stage: str,
    promotions: list[dict],
    message_text: str,
) -> list[dict]:
    """
    Score and rank products using composite formula.

    Formula:
      score = 0.45 * aesthetic_fit
            + 0.30 * intent_fit
            + 0.15 * commercial_fit
            + 0.10 * popularity

    Args:
      products: list of product dicts (from _serialize_product)
      buyer: BuyerProfile instance
      stage: current conversation stage
      promotions: active promotions list
      message_text: raw buyer message (for occasion extraction)

    Returns:
      Top 3 products sorted descending by score, each with 'recommendation_score' and 'score_breakdown'.
    """
    if not products:
        return []

    try:
        occasion_hints = _extract_occasion_hints(message_text)

        scored_products = []
        for product in products:
            # Check stock availability
            variants = product.get('variants', [])
            has_stock = any(v.get('in_stock', False) for v in variants)

            # Compute component scores
            aes = _aesthetic_fit(product, buyer, occasion_hints)
            intent = _intent_fit(product, stage, buyer, has_stock)
            comm = _commercial_fit(product, promotions, has_stock)
            pop = _popularity_score(product)

            # Composite score
            total_score = 0.45 * aes + 0.30 * intent + 0.15 * comm + 0.10 * pop

            # Augment product dict with scoring info
            product_copy = product.copy()
            product_copy['recommendation_score'] = round(total_score, 3)
            product_copy['score_breakdown'] = {
                'aesthetic_fit': round(aes, 3),
                'intent_fit': round(intent, 3),
                'commercial_fit': round(comm, 3),
                'popularity': round(pop, 3),
            }

            scored_products.append((product_copy, total_score))

        # Sort by score descending
        scored_products.sort(key=lambda x: x[1], reverse=True)

        # Return top 3 with scores
        return [p for p, _ in scored_products[:3]]

    except Exception as exc:
        logger.warning('recommendation_scoring_error', error=str(exc))
        # Fallback: return first limit products unchanged
        return products[:3]
