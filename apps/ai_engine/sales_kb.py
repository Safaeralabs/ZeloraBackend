"""
Sales Agent KB retrieval: semantic search with cosine similarity and fallback keyword matching.

All inter-app imports (knowledge_base models) are deferred inside function bodies.
"""
from __future__ import annotations

from typing import Any

import structlog

from .sales_models import STAGE_CHECKOUT_BLOCKED, STAGE_CLOSED_LOST, STAGE_CLOSED_WON, STAGE_CONSIDERING, STAGE_DISCOVERING, STAGE_FOLLOW_UP_NEEDED, STAGE_HUMAN_HANDOFF, STAGE_INTENT_TO_BUY, STAGE_LOST, BusinessContext, SalesContext

logger = structlog.get_logger(__name__)


_STAGE_PURPOSE_MAP: dict[str, list[str]] = {
    STAGE_DISCOVERING:       ['faq', 'business'],
    STAGE_CONSIDERING:       ['business', 'faq'],
    STAGE_INTENT_TO_BUY:     ['sales_scripts', 'policy'],
    STAGE_FOLLOW_UP_NEEDED:  ['sales_scripts'],
    STAGE_LOST:              ['sales_scripts'],
    STAGE_CLOSED_LOST:       ['sales_scripts'],
    STAGE_CLOSED_WON:        ['sales_scripts'],
    STAGE_CHECKOUT_BLOCKED:  ['sales_scripts', 'policy'],
    STAGE_HUMAN_HANDOFF:     ['policy'],
}
_BASELINE_PURPOSES = ['faq', 'business']


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_query(text: str) -> list[float] | None:
    """Get OpenAI embedding for query text."""
    try:
        import os
        from openai import OpenAI

        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            return None
        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(model='text-embedding-3-small', input=text[:512])
        return response.data[0].embedding
    except Exception:
        return None


def _build_knowledge_snapshot_block(knowledge_snapshot: list[dict[str, Any]]) -> str:
    """Format knowledge snapshot for prompt injection."""
    if not knowledge_snapshot:
        return 'Sin knowledge base publicada.'

    lines: list[str] = []
    for item in knowledge_snapshot:
        item_type = item.get('type', 'item')
        category = item.get('category') or 'general'
        content = item.get('content', '')
        lines.append(f'- [{item_type}] {item.get("title", "sin titulo")} | {category} | {content}')
    return '\n'.join(lines)


def _lookup_relevant_knowledge(
    conversation,
    business: BusinessContext,
    products: list[dict[str, Any]],
    sales_ctx: SalesContext | None = None,
    stage: str = STAGE_DISCOVERING,
) -> str:
    """Fetch and rank KB articles by semantic similarity and stage-aware purpose."""
    try:
        from apps.knowledge_base.models import KBArticle, KBDocument

        org = getattr(conversation, 'organization', None)
        if org is None:
            return 'Sin conocimiento adicional.'

        base_qs = KBArticle.objects.filter(organization=org, is_active=True, status='published')

        # --- Stage-aware purpose retrieval ---
        priority_purposes = _STAGE_PURPOSE_MAP.get(stage, _BASELINE_PURPOSES)
        all_purposes = list(set(priority_purposes + _BASELINE_PURPOSES))

        purpose_articles: list[Any] = []
        seen_ids: set = set()

        # Fetch up to 2 articles per purpose, in priority order
        for purpose in all_purposes:
            if len(purpose_articles) >= 4:
                break
            qs = base_qs.filter(purpose=purpose).only('id', 'title', 'content', 'purpose', 'embedding_vector').order_by('-updated_at')[:4]
            for art in qs:
                if art.id not in seen_ids:
                    purpose_articles.append(art)
                    seen_ids.add(art.id)
                    if len(purpose_articles) >= 4:
                        break

        # --- Semantic re-ranking via cosine similarity ---
        # Build query text from last customer message + products
        query_parts: list[str] = []
        try:
            last_user_msg = conversation.messages.filter(role='user').order_by('-timestamp').first()
            if last_user_msg and last_user_msg.content:
                query_parts.append(last_user_msg.content[:120])
        except Exception:
            pass
        for product in products[:2]:
            t = product.get('title', '')
            if t:
                query_parts.append(t[:60])
        if business.what_you_sell:
            query_parts.append(business.what_you_sell[:60])
        query_text = ' '.join(query_parts).strip() or 'productos y servicios'

        # Broaden pool with general articles if purpose-filtered set is small
        if len(purpose_articles) < 3:
            extra = list(
                base_qs.exclude(id__in=seen_ids)
                .only('id', 'title', 'content', 'purpose', 'embedding_vector')
                .order_by('-updated_at')[:20]
            )
            purpose_articles.extend(extra)

        query_vec = _embed_query(query_text)
        articles_with_emb = [a for a in purpose_articles if a.embedding_vector]

        if query_vec and articles_with_emb:
            scored = [
                (a, _cosine_similarity(query_vec, a.embedding_vector))
                for a in articles_with_emb
            ]
            scored.sort(key=lambda t: t[1], reverse=True)
            top_articles = [a for a, score in scored[:4] if score > 0.20]
            # Add purpose-priority articles that didn't make cosine cut (low text but on-purpose)
            for art in purpose_articles[:2]:
                if art not in top_articles:
                    top_articles.insert(0, art)
            top_articles = top_articles[:4]
        else:
            # Fallback: keyword icontains on general pool
            terms = [w for w in query_text.lower().split() if len(w) > 3][:6]
            if terms:
                from django.db.models import Q
                kb_filter = Q()
                for term in terms:
                    kb_filter |= Q(title__icontains=term) | Q(content__icontains=term)
                top_articles = list(base_qs.filter(kb_filter).order_by('-updated_at')[:4])
            else:
                top_articles = purpose_articles[:3]

        snippets: list[str] = []
        for article in top_articles:
            purpose_label = f'[{article.purpose}] ' if getattr(article, 'purpose', '') else ''
            snippets.append(f'- {purpose_label}{article.title}: {" ".join(article.content.split())[:220]}')

        # --- Documents (keyword match) ---
        document_queryset = KBDocument.objects.filter(organization=org, is_active=True, processing_status='ready')
        terms = [w for w in query_text.lower().split() if len(w) > 3][:6]
        if terms:
            from django.db.models import Q
            doc_filter = Q()
            for term in terms:
                doc_filter |= Q(filename__icontains=term) | Q(extracted_text__icontains=term)
            documents = document_queryset.filter(doc_filter).order_by('-updated_at')[:2]
        else:
            documents = document_queryset.order_by('-updated_at')[:2]

        for document in documents:
            excerpt = ' '.join((document.extracted_text or '').split())[:220]
            if excerpt:
                snippets.append(f'- [doc] {document.filename}: {excerpt}')

        if snippets:
            return '\n'.join(snippets)

        if sales_ctx and sales_ctx.knowledge_snapshot:
            return _build_knowledge_snapshot_block(sales_ctx.knowledge_snapshot[:4])
        return 'Sin conocimiento adicional.'
    except Exception:
        if sales_ctx and sales_ctx.knowledge_snapshot:
            return _build_knowledge_snapshot_block(sales_ctx.knowledge_snapshot[:4])
        return 'Sin conocimiento adicional.'
