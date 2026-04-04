from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Organization
from apps.analytics.kb_seed_import import import_kb_seed_for_organization


class Command(BaseCommand):
    help = 'Convierte un kb_seed.json en articulos reales de Knowledge Base para una organizacion.'

    def add_arguments(self, parser):
        parser.add_argument('--org-slug', required=True, help='Slug de la organizacion destino.')
        parser.add_argument('--seed-path', required=True, help='Ruta al archivo kb_seed.json.')
        parser.add_argument(
            '--author-email',
            default='',
            help='Email opcional del autor a asociar a los articulos creados.',
        )

    def handle(self, *args, **options):
        org_slug = options['org_slug'].strip()
        seed_path = Path(options['seed_path']).expanduser()
        author_email = options['author_email'].strip()

        if not seed_path.exists():
            raise CommandError(f'No existe el archivo de seeds: {seed_path}')

        try:
            organization = Organization.objects.get(slug=org_slug, is_active=True)
        except Organization.DoesNotExist as exc:
            raise CommandError(f'No existe una organizacion activa con slug "{org_slug}".') from exc

        result = import_kb_seed_for_organization(
            organization=organization,
            seed_path=seed_path,
            author_email=author_email,
        )

        self.stdout.write(self.style.SUCCESS('KB seed importado'))
        self.stdout.write(f'organization: {organization.slug}')
        self.stdout.write(f'created: {result["created"]}')
        self.stdout.write(f'updated: {result["updated"]}')
