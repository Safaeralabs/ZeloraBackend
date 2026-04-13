"""
KB Service — Knowledge Base article retrieval.
"""
import logging
from typing import List, Optional

from apps.knowledge_base.models import KBArticle

logger = logging.getLogger(__name__)


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
        # Filter by org, status, purpose
        qs = KBArticle.objects.filter(
            organization=organization,
            status='published',
            purpose__in=purposes,
        )

        # Sort: search match first (simple keyword), then by visits
        if query:
            from django.db.models import Q
            words = query.lower().split()[:3]
            q_filter = Q()
            for word in words:
                q_filter |= Q(title__icontains=word) | Q(content__icontains=word)
            qs = qs.filter(q_filter)

        articles = list(qs.order_by('-visits')[:max_articles])

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
