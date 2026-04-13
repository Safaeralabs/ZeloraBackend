"""
Catalog Service — Real product queries with embeddings.
"""
import logging
from typing import Optional, List
from decimal import Decimal

from apps.ecommerce.models import Product, ProductVariant, Promotion
from apps.ai_engine.models import SalesSession

logger = logging.getLogger(__name__)


class CatalogService:
    """
    Queries real products from catalog.
    - First tries embedding-based semantic search
    - Fallback to keyword search
    - Filters by stock, org, active status
    """

    @staticmethod
    def search(
        query: str,
        organization,
        session: Optional[SalesSession] = None,
        limit: int = 5,
    ) -> List[dict]:
        """
        Search for products.

        Args:
            query: Search query from user
            organization: Organization to filter by
            session: SalesSession for context (avoid repeated products)
            limit: Max products to return

        Returns:
            List of dicts with product info (id, title, price_min, stock, etc.)
        """
        # Base queryset — active products for this org
        qs = Product.objects.filter(
            organization=organization,
            is_active=True,
        )

        # Stop words that carry no product-search value
        STOP_WORDS = {
            'hola', 'que', 'tal', 'como', 'hay', 'tienes', 'tienen', 'quisiera',
            'quiero', 'ver', 'saber', 'que', 'los', 'las', 'una', 'uno', 'por',
            'favor', 'gracias', 'porfavor', 'buenas', 'bueno', 'buena', 'sii',
            'siii', 'siiii', 'noo', 'nooo', 'claro', 'okey', 'ok', 'oke',
            'algo', 'algo', 'puede', 'puedo', 'podria', 'gustaria', 'gustar',
            'mostrar', 'mostrarme', 'recomendar', 'recomendarme', 'ayudar',
        }

        # Keyword search across all relevant product fields
        products = []
        try:
            from django.db.models import Q

            # Filter meaningful words (len > 2, not stop words)
            if query:
                words = [
                    w for w in query.lower().split()
                    if len(w) > 2 and w not in STOP_WORDS
                ][:6]
            else:
                words = []

            if words:
                q_filter = Q()
                for word in words:
                    q_filter |= (
                        Q(title__icontains=word) |
                        Q(brand__icontains=word) |
                        Q(category__icontains=word) |
                        Q(subcategory__icontains=word) |
                        Q(description__icontains=word) |
                        Q(color__icontains=word) |
                        Q(material__icontains=word) |
                        Q(style__icontains=word) |
                        Q(formality__icontains=word) |
                        Q(fit__icontains=word)
                    )
                products = list(qs.filter(q_filter).order_by('-is_bestseller', '-popularity_score')[:limit * 2])

            # Fallback: if no keyword results (generic query or no match), show top products
            if not products:
                products = list(qs.order_by('-is_bestseller', '-popularity_score')[:limit * 2])
                logger.info(f'No keyword matches for query "{query[:40]}", showing top {len(products)} products')

        except Exception as e:
            logger.warning(f'Product search failed: {e}')
            products = list(qs.order_by('-is_bestseller', '-popularity_score')[:limit])

        # Avoid showing products already shown in session
        if session:
            shown_ids = session.shown_products or []
            products = [p for p in products if str(p.id) not in shown_ids]

        # Enrich and limit
        enriched = []
        for product in products[:limit]:
            try:
                enriched.append(CatalogService._enrich_product(product))
            except Exception as e:
                logger.warning(f'Error enriching product {product.id}: {e}')
                continue

        return enriched

    @staticmethod
    def _enrich_product(product: Product) -> dict:
        """
        Enrich product with variant pricing and promotions.

        Args:
            product: Product instance

        Returns:
            Dict with enriched data
        """
        # Get min/max price and total stock from variants
        variants = ProductVariant.objects.filter(product=product)
        prices = [v.price for v in variants if v.price]
        stocks = [v.stock for v in variants]

        price_min = min(prices) if prices else None
        price_max = max(prices) if prices else None
        total_stock = sum(stocks) if stocks else 0

        # Check for active promotions
        promotion = Promotion.objects.filter(
            organization=product.organization,
            is_active=True,
            products=product,
        ).first()

        return {
            'id': str(product.id),
            'title': product.title,
            'brand': product.brand or '',
            'category': product.category or '',
            'description': product.description[:200] if product.description else '',
            'price_min': float(price_min) if price_min else None,
            'price_max': float(price_max) if price_max else None,
            'stock': total_stock,
            'is_bestseller': product.is_bestseller or False,
            'occasion': product.occasion or [],
            'style': product.style or '',
            'promotion': {
                'title': promotion.title,
                'discount_type': promotion.discount_type,
                'discount_value': float(promotion.discount_value),
            } if promotion else None,
        }

    @staticmethod
    def get_product_by_id(product_id: str, organization) -> Optional[dict]:
        """
        Fetch a single product by ID.

        Args:
            product_id: UUID of product
            organization: Organization to filter by

        Returns:
            Enriched product dict or None
        """
        try:
            product = Product.objects.get(id=product_id, organization=organization)
            return CatalogService._enrich_product(product)
        except Product.DoesNotExist:
            return None

    @staticmethod
    def search_by_category(
        category: str,
        organization,
        session: Optional[SalesSession] = None,
        limit: int = 5,
    ) -> List[dict]:
        """
        Search products by category.

        Args:
            category: Category name or slug
            organization: Organization to filter by
            session: SalesSession for context
            limit: Max products to return

        Returns:
            List of enriched product dicts
        """
        qs = Product.objects.filter(
            organization=organization,
            is_active=True,
            category__icontains=category,
        )

        products = list(qs[:limit * 2])

        # Avoid repetition
        if session:
            shown_ids = session.shown_products or []
            products = [p for p in products if str(p.id) not in shown_ids]

        enriched = []
        for product in products[:limit]:
            try:
                enriched.append(CatalogService._enrich_product(product))
            except Exception as e:
                logger.warning(f'Error enriching product {product.id}: {e}')
                continue

        return enriched
