from datetime import timedelta

from django.db import migrations
from django.utils import timezone

LEGACY_PLAN_MAP = {
    'pilot': 'crece',
    'basic': 'emprende',
    'pro': 'crece',
    'enterprise': 'negocio',
}
ACTIVE = ['trialing', 'active', 'past_due']


def backfill(apps, schema_editor):
    Organization = apps.get_model('accounts', 'Organization')
    Plan = apps.get_model('billing', 'Plan')
    Subscription = apps.get_model('billing', 'Subscription')

    now = timezone.now()
    for org in Organization.objects.all():
        if Subscription.objects.filter(organization=org, status__in=ACTIVE).exists():
            continue
        slug = LEGACY_PLAN_MAP.get((org.plan or '').lower(), 'emprende')
        plan = (
            Plan.objects.filter(slug=slug, is_active=True).first()
            or Plan.objects.filter(is_active=True).order_by('price_cop').first()
        )
        if plan is None:
            continue
        Subscription.objects.create(
            organization=org,
            plan=plan,
            status='active',
            is_trial=False,
            period_start=now,
            period_end=now + timedelta(days=30),
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_seed_plans'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
