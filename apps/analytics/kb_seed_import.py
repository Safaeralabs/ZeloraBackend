from __future__ import annotations

import json
from pathlib import Path

from django.contrib.auth import get_user_model

from apps.accounts.models import Organization
from apps.knowledge_base.models import KBArticle


User = get_user_model()


def build_article_content(seed_item: dict) -> str:
    lines: list[str] = []
    topic = str(seed_item.get('topic', '')).strip()
    route_hint = str(seed_item.get('route_hint', '')).strip()
    sample_questions = [str(item).strip() for item in seed_item.get('sample_questions', []) if str(item).strip()]
    sample_answers = [str(item).strip() for item in seed_item.get('sample_answers', []) if str(item).strip()]

    if topic:
        lines.append(f'Tema: {topic}')
    if route_hint:
        lines.append(f'Ruta sugerida: {route_hint}')

    if sample_questions:
        lines.append('')
        lines.append('Preguntas reales detectadas:')
        for question in sample_questions[:10]:
            lines.append(f'- {question}')

    if sample_answers:
        lines.append('')
        lines.append('Respuestas historicas de referencia:')
        for answer in sample_answers[:10]:
            lines.append(f'- {answer}')

    seed_note = str(seed_item.get('article_seed', '')).strip()
    if seed_note:
        lines.append('')
        lines.append(seed_note)

    return '\n'.join(lines).strip()


def import_kb_seed_for_organization(*, organization: Organization, seed_path: Path, author_email: str = '') -> dict[str, int]:
    author = None
    if author_email:
        author = User.objects.filter(email=author_email, organization=organization).first()

    seed_items = json.loads(seed_path.read_text(encoding='utf-8'))
    created = 0
    updated = 0

    for item in seed_items:
        title = str(item.get('title', '')).strip()
        if not title:
            continue
        category = str(item.get('topic', '')).strip() or str(item.get('route_hint', '')).strip() or 'general'
        content = build_article_content(item)
        tags = [
            str(item.get('topic', '')).strip(),
            str(item.get('route_hint', '')).strip(),
            'historical_import',
        ]
        tags = [tag for tag in tags if tag]

        article, article_created = KBArticle.objects.get_or_create(
            organization=organization,
            title=title,
            defaults={
                'author': author,
                'content': content,
                'category': category,
                'tags': tags,
                'status': 'published',
                'is_active': True,
            },
        )

        if article_created:
            created += 1
            continue

        article.author = article.author or author
        article.content = content
        article.category = category
        article.tags = sorted(set([*(article.tags or []), *tags]))
        article.status = 'published'
        article.is_active = True
        article.save(update_fields=['author', 'content', 'category', 'tags', 'status', 'is_active', 'updated_at'])
        updated += 1

    return {'created': created, 'updated': updated}
