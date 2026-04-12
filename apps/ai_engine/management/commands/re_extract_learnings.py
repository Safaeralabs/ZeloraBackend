"""
L9: Management command to re-extract learnings from historical conversations.

Allows benefiting from improved extraction prompts without waiting for new conversations.

Usage:
  python manage.py re_extract_learnings --since=2026-01-01
  python manage.py re_extract_learnings --only-kind=faq --min-confidence=0.75
  python manage.py re_extract_learnings --force  # Reset learning_processed flag
"""
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from apps.conversations.models import Conversation
from apps.ai_engine.tasks import run_learning_engine


class Command(BaseCommand):
    help = 'Re-extract learnings from historical conversations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--since',
            type=str,
            default=None,
            help='Re-extract from conversations since this date (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--until',
            type=str,
            default=None,
            help='Re-extract until this date (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--only-kind',
            type=str,
            default=None,
            help='Limit to specific LearningCandidate kind (faq, conversation_example, estilo_comunicacion)',
        )
        parser.add_argument(
            '--min-confidence',
            type=float,
            default=0.0,
            help='Only re-extract if existing confidence < this threshold',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Reset learning_processed flag to re-process',
        )
        parser.add_argument(
            '--org',
            type=str,
            default=None,
            help='Limit to specific organization UUID',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Process this many conversations per batch',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be extracted without processing',
        )

    def handle(self, *args, **options):
        since = options.get('since')
        until = options.get('until')
        only_kind = options.get('only_kind')
        min_confidence = options.get('min_confidence', 0.0)
        force = options.get('force', False)
        org_id = options.get('org')
        batch_size = options.get('batch_size', 10)
        dry_run = options.get('dry_run', False)

        # Build conversation filter
        conv_filter = Q(estado__in=['resuelto', 'escalado'])
        if org_id:
            conv_filter &= Q(organization_id=org_id)
        if since:
            try:
                since_date = datetime.strptime(since, '%Y-%m-%d')
                conv_filter &= Q(created_at__gte=timezone.make_aware(since_date))
            except ValueError:
                self.stderr.write(self.style.ERROR('Invalid date format for --since'))
                return
        if until:
            try:
                until_date = datetime.strptime(until, '%Y-%m-%d')
                conv_filter &= Q(created_at__lte=timezone.make_aware(until_date))
            except ValueError:
                self.stderr.write(self.style.ERROR('Invalid date format for --until'))
                return

        # Filter conversations needing re-extraction
        if not force:
            conv_filter &= Q(metadata__learning_processed=False)

        conversations = Conversation.objects.filter(conv_filter).order_by('-created_at')
        total = conversations.count()
        self.stdout.write(f'Found {total} conversations to re-extract from')

        processed = 0
        failed = 0
        for conv in conversations[:1000]:  # Safety limit
            if dry_run:
                self.stdout.write(f'  Would re-extract: {conv.id} ({conv.created_at})')
                processed += 1
            else:
                try:
                    result = run_learning_engine(str(conv.id))
                    if result.get('status') == 'ok':
                        self.stdout.write(f'  ✓ {conv.id}: {result}')
                        processed += 1
                    else:
                        self.stdout.write(f'  ⊘ {conv.id}: {result.get("reason")}')
                except Exception as exc:
                    self.stdout.write(f'  ✗ {conv.id}: {str(exc)}')
                    failed += 1

        self.stdout.write(self.style.SUCCESS(f'Re-extraction complete: {processed} processed, {failed} failed'))
