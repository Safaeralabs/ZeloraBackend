"""
Tareas Celery de billing.

`reset_billing_cycles_task`: rueda el ciclo de las suscripciones cuyo period_end
ya pasó — reinicia contadores de conversaciones y excedente, y fija el nuevo
periodo. Corre a diario para respetar los cortes por-org.
"""
from datetime import timedelta

from celery import shared_task
from django.utils import timezone


@shared_task(name='billing.reset_billing_cycles')
def reset_billing_cycles_task():
    from apps.billing.models import Subscription

    now = timezone.now()
    rolled = 0
    qs = Subscription.objects.filter(status__in=['active', 'past_due'], period_end__lte=now)
    for sub in qs:
        # TODO(pasarela): antes de reiniciar, cobrar sub.overage_amount_cop (Wompi/Bold).
        new_start = sub.period_end or now
        new_end = new_start + timedelta(days=30)
        if new_end <= now:  # periodo muy atrasado → alinear al presente
            new_start = now
            new_end = now + timedelta(days=30)
        sub.reset_cycle(period_start=new_start, period_end=new_end)
        sub.save(update_fields=[
            'conversations_used', 'overage_conversations', 'overage_amount_cop',
            'period_start', 'period_end',
        ])
        rolled += 1
    return {'rolled': rolled}
