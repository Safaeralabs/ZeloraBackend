"""
L10: Management command to export approved learning candidates as JSONL for fine-tuning.

Exports conversation_example candidates in OpenAI fine-tuning format.

Usage:
  python manage.py export_training_dataset --org=<slug>
  python manage.py export_training_dataset --org=<slug> --kind=conversation_example --min-confidence=0.85
  python manage.py export_training_dataset --org=<slug> --output=dataset.jsonl
"""
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from apps.analytics.models import LearningCandidate
from apps.accounts.models import Organization


class Command(BaseCommand):
    help = 'Export approved learning candidates as JSONL for fine-tuning'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            required=True,
            help='Organization slug or UUID',
        )
        parser.add_argument(
            '--kind',
            type=str,
            default='conversation_example',
            help='LearningCandidate kind to export (default: conversation_example)',
        )
        parser.add_argument(
            '--min-confidence',
            type=float,
            default=0.80,
            help='Only include candidates with confidence >= this value',
        )
        parser.add_argument(
            '--output',
            type=str,
            default=None,
            help='Output file path (default: dataset-{org_slug}-{kind}.jsonl)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be exported without writing',
        )

    def handle(self, *args, **options):
        org_param = options['org']
        kind = options['kind']
        min_confidence = options['min_confidence']
        output = options['output']
        dry_run = options['dry_run']

        # Find organization
        try:
            org = Organization.objects.get(slug=org_param)
        except Organization.DoesNotExist:
            try:
                org = Organization.objects.get(id=org_param)
            except Organization.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'Organization not found: {org_param}'))
                return

        # Query approved candidates
        candidates = (
            LearningCandidate.objects
            .filter(
                organization=org,
                kind=kind,
                status='approved',
                confidence__gte=min_confidence,
            )
            .order_by('-confidence')
        )

        count = candidates.count()
        if count == 0:
            self.stdout.write(self.style.WARNING(f'No candidates found for export'))
            return

        self.stdout.write(f'Exporting {count} {kind} candidates with confidence >= {min_confidence}')

        if dry_run:
            for cand in candidates[:5]:
                self.stdout.write(f'  Sample: {cand.title} (confidence={cand.confidence})')
            return

        # Prepare output file
        if not output:
            output = f'dataset-{org.slug}-{kind}.jsonl'
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Export as JSONL
        exported = 0
        with open(output_path, 'w', encoding='utf-8') as f:
            for cand in candidates:
                # Format: {messages: [{role: user, content: ...}, {role: assistant, content: ...}]}
                if kind == 'conversation_example':
                    # User message → Agent reply
                    record = {
                        'messages': [
                            {'role': 'user', 'content': cand.source_question},
                            {'role': 'assistant', 'content': cand.proposed_answer},
                        ]
                    }
                else:
                    # Generic FAQ format: question → answer
                    record = {
                        'messages': [
                            {'role': 'user', 'content': cand.source_question or cand.title},
                            {'role': 'assistant', 'content': cand.proposed_answer},
                        ]
                    }

                # Add metadata for tracking
                record['_metadata'] = {
                    'candidate_id': str(cand.id),
                    'kind': cand.kind,
                    'confidence': cand.confidence,
                    'evidence_count': cand.evidence_count,
                    'channel': cand.metadata.get('channel', 'web') if cand.metadata else 'web',
                    'stage': cand.metadata.get('stage', 'discovering') if cand.metadata else 'discovering',
                }

                f.write(json.dumps(record, ensure_ascii=False) + '\n')
                exported += 1

        self.stdout.write(self.style.SUCCESS(f'Exported {exported} records to {output_path}'))
        self.stdout.write(f'  Format: OpenAI fine-tuning JSONL')
        self.stdout.write(f'  Usage: openai api fine_tunes.create -t {output_path}')
