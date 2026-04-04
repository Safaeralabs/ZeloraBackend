from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Organization
from apps.analytics.historical_import import import_historical_chats


class Command(BaseCommand):
    help = 'Importa historicos de chat por organizacion, anonimiza PII y genera salidas para router, KB y evals.'

    def add_arguments(self, parser):
        parser.add_argument('--org-slug', required=True, help='Slug de la organizacion destino.')
        parser.add_argument('--chats', required=True, help='Ruta al archivo chats.jsonl.')
        parser.add_argument('--source-name', default='historical_import', help='Nombre corto de la fuente.')
        parser.add_argument(
            '--output-dir',
            default=str(Path(settings.BASE_DIR) / 'data' / 'historical_imports'),
            help='Directorio donde se escriben los artefactos generados.',
        )

    def handle(self, *args, **options):
        org_slug = options['org_slug'].strip()
        chats_path = Path(options['chats']).expanduser()
        output_dir = Path(options['output_dir']).expanduser()
        source_name = options['source_name'].strip() or 'historical_import'

        if not Organization.objects.filter(slug=org_slug, is_active=True).exists():
            raise CommandError(f'No existe una organizacion activa con slug "{org_slug}".')
        if not chats_path.exists():
            raise CommandError(f'No existe el archivo de chats: {chats_path}')

        result = import_historical_chats(
            org_slug=org_slug,
            chats_path=chats_path,
            output_dir=output_dir,
            source_name=source_name,
        )

        report = result['report']
        self.stdout.write(self.style.SUCCESS('Importacion historica completada'))
        self.stdout.write(f'output_dir: {result["target_dir"]}')
        self.stdout.write(f'sessions: {report["sessions"]}')
        self.stdout.write(f'router_examples: {report["router_examples"]}')
        self.stdout.write(f'eval_examples: {report["eval_examples"]}')
        self.stdout.write(f'top_topics: {report["topics"][:5]}')
