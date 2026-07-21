from django.db import migrations


def seed_plans(apps, schema_editor):
    Plan = apps.get_model('billing', 'Plan')
    from apps.billing.plan_data import SEED_PLANS
    for data in SEED_PLANS:
        slug = data['slug']
        defaults = {k: v for k, v in data.items() if k != 'slug'}
        Plan.objects.update_or_create(slug=slug, defaults=defaults)


def noop(apps, schema_editor):
    # No borramos planes al revertir (evita perder suscripciones ligadas).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_plan_annual_price_cop_plan_max_products_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_plans, noop),
    ]
