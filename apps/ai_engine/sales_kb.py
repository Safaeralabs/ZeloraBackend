"""
Shared semantic-search helpers for the Knowledge Base.

Single source for embedding generation and cosine similarity so the sales
agent retrieval (KBService), the learning engine, and the conflict detection
in apps.analytics.learning all speak the same vector language.

Note: `_embed_query` and `_cosine_similarity` are part of an existing import
contract (apps.analytics.learning imports these exact names).
"""
from __future__ import annotations


def _embed_query(text: str, organization_id: str = '') -> list[float]:
    """Embed a query/document with the same model used by the learning engine."""
    from apps.ai_engine.tasks import _generate_embedding

    return _generate_embedding(text, organization_id)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    from apps.ai_engine.tasks import _cosine_similarity as cosine

    return cosine(a, b)


# Public aliases
embed_text = _embed_query
cosine_similarity = _cosine_similarity
