"""
KB Service — Knowledge Base article retrieval.

Retrieval order for query-based lookups:
  1. Semantic search over stored embedding vectors (when real AI is enabled
     and articles have embeddings) — "envios a Cartagena" finds
     "Politica de entregas" even without shared keywords.
  2. Keyword fallback (title/content icontains, ranked by visits).
"""
import logging
from typing import List, Optional

from django.conf import settings

from apps.knowledge_base.models import KBArticle

logger = logging.getLogger(__name__)

#: Minimum cosine similarity for a semantic match to count.
SEMANTIC_MIN_SIMILARITY = 0.25


class KBService:
    """
    Fetches KB articles by purpose.
    Filters by organization, status, and purpose.
    """

    PURPOSES = ['faq', 'business', 'sales_scripts', 'policy']

    @staticmethod
    def fetch(
        purposes: List[str],
        organization,
        query: Optional[str] = None,
        max_articles: int = 3,
    ) -> str:
        """
        Fetch KB articles matching purposes and optionally search query.

        Args:
            purposes: List of purposes (faq, business, sales_scripts, policy)
            organization: Organization to filter by
            query: Optional search keywords
            max_articles: Max articles to include

        Returns:
            Formatted string of KB article content (max 600 chars each)
        """
        candidates = list(
            KBArticle.objects.filter(
                organization=organization,
                status='published',
                purpose__in=purposes,
            ).order_by('-visits')[:60]
        )
        if not candidates:
            return ''

        if query:
            articles = KBService._semantic_rank(candidates, query, organization, max_articles)
            if articles is None:
                articles = KBService._keyword_rank(candidates, query, max_articles)
        else:
            articles = candidates[:max_articles]

        if not articles:
            return ''

        # Format output
        lines = []
        for article in articles:
            lines.append(f'**{article.title}**')
            content_preview = article.content[:400] if article.content else ''
            lines.append(content_preview)
            lines.append('')

        return '\n'.join(lines)

    @staticmethod
    def _semantic_rank(
        candidates: List[KBArticle],
        query: str,
        organization,
        max_articles: int,
    ) -> Optional[List[KBArticle]]:
        """
        Rank candidates by cosine similarity against the query embedding.
        Returns None when semantic search is unavailable or produced nothing
        useful, so the caller can fall back to keyword matching.
        """
        if not settings.OPENAI_API_KEY or not getattr(settings, 'ENABLE_REAL_AI', False):
            return None

        embedded = [article for article in candidates if article.embedding_vector]
        if not embedded:
            return None

        try:
            from apps.ai_engine.sales_kb import _cosine_similarity, _embed_query

            query_embedding = _embed_query(query, str(organization.id))
            if not query_embedding:
                return None

            scored = [
                (article, _cosine_similarity(query_embedding, article.embedding_vector))
                for article in embedded
            ]
            scored = [item for item in scored if item[1] >= SEMANTIC_MIN_SIMILARITY]
            if not scored:
                return None

            scored.sort(key=lambda item: item[1], reverse=True)
            return [article for article, _score in scored[:max_articles]]
        except Exception as exc:
            logger.warning('KB semantic ranking failed: %s', exc)
            return None

    @staticmethod
    def _keyword_rank(candidates: List[KBArticle], query: str, max_articles: int) -> List[KBArticle]:
        words = [word for word in query.lower().split()[:3] if word]
        if not words:
            return candidates[:max_articles]
        matched = [
            article for article in candidates
            if any(
                word in (article.title or '').lower() or word in (article.content or '').lower()
                for word in words
            )
        ]
        # candidates arrive pre-sorted by visits, so order is preserved.
        return matched[:max_articles]

    @staticmethod
    def fetch_policy(organization) -> str:
        """
        Fetch all policy articles (shipping, returns, payments, warranties).

        Args:
            organization: Organization to filter by

        Returns:
            Formatted policy KB content
        """
        return KBService.fetch(
            purposes=['policy'],
            organization=organization,
            max_articles=3,
        )

    @staticmethod
    def fetch_faq(organization, query: Optional[str] = None) -> str:
        """
        Fetch FAQ articles.

        Args:
            organization: Organization to filter by
            query: Optional search keywords

        Returns:
            Formatted FAQ KB content
        """
        return KBService.fetch(
            purposes=['faq'],
            organization=organization,
            query=query,
            max_articles=2,
        )

    @staticmethod
    def fetch_sales_scripts(organization, situation: Optional[str] = None) -> str:
        """
        Fetch sales script articles (for objection handling, closing, etc.).

        Args:
            organization: Organization to filter by
            situation: Optional customer situation for targeted scripts

        Returns:
            Formatted sales script KB content
        """
        return KBService.fetch(
            purposes=['sales_scripts'],
            organization=organization,
            query=situation,
            max_articles=2,
        )

    @staticmethod
    def fetch_business(organization) -> str:
        """
        Fetch business/brand articles (value prop, differentiators, testimonials).

        Args:
            organization: Organization to filter by

        Returns:
            Formatted business KB content
        """
        return KBService.fetch(
            purposes=['business'],
            organization=organization,
            max_articles=2,
        )
