"""
Siembra/actualiza los planes comerciales de Zelora (idempotente).

    python manage.py seed_plans

Los datos viven en apps/billing/plan_data.py (fuente única, compartida con la
migración de datos 0003). Reejecutar tras cambiar precios/límites.
"""
from django.core.management.base import BaseCommand

from apps.billing.models import Plan
from apps.billing.plan_data import SEED_PLANS


class Command(BaseCommand):
    help = 'Crea o actualiza los planes comerciales (Emprende / Crece / Negocio).'

    def handle(self, *args, **options):
        for data in SEED_PLANS:
            slug = data['slug']
            defaults = {k: v for k, v in data.items() if k != 'slug'}
            plan, created = Plan.objects.update_or_create(slug=slug, defaults=defaults)
            verb = 'creado' if created else 'actualizado'
            self.stdout.write(f'  {verb}: {plan.name} - ${int(plan.price_cop):,} COP/mes - {plan.max_conversations_month} conv')
        self.stdout.write(self.style.SUCCESS(f'Listo. {len(SEED_PLANS)} planes sembrados.'))
