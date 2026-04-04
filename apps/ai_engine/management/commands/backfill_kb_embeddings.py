"""
Management command: generate missing embeddings for KBArticles.

Usage:
    python manage.py backfill_kb_embeddings
    python manage.py backfill_kb_embeddings --org <org_id>
    python manage.py backfill_kb_embeddings --batch-size 20 --dry-run
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate embedding_vector for KBArticles that have none.'

    def add_arguments(self, parser):
        parser.add_argument('--org', type=str, default=None, help='Limit to a specific organization UUID')
        parser.add_argument('--batch-size', type=int, default=50, help='Articles per batch (default: 50)')
        parser.add_argument('--dry-run', action='store_true', help='Show count only, do not write')

    def handle(self, *args, **options):
        import os
        import time

        from openai import OpenAI

        from apps.knowledge_base.models import KBArticle

        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            self.stderr.write(self.style.ERROR('OPENAI_API_KEY not set.'))
            return

        qs = KBArticle.objects.filter(is_active=True, status='published', embedding_vector=[])
        if options['org']:
            qs = qs.filter(organization__id=options['org'])

        total = qs.count()
        self.stdout.write(f'Articles without embedding: {total}')

        if options['dry_run'] or total == 0:
            return

        client = OpenAI(api_key=api_key)
        batch_size = options['batch_size']
        done = 0
        errors = 0

        for offset in range(0, total, batch_size):
            batch = list(qs[offset: offset + batch_size])
            texts = [f"{a.title}\n{a.content}"[:512] for a in batch]

            try:
                response = client.embeddings.create(model='text-embedding-3-small', input=texts)
                for article, emb_data in zip(batch, response.data):
                    article.embedding_vector = emb_data.embedding
                KBArticle.objects.bulk_update(batch, ['embedding_vector'])
                done += len(batch)
                self.stdout.write(f'  {done}/{total} embedded...')
                # Respect rate limits — 0.5s between batches
                time.sleep(0.5)
            except Exception as exc:
                errors += len(batch)
                self.stderr.write(self.style.WARNING(f'  Batch failed: {exc}'))

        style = self.style.SUCCESS if errors == 0 else self.style.WARNING
        self.stdout.write(style(f'Done. {done} embedded, {errors} errors.'))
