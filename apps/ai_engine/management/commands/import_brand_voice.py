"""
import_brand_voice — learn a brand's real chat voice from an inbox export.

Parses a Meta/Instagram DM export folder, compiles the brand's voice_card +
voice_examples (see apps.ai_engine.sales.voice_import) and optionally:

  --apply     merge them into the org's onboarding settings (ChannelConfig)
  --examples  seed approved conversation_example LearningCandidates so the
              ExampleBank retrieves real exchanges as few-shot

Dry-run by default: prints the compiled card and touches nothing.

Usage:
    python manage.py import_brand_voice --org aura --path C:/exports/inbox \
        --brand-name AURA --apply --examples
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.ai_engine.sales.voice_import import (
    apply_voice_to_settings,
    compile_voice_card,
    parse_instagram_inbox,
    seed_example_candidates,
    select_example_exchanges,
)


class Command(BaseCommand):
    help = "Compila la voz real de una marca desde un export de Instagram DM"

    def add_arguments(self, parser):
        parser.add_argument('--org', required=True, help='Slug o UUID de la organizacion')
        parser.add_argument('--path', required=True, help='Carpeta del export (una subcarpeta por conversacion)')
        parser.add_argument('--brand-name', default='', help='Nombre del participante que es la marca (autodetecta si se omite)')
        parser.add_argument('--apply', action='store_true', help='Escribir voice_card + voice_examples en los settings de onboarding')
        parser.add_argument('--examples', action='store_true', help='Crear LearningCandidates aprobados (conversation_example)')

    def handle(self, *args, **options):
        from apps.accounts.models import Organization

        organization = (
            Organization.objects.filter(slug=options['org']).first()
            or Organization.objects.filter(id=options['org']).first()
        )
        if organization is None:
            raise CommandError(f"Organizacion no encontrada: {options['org']}")

        conversations = parse_instagram_inbox(options['path'], brand_name=options['brand_name'] or None)
        if not conversations:
            raise CommandError('No se encontraron conversaciones parseables en esa ruta')

        compiled = compile_voice_card(conversations)
        voice_card = compiled['voice_card']
        voice_examples = compiled['voice_examples']
        exchanges = select_example_exchanges(conversations)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Voz compilada de {len(conversations)} conversaciones "
            f"({compiled['stats'].get('brand_messages', 0)} mensajes de la marca)"
        ))
        self._print('voice_card = ' + json.dumps(voice_card, ensure_ascii=False, indent=2))
        self._print(f'voice_examples ({len(voice_examples)}):')
        for example in voice_examples:
            self._print(f'  - {example}')
        self._print(f'exchanges para ExampleBank: {len(exchanges)}')

        if not voice_card:
            raise CommandError('Muy pocos mensajes de la marca para compilar una voz confiable')

        if options['apply']:
            if apply_voice_to_settings(organization, voice_card, voice_examples, source='imported'):
                self.stdout.write(self.style.SUCCESS('Settings de onboarding actualizados (voice_card + voice_examples)'))
            else:
                self.stdout.write(self.style.WARNING('voice_card marcada como manual — no se sobreescribio'))
        if options['examples']:
            created = seed_example_candidates(organization, exchanges)
            self.stdout.write(self.style.SUCCESS(f'LearningCandidates creados/actualizados: {created}'))
        if not options['apply'] and not options['examples']:
            self.stdout.write(self.style.WARNING('Dry-run: nada fue guardado (usa --apply / --examples)'))

    def _print(self, text: str) -> None:
        """Windows consoles (cp1252) choke on emojis; degrade instead of crash."""
        try:
            self.stdout.write(text)
        except UnicodeEncodeError:
            self.stdout.write(text.encode('ascii', 'backslashreplace').decode('ascii'))
