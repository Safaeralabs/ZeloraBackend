"""
Catalog Service — Stable catalog lookup and product serialization.
"""
import logging
import re
from typing import Optional, List, Tuple
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.ecommerce.models import Product, ProductVariant, Promotion
from apps.ai_engine.models import SalesSession
from .product_query import ProductQueryInterpreter

logger = logging.getLogger(__name__)

# Below this cosine similarity, a semantic match is considered noise rather
# than a real alternative — same threshold KBService uses for article ranking.
SEMANTIC_MIN_SIMILARITY = 0.25
SEMANTIC_CANDIDATE_CAP = 300


class CatalogService:
    """
    Queries real products from catalog.
    - Exact title match first
    - Keyword search (interpreted query) second
    - Embedding-based semantic search as a fallback when keywords find nothing
      (e.g. "camisa" finding "blusa" when the store has no literal "camisa")
    - Filters by stock, org, active status for anything shown as purchasable
    """

    @staticmethod
    def search(
        query: str,
        organization,
        session: Optional[SalesSession] = None,
        limit: int = 5,
    ) -> List[dict]:
        """
        Search for purchasable (in-stock) products.

        Args:
            query: Search query from user
            organization: Organization to filter by
            session: SalesSession for context (avoid repeated products)
            limit: Max products to return

        Returns:
            List of dicts with product info (id, title, price_min, stock, etc.)
        """
        resolution = CatalogService.resolve_query(
            query=query,
            organization=organization,
            session=session,
            limit=limit,
        )
        return resolution['products']

    @staticmethod
    def resolve_query(
        query: str,
        organization,
        session: Optional[SalesSession] = None,
        limit: int = 5,
    ) -> dict:
        normalized_query = (query or '').strip()

        # Base queryset — active products for this org (stock is NOT filtered
        # here; that split happens per-branch so out-of-stock matches can still
        # surface as "unavailable_products" instead of looking nonexistent).
        qs = Product.objects.filter(
            organization=organization,
            is_active=True,
        )

        # Exact resolution first: if the user asks for a very specific product,
        # do not silently fall back to generic bestsellers.
        exact_products = CatalogService._find_exact_matches(qs, normalized_query)
        if exact_products:
            available, unavailable = CatalogService._split_products(exact_products, limit=limit)
            if available:
                return {
                    'products': available,
                    'unavailable_products': unavailable,
                    'resolution': {
                        'match_type': 'exact',
                        'needs_confirmation': False,
                        'query_type': 'exact_product',
                        'interpreted_query': normalized_query,
                        'reason': 'exact_match',
                        'confidence': 1.0,
                        'product_name': normalized_query,
                        'category': '',
                        'color': '',
                        'search_terms': [],
                    },
                }
            # Exact title match, but every match is out of stock.
            return {
                'products': [],
                'unavailable_products': unavailable,
                'resolution': {
                    'match_type': 'exact_out_of_stock',
                    'needs_confirmation': False,
                    'query_type': 'exact_product',
                    'interpreted_query': normalized_query,
                    'reason': 'exact_match_out_of_stock',
                    'confidence': 1.0,
                    'product_name': normalized_query,
                    'category': '',
                    'color': '',
                    'search_terms': [],
                },
            }

        interpreted = ProductQueryInterpreter.interpret(normalized_query, session=session)
        available, unavailable = CatalogService._search_from_interpretation(
            qs=qs,
            interpreted=interpreted,
            session=session,
            limit=limit,
        )

        if available:
            needs_confirmation = (
                not interpreted.get('is_catalog_browse')
                and (
                    len(available) > 1
                    or interpreted.get('confidence', 0) < 0.75
                )
            )
            match_type = 'browse'
            if interpreted.get('product_name'):
                match_type = 'interpreted'
            if needs_confirmation:
                match_type = 'ambiguous'

            return {
                'products': available,
                'unavailable_products': unavailable,
                'resolution': {
                    'match_type': match_type,
                    'needs_confirmation': needs_confirmation,
                    'query_type': 'catalog_browse' if interpreted.get('is_catalog_browse') else 'product_lookup',
                    'interpreted_query': interpreted.get('product_name') or normalized_query,
                    'reason': 'llm_or_heuristic_interpretation',
                    'confidence': interpreted.get('confidence', 0.0),
                    'product_name': interpreted.get('product_name', ''),
                    'category': interpreted.get('category', ''),
                    'color': interpreted.get('color', ''),
                    'search_terms': interpreted.get('search_terms', []),
                },
            }

        if interpreted.get('is_catalog_browse'):
            top_available, top_unavailable = CatalogService._search_top_products(qs, session=session, limit=limit)
            return {
                'products': top_available,
                'unavailable_products': top_unavailable,
                'resolution': {
                    'match_type': 'browse',
                    'needs_confirmation': False,
                    'query_type': 'catalog_browse',
                    'interpreted_query': '',
                    'reason': 'catalog_browse_fallback',
                    'confidence': interpreted.get('confidence', 0.0),
                    'product_name': '',
                    'category': interpreted.get('category', ''),
                    'color': interpreted.get('color', ''),
                    'search_terms': interpreted.get('search_terms', []),
                },
            }

        if unavailable:
            # Keyword search matched something real, just not sellable right now.
            return {
                'products': [],
                'unavailable_products': unavailable,
                'resolution': {
                    'match_type': 'out_of_stock',
                    'needs_confirmation': False,
                    'query_type': 'product_lookup',
                    'interpreted_query': interpreted.get('product_name') or normalized_query,
                    'reason': 'matched_out_of_stock',
                    'confidence': interpreted.get('confidence', 0.0),
                    'product_name': interpreted.get('product_name', ''),
                    'category': interpreted.get('category', ''),
                    'color': interpreted.get('color', ''),
                    'search_terms': interpreted.get('search_terms', []),
                },
            }

        # Nothing via literal keywords — try a semantic fallback so synonyms
        # the customer's own vocabulary ("camisa") can still surface the
        # closest thing the store actually sells ("blusa").
        semantic_available, semantic_unavailable = CatalogService._semantic_fallback(
            query=normalized_query,
            qs=qs,
            organization=organization,
            session=session,
            limit=limit,
        )
        if semantic_available or semantic_unavailable:
            return {
                'products': semantic_available,
                'unavailable_products': semantic_unavailable,
                'resolution': {
                    'match_type': 'semantic',
                    'needs_confirmation': len(semantic_available) > 1,
                    'query_type': 'product_lookup',
                    'interpreted_query': normalized_query,
                    'reason': 'semantic_fallback',
                    'confidence': 0.5,
                    'product_name': interpreted.get('product_name', ''),
                    'category': interpreted.get('category', ''),
                    'color': interpreted.get('color', ''),
                    'search_terms': interpreted.get('search_terms', []),
                },
            }

        return {
            'products': [],
            'unavailable_products': [],
            'resolution': {
                'match_type': 'none',
                'needs_confirmation': False,
                'query_type': 'product_lookup',
                'interpreted_query': interpreted.get('product_name') or normalized_query,
                'reason': 'no_match',
                'confidence': interpreted.get('confidence', 0.0),
                'product_name': interpreted.get('product_name', ''),
                'category': interpreted.get('category', ''),
                'color': interpreted.get('color', ''),
                'search_terms': interpreted.get('search_terms', []),
            },
        }

    @staticmethod
    def build_embedding_text(product: Product) -> str:
        """
        Rich text used to embed a product (title + attrs + description).
        Shared by the create/update auto-embed hook and the backfill command
        so both stay in sync.
        """
        parts = [product.title]
        for value in (
            product.brand,
            product.category,
            product.subcategory,
            product.style,
            product.formality,
            product.color,
            product.material,
            product.fit,
            product.target_audience,
        ):
            if value:
                parts.append(value)
        if product.occasion:
            parts.append(', '.join(product.occasion))
        if product.description:
            parts.append(product.description[:300])
        return '\n'.join(parts)[:512]

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
        prices = [v.price for v in variants if v.price is not None]
        stocks = [max((v.stock or 0) - (v.reserved or 0), 0) for v in variants]

        price_min = min(prices) if prices else None
        price_max = max(prices) if prices else None
        total_stock = sum(stocks) if stocks else 0
        has_stock = total_stock > 0
        is_service_like = product.offer_type in ('service', 'hybrid') and not product.requires_shipping
        is_available = has_stock or is_service_like

        # Check for active promotions
        now = timezone.now()
        promotion = Promotion.objects.filter(
            organization=product.organization,
            is_active=True,
            scope='product',
        ).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now)
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gte=now)
        ).filter(
            Q(applies_to='all_products')
            | Q(applies_to='category', category__iexact=(product.category or ''))
            | Q(applies_to='specific_products', products=product)
        ).order_by('priority', '-updated_at').first()

        images = product.images or []
        image_url = images[0] if images else ''

        return {
            'id': str(product.id),
            'title': product.title,
            'brand': product.brand or '',
            'category': product.category or '',
            'description': product.description[:200] if product.description else '',
            'price_min': float(price_min) if price_min else None,
            'price_max': float(price_max) if price_max else None,
            'stock': total_stock,
            'is_available': is_available,
            'availability_label': 'Disponible' if is_available else 'Agotado',
            'offer_type': product.offer_type,
            'price_type': product.price_type,
            'requires_shipping': product.requires_shipping,
            'is_bestseller': product.is_bestseller or False,
            'requires_size': bool(product.requires_size),
            'made_to_order': bool(product.made_to_order),
            'occasion': product.occasion or [],
            'style': product.style or '',
            'image_url': image_url,
            'promotion': {
                'title': promotion.title,
                'discount_type': promotion.discount_type,
                'discount_value': float(promotion.discount_value),
            } if promotion else None,
        }

    @staticmethod
    def get_product_by_id(product_id: str, organization) -> Optional[dict]:
        """
        Fetch a single purchasable product by ID (returns None if out of stock).

        Args:
            product_id: UUID of product
            organization: Organization to filter by

        Returns:
            Enriched product dict or None
        """
        try:
            product = Product.objects.get(id=product_id, organization=organization)
            enriched = CatalogService._enrich_product(product)
            if not enriched.get('is_available'):
                return None
            return enriched
        except Product.DoesNotExist:
            return None

    @staticmethod
    def get_variant_snapshot(product_id: str, organization) -> dict:
        """
        Return a lightweight availability snapshot for product variants.
        Used for questions like "que tallas tienes?".
        """
        variants = ProductVariant.objects.filter(
            product_id=product_id,
            product__organization=organization,
            product__is_active=True,
        ).only('name', 'sku', 'stock', 'reserved')

        available = []
        unavailable = []
        for variant in variants:
            label = str(variant.name or variant.sku or '').strip()
            if not label:
                continue
            in_stock = max((variant.stock or 0) - (variant.reserved or 0), 0) > 0
            if in_stock:
                available.append(label)
            else:
                unavailable.append(label)

        return {
            'product_id': str(product_id or ''),
            'labels_available': list(dict.fromkeys(available)),
            'labels_unavailable': list(dict.fromkeys(unavailable)),
        }

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

        return CatalogService._serialize_products(products, limit=limit)

    @staticmethod
    def _serialize_products(products: List[Product], limit: int = 5) -> List[dict]:
        """Purchasable products only — kept for existing callers (search_by_category, tests)."""
        available, _unavailable = CatalogService._split_products(products, limit=limit)
        return available

    @staticmethod
    def _split_products(
        products: List[Product],
        limit: int = 5,
        unavailable_limit: int = 2,
    ) -> Tuple[List[dict], List[dict]]:
        """
        Enrich and bucket products into (available, unavailable) — out-of-stock
        matches are never silently dropped, so callers can decide whether to
        surface them (e.g. "lo tenemos pero esta agotado").
        """
        available: List[dict] = []
        unavailable: List[dict] = []
        for product in products:
            try:
                payload = CatalogService._enrich_product(product)
            except Exception as e:
                logger.warning(f'Error enriching product {product.id}: {e}')
                continue

            if payload.get('is_available'):
                if len(available) < limit:
                    available.append(payload)
            elif len(unavailable) < unavailable_limit:
                unavailable.append(payload)

            if len(available) >= limit and len(unavailable) >= unavailable_limit:
                break

        return available, unavailable

    @staticmethod
    def _normalize_query(value: str) -> str:
        value = (value or '').strip().lower()
        return re.sub(r'[^a-z0-9]+', ' ', value).strip()

    def _find_exact_matches(qs, query: str) -> List[Product]:
        normalized = CatalogService._normalize_query(query)
        if not normalized or len(normalized) < 4:
            return []

        compact = normalized.replace(' ', '')
        matches = []
        for product in qs.order_by('-is_bestseller', '-popularity_score')[:50]:
            title_norm = CatalogService._normalize_query(product.title)
            title_compact = title_norm.replace(' ', '')
            brand_norm = CatalogService._normalize_query(product.brand)

            if (
                normalized == title_norm
                or compact == title_compact
                or normalized in title_norm
                or title_norm in normalized
                or (brand_norm and normalized == f'{brand_norm} {title_norm}'.strip())
            ):
                matches.append(product)

        if matches:
            return matches

        return list(
            qs.filter(
                Q(title__iexact=query.strip()) |
                Q(title__icontains=query.strip())
            ).order_by('-is_bestseller', '-popularity_score')[:5]
        )

    @staticmethod
    def _search_top_products(qs, session: Optional[SalesSession], limit: int) -> Tuple[List[dict], List[dict]]:
        products = list(qs.order_by('-is_bestseller', '-popularity_score')[:limit * 2])
        if session:
            shown_ids = session.shown_products or []
            unseen = [p for p in products if str(p.id) not in shown_ids]
            # If all products were already shown, repeat top items instead of
            # returning an empty catalog response.
            products = unseen or products
        return CatalogService._split_products(products, limit=limit)

    @staticmethod
    def _search_from_interpretation(
        qs, interpreted: dict, session: Optional[SalesSession], limit: int
    ) -> Tuple[List[dict], List[dict]]:
        terms = CatalogService._build_search_terms(interpreted)
        if not terms:
            return [], []

        q_filter = Q()
        for term in terms:
            q_filter |= (
                Q(title__icontains=term) |
                Q(brand__icontains=term) |
                Q(category__icontains=term) |
                Q(subcategory__icontains=term) |
                Q(description__icontains=term) |
                Q(color__icontains=term) |
                Q(material__icontains=term) |
                Q(style__icontains=term) |
                Q(formality__icontains=term) |
                Q(fit__icontains=term)
            )

        products = list(qs.filter(q_filter).order_by('-is_bestseller', '-popularity_score')[:limit * 3])
        if session and interpreted.get('is_catalog_browse'):
            shown_ids = session.shown_products or []
            unseen = [p for p in products if str(p.id) not in shown_ids]
            # For browse-style queries ("que otros productos"), avoid false
            # "no products" when catalog is small and everything was shown.
            products = unseen or products

        return CatalogService._split_products(products, limit=limit)

    @staticmethod
    def _semantic_fallback(
        query: str,
        qs,
        organization,
        session: Optional[SalesSession],
        limit: int,
    ) -> Tuple[List[dict], List[dict]]:
        """
        Embedding-based similarity search — the fallback of last resort when
        literal keyword matching finds nothing. Lets a customer's own words
        ("camisa") find the closest thing the store actually sells ("blusa")
        without maintaining a hardcoded synonym dictionary.
        """
        if not query or not settings.OPENAI_API_KEY or not getattr(settings, 'ENABLE_REAL_AI', False):
            return [], []

        candidates = list(qs.exclude(embedding_vector=[])[:SEMANTIC_CANDIDATE_CAP])
        if not candidates:
            return [], []

        try:
            from apps.ai_engine.sales_kb import _cosine_similarity, _embed_query

            query_embedding = _embed_query(query, str(organization.id))
            if not query_embedding:
                return [], []

            scored = [
                (product, _cosine_similarity(query_embedding, product.embedding_vector))
                for product in candidates
                if product.embedding_vector
            ]
            scored = [item for item in scored if item[1] >= SEMANTIC_MIN_SIMILARITY]
            if not scored:
                return [], []

            scored.sort(key=lambda item: item[1], reverse=True)
            top_products = [product for product, _score in scored[:limit * 2]]

            if session:
                shown_ids = session.shown_products or []
                unseen = [p for p in top_products if str(p.id) not in shown_ids]
                top_products = unseen or top_products

            return CatalogService._split_products(top_products, limit=limit)
        except Exception as exc:
            logger.warning(f'Product semantic fallback failed: {exc}')
            return [], []

    @staticmethod
    def _build_search_terms(interpreted: dict) -> List[str]:
        raw_terms = []
        for key in ('product_name', 'category', 'color', 'brand'):
            value = (interpreted.get(key) or '').strip().lower()
            if value:
                raw_terms.extend(value.split())
        raw_terms.extend(interpreted.get('attributes') or [])
        raw_terms.extend(interpreted.get('search_terms') or [])

        seen = set()
        terms = []
        for term in raw_terms:
            clean = CatalogService._normalize_query(term)
            if not clean or clean in seen or len(clean) < 3:
                continue
            seen.add(clean)
            terms.append(clean)
        return terms[:8]
