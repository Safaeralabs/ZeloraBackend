"""
Articles created by the learning-approval flow kept using pre-0004 purposes
('objection', 'brand_voice'), which the sales agent never retrieves.
Re-run the consolidation so approved learnings become visible to the agent.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    KBArticle = apps.get_model('knowledge_base', 'KBArticle')
    KBArticle.objects.filter(purpose__in=['objection', 'closing']).update(purpose='sales_scripts')
    KBArticle.objects.filter(purpose__in=['brand_voice', 'why_us', 'product_context']).update(purpose='business')


def backwards(apps, schema_editor):
    pass  # consolidation is intentionally one-way


class Migration(migrations.Migration):
    dependencies = [
        ('knowledge_base', '0004_consolidate_purposes'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
