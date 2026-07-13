"""
Example Bank — few-shot retrieval of the brand's best real replies.

Approved LearningCandidates of kind `conversation_example` / `winning_reply`
(extracted by the learning engine from human-resolved conversations, with
outcome-based confidence) are retrieved each turn and injected into the
generator prompt so the agent imitates how the brand actually sells.

They intentionally stay as LearningCandidates instead of being flattened
into FAQ KBArticles at approval time: the stage/outcome metadata drives
retrieval here and would be lost as plain articles.

Ranking order for a query:
  1. Semantic similarity against the embedding stored at extraction time
     (when real AI is enabled).
  2. Fallback: same-stage examples first, then highest confidence.
"""
import logging
from typing import List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

#: Minimum cosine similarity for a semantic match to count.
SEMANTIC_MIN_SIMILARITY = 0.20

EXAMPLE_KINDS = ('conversation_example', 'winning_reply')


class ExampleBank:
    """
    Fetches approved conversation examples for an organization,
    formatted as few-shot lines for the generator prompt.
    """

    @staticmethod
    def fetch(
        organization,
        query: str = '',
        stage: str = '',
        max_examples: int = 2,
    ) -> str:
        """
        Fetch the best matching examples for the current turn.

        Args:
            organization: Organization to filter by
            query: Current user message (accumulated catalog query)
            stage: Current session stage (discovering/considering/...)
            max_examples: Max examples to include

        Returns:
            Formatted 'Cliente: .../Marca: ...' pairs, or '' when the org
            has no approved examples yet.
        """
        from apps.analytics.models import LearningCandidate

        candidates = list(
            LearningCandidate.objects.filter(
                organization=organization,
                status='approved',
                kind__in=EXAMPLE_KINDS,
            ).order_by('-confidence', '-updated_at')[:40]
        )
        if not candidates:
            return ''

        ranked = None
        if query:
            ranked = ExampleBank._semantic_rank(candidates, query, organization, max_examples)
        if ranked is None:
            ranked = ExampleBank._stage_rank(candidates, stage, max_examples)
        if not ranked:
            return ''

        lines: List[str] = []
        for candidate in ranked:
            question = ' '.join((candidate.source_question or '').split())[:220]
            answer = ' '.join((candidate.proposed_answer or '').split())[:320]
            if not question or not answer:
                continue
            lines.append(f'Cliente: "{question}"')
            lines.append(f'Marca: "{answer}"')
            lines.append('')

        return '\n'.join(lines).strip()

    @staticmethod
    def _semantic_rank(
        candidates: List,
        query: str,
        organization,
        max_examples: int,
    ) -> Optional[List]:
        """
        Rank by cosine similarity between the query and the embedding stored
        in candidate metadata. Returns None when semantic search is
        unavailable so the caller falls back to stage/confidence ranking.
        """
        if not settings.OPENAI_API_KEY or not getattr(settings, 'ENABLE_REAL_AI', False):
            return None

        embedded = [
            candidate for candidate in candidates
            if (candidate.metadata or {}).get('embedding')
        ]
        if not embedded:
            return None

        try:
            from apps.ai_engine.sales_kb import _cosine_similarity, _embed_query

            query_embedding = _embed_query(query, str(organization.id))
            if not query_embedding:
                return None

            scored = [
                (candidate, _cosine_similarity(query_embedding, candidate.metadata['embedding']))
                for candidate in embedded
            ]
            scored = [item for item in scored if item[1] >= SEMANTIC_MIN_SIMILARITY]
            if not scored:
                return None

            scored.sort(key=lambda item: item[1], reverse=True)
            return [candidate for candidate, _score in scored[:max_examples]]
        except Exception as exc:
            logger.warning('Example bank semantic ranking failed: %s', exc)
            return None

    @staticmethod
    def _stage_rank(candidates: List, stage: str, max_examples: int) -> List:
        """Same-stage examples first; candidates arrive pre-sorted by confidence."""
        if not stage:
            return candidates[:max_examples]
        same_stage = [
            candidate for candidate in candidates
            if (candidate.metadata or {}).get('stage') == stage
        ]
        rest = [candidate for candidate in candidates if candidate not in same_stage]
        return (same_stage + rest)[:max_examples]
