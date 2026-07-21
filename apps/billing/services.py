"""
Servicios de suscripción: crear la prueba al registrarse y hacer backfill de
las organizaciones existentes. Idempotentes (nunca duplican una suscripción).
"""
from datetime import timedelta

from django.utils import timezone

from .models import Plan, Subscription

# El trial da acceso al plan destacado (features completas) para que el dueño
# sienta el producto entero. El tope de conversaciones del trial se aplica en la
# capa de enforcement (paso siguiente), no aquí.
TRIAL_PLAN_SLUG = 'crece'
TRIAL_CONVERSATION_CAP = 100  # tope duro durante la prueba (sin PAYG)
DEFAULT_TRIAL_DAYS = 7

# Mapeo del campo legacy Organization.plan (string) al slug del plan comercial.
LEGACY_PLAN_MAP = {
    'pilot': 'crece',
    'basic': 'emprende',
    'pro': 'crece',
    'enterprise': 'negocio',
}

_ACTIVE_STATUSES = ['trialing', 'active', 'past_due']


def _plan_by_slug(slug):
    return (
        Plan.objects.filter(slug=slug, is_active=True).first()
        or Plan.objects.filter(is_active=True).order_by('price_cop').first()
    )


def start_trial(organization, *, plan_slug=TRIAL_PLAN_SLUG):
    """Crea una prueba de 7 días para una org nueva, si no tiene suscripción activa."""
    existing = organization.subscriptions.filter(status__in=_ACTIVE_STATUSES).first()
    if existing:
        return existing
    plan = _plan_by_slug(plan_slug)
    if plan is None:
        return None  # catálogo de planes aún no sembrado
    now = timezone.now()
    trial_days = plan.trial_days or DEFAULT_TRIAL_DAYS
    return Subscription.objects.create(
        organization=organization,
        plan=plan,
        status='trialing',
        is_trial=True,
        trial_ends_at=now + timedelta(days=trial_days),
        period_start=now,
        period_end=now + timedelta(days=30),
    )


def record_conversation_usage(organization, conversation):
    """
    Cuenta una conversación del ciclo (una sola vez por hilo por periodo, dedup por
    metadata) e incrementa el excedente si se pasó del cupo (PAYG). Atómico bajo
    concurrencia. Idempotente. Nunca debe romper el chat — el caller lo envuelve,
    pero acá también evitamos efectos si no hay suscripción.
    """
    from django.db import transaction

    sub = organization.subscriptions.filter(status__in=_ACTIVE_STATUSES).order_by('-started_at').first()
    if sub is None:
        return None

    period_key = sub.period_start.isoformat() if sub.period_start else 'nocycle'
    meta = conversation.metadata or {}
    if meta.get('billing_metered_period') == period_key:
        return sub  # ya contada en este ciclo

    with transaction.atomic():
        locked = Subscription.objects.select_for_update().get(pk=sub.pk)
        locked.register_conversation(count=1)
        locked.save(update_fields=['conversations_used', 'overage_conversations', 'overage_amount_cop'])

    meta['billing_metered_period'] = period_key
    conversation.metadata = meta
    conversation.save(update_fields=['metadata'])
    return sub


def ensure_subscription(organization):
    """
    Backfill de una org existente: le asigna una suscripción 'active' (no trial)
    según su plan legacy. Idempotente.
    """
    existing = organization.subscriptions.filter(status__in=_ACTIVE_STATUSES).first()
    if existing:
        return existing
    slug = LEGACY_PLAN_MAP.get((organization.plan or '').lower(), 'emprende')
    plan = _plan_by_slug(slug)
    if plan is None:
        return None
    now = timezone.now()
    return Subscription.objects.create(
        organization=organization,
        plan=plan,
        status='active',
        is_trial=False,
        period_start=now,
        period_end=now + timedelta(days=30),
    )
