"""
Asigna una suscripción a las organizaciones que aún no tienen una (idempotente).

    python manage.py backfill_subscriptions

Usa el plan legacy Organization.plan para elegir el plan comercial y la marca
como 'active'. Reejecutable sin duplicar.
"""
from django.core.management.base import BaseCommand

from apps.accounts.models import Organization
from apps.billing.services import ensure_subscription


class Command(BaseCommand):
    help = 'Crea suscripciones para las organizaciones existentes que no tengan una.'

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        for org in Organization.objects.all():
            before = org.subscriptions.filter(status__in=['trialing', 'active', 'past_due']).exists()
            sub = ensure_subscription(org)
            if before or sub is None:
                skipped += 1
            else:
                created += 1
                self.stdout.write(f'  {org.name} -> {sub.plan.name}')
        self.stdout.write(self.style.SUCCESS(f'Listo. {created} creadas, {skipped} sin cambios.'))
