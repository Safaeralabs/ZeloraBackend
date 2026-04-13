"""
Recommendation Engine — Product recommendations using relations, promotions, occasion filters.
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal

from apps.ecommerce.models import Product, ProductRelation, Promotion
from .catalog import CatalogService
from .promo import PromoEngine

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """
    Builds product recommendations based on ProductRelation graph and promotions.
    """

    # Relation type weights for recommendation scoring
    RELATION_WEIGHTS = {
        'combina_con': 0.8,  # strong signal for bundle/add-on
        'bundle_con': 1.0,   # strongest — explicit bundle
        'alternativa_premium': 0.7,  # upsell opportunity
        'alternativa_barata': 0.6,   # downgrade/budget alternative
        'similar_a': 0.5,    # fallback if no other relations
        'evita_con': -0.5,   # negative signal, avoid
    }

    @staticmethod
    def build(
        base_products: List[str],
        session,
        organization,
    ) -> Dict:
        """
        Build recommendation set based on base products and session context.

        Args:
            base_products: List of product IDs (UUIDs) as base for recommendations
            session: SalesSession instance
            organization: Organization to filter by

        Returns:
            RecommendationSet dict with:
            {
              "primary": {product dict},
              "alternatives": [{product dict}, ...],
              "bundle": [{product dict}, ...],
              "reasoning": str
            }
        """
        if not base_products:
            return {
                'primary': None,
                'alternatives': [],
                'bundle': [],
                'reasoning': 'No base products to recommend from.',
            }

        recommendations = {
            'primary': None,
            'alternatives': [],
            'bundle': [],
            'reasoning': '',
        }

        try:
            # Fetch all relations for base products
            relations = ProductRelation.objects.filter(
                organization=organization,
                source_product_id__in=base_products,
            ).select_related('target_product').order_by('-weight')

            # Score and rank candidates
            candidates = {}  # {product_id: {product, relation_type, weight, score}}

            for relation in relations:
                target = relation.target_product

                # Skip if already in session.selected_products
                if str(target.id) in session.selected_products:
                    continue

                # Negative signal from 'evita_con' — skip
                if relation.relation_type == 'evita_con':
                    continue

                # Enrich product
                enriched = CatalogService._enrich_product(target)
                if not enriched or enriched.get('stock', 0) <= 0:
                    continue

                # Calculate score: relation weight + promotion bonus
                relation_weight = RecommendationEngine.RELATION_WEIGHTS.get(
                    relation.relation_type, 0.5
                )
                score = relation_weight * relation.weight  # 0–1 scale

                # Boost score if product has active promotion
                promos = PromoEngine.get_active(organization, products=[str(target.id)])
                if promos:
                    score += 0.2  # promotion bonus

                # Occasion filter: if session has category_interest, prefer matching occasions
                if session.category_interest and enriched.get('occasion'):
                    if session.category_interest.lower() in [o.lower() for o in enriched.get('occasion', [])]:
                        score += 0.15

                if str(target.id) not in candidates:
                    candidates[str(target.id)] = {
                        'product': enriched,
                        'relation_type': relation.relation_type,
                        'weight': relation.weight,
                        'score': score,
                    }
                else:
                    # If multiple relations, keep highest score
                    if score > candidates[str(target.id)]['score']:
                        candidates[str(target.id)]['score'] = score
                        candidates[str(target.id)]['relation_type'] = relation.relation_type

            # Sort by score
            sorted_candidates = sorted(
                candidates.values(),
                key=lambda x: x['score'],
                reverse=True,
            )

            # Classify into categories and limit
            primary_relations = ['combina_con', 'bundle_con']
            alternative_relations = ['alternativa_premium', 'alternativa_barata', 'similar_a']

            primary_list = [
                c for c in sorted_candidates
                if c['relation_type'] in primary_relations
            ][:2]

            alternative_list = [
                c for c in sorted_candidates
                if c['relation_type'] in alternative_relations
            ][:2]

            # Set primary recommendation (highest score overall)
            if sorted_candidates:
                top = sorted_candidates[0]
                recommendations['primary'] = top['product']
                reasoning_parts = [
                    f"Basado en: {top['relation_type'].replace('_', ' ')}"
                ]
            else:
                recommendations['primary'] = None
                reasoning_parts = []

            # Set bundle recommendations (combina_con, bundle_con)
            if primary_list:
                recommendations['bundle'] = [c['product'] for c in primary_list][:2]
                if len(primary_list) > 1:
                    reasoning_parts.append(f"+ {len(primary_list)} opciones para combinar")

            # Set alternatives
            if alternative_list:
                recommendations['alternatives'] = [c['product'] for c in alternative_list][:2]

            recommendations['reasoning'] = ', '.join(reasoning_parts) if reasoning_parts else ''

            logger.info(
                f'Built recommendations: primary={bool(recommendations["primary"])}, '
                f'alternatives={len(recommendations["alternatives"])}, '
                f'bundle={len(recommendations["bundle"])}'
            )

        except Exception as e:
            logger.error(f'Recommendation building failed: {e}')

        return recommendations

    @staticmethod
    def format_for_llm(recommendation_set: Dict) -> str:
        """
        Format recommendation set for inclusion in LLM system prompt.

        Args:
            recommendation_set: RecommendationSet dict from build()

        Returns:
            Formatted markdown string
        """
        if not recommendation_set or not (
            recommendation_set.get('primary')
            or recommendation_set.get('alternatives')
            or recommendation_set.get('bundle')
        ):
            return ''

        lines = []

        if recommendation_set.get('primary'):
            primary = recommendation_set['primary']
            lines.append('## Recommended Product')
            price_str = f"${primary['price_min']}" if primary.get('price_min') else 'Contact for price'
            lines.append(f"- **{primary['title']}**: {price_str}")
            if primary.get('promotion'):
                promo = primary['promotion']
                lines.append(f"  Special offer: {promo['title']}")
            lines.append('')

        if recommendation_set.get('bundle'):
            lines.append('## Great Combinations')
            for product in recommendation_set['bundle'][:2]:
                price_str = f"${product['price_min']}" if product.get('price_min') else 'Contact for price'
                lines.append(f"- {product['title']}: {price_str}")
            lines.append('')

        if recommendation_set.get('alternatives'):
            lines.append('## Other Options')
            for product in recommendation_set['alternatives'][:2]:
                price_str = f"${product['price_min']}" if product.get('price_min') else 'Contact for price'
                lines.append(f"- {product['title']}: {price_str}")
            lines.append('')

        if recommendation_set.get('reasoning'):
            lines.append(f'*{recommendation_set["reasoning"]}*')

        return '\n'.join(lines)
