"""
Management command: generate missing embeddings for Products.

Usage:
    python manage.py backfill_product_embeddings
    python manage.py backfill_product_embeddings --org <org_id>
    python manage.py backfill_product_embeddings --batch-size 20 --dry-run
"""
from django.core.management.base import BaseCommand


def _build_product_embedding_text(product) -> str:
    """Construct rich text for product embedding (title + attrs + description)."""
    parts = [product.title]

    # Add structured fields in priority order
    for field, val in [
        ('brand', product.brand),
        ('category', product.category),
        ('subcategory', product.subcategory),
        ('style', product.style),
        ('formality', product.formality),
        ('color', product.color),
        ('material', product.material),
        ('fit', product.fit),
        ('target_audience', product.target_audience),
    ]:
        if val:
            parts.append(val)

    # Add occasion list
    if product.occasion:
        parts.append(', '.join(product.occasion))

    # Add description snippet (first 300 chars)
    if product.description:
        parts.append(product.description[:300])

    # Join and truncate to 512 chars (matching KB pattern)
    text = '\n'.join(parts)[:512]
    return text


class Command(BaseCommand):
    help = 'Generate embedding_vector for Products that have none.'

    def add_arguments(self, parser):
        parser.add_argument('--org', type=str, default=None, help='Limit to a specific organization UUID')
        parser.add_argument('--batch-size', type=int, default=50, help='Products per batch (default: 50)')
        parser.add_argument('--dry-run', action='store_true', help='Show count only, do not write')

    def handle(self, *args, **options):
        import os
        import time

        from openai import OpenAI

        from apps.ecommerce.models import Product

        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            self.stderr.write(self.style.ERROR('OPENAI_API_KEY not set.'))
            return

        qs = Product.objects.filter(is_active=True, status='active', embedding_vector=[])
        if options['org']:
            qs = qs.filter(organization__id=options['org'])

        total = qs.count()
        self.stdout.write(f'Products without embedding: {total}')

        if options['dry_run'] or total == 0:
            return

        client = OpenAI(api_key=api_key)
        batch_size = options['batch_size']
        done = 0
        errors = 0

        for offset in range(0, total, batch_size):
            batch = list(qs[offset: offset + batch_size])
            texts = [_build_product_embedding_text(p) for p in batch]

            try:
                response = client.embeddings.create(model='text-embedding-3-small', input=texts)
                for product, emb_data in zip(batch, response.data):
                    product.embedding_vector = emb_data.embedding
                Product.objects.bulk_update(batch, ['embedding_vector'])
                done += len(batch)
                self.stdout.write(f'  {done}/{total} embedded...')
                # Respect rate limits — 0.5s between batches
                time.sleep(0.5)
            except Exception as exc:
                errors += len(batch)
                self.stderr.write(self.style.WARNING(f'  Batch failed: {exc}'))

        style = self.style.SUCCESS if errors == 0 else self.style.WARNING
        self.stdout.write(style(f'Done. {done} embedded, {errors} errors.'))
