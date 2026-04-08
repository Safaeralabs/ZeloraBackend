from django.db import migrations


def forward(apps, schema_editor):
    KBArticle = apps.get_model('knowledge_base', 'KBArticle')
    # Merge product_context + why_us → business
    KBArticle.objects.filter(purpose__in=['product_context', 'why_us']).update(purpose='business')
    # Merge objection + closing → sales_scripts
    KBArticle.objects.filter(purpose__in=['objection', 'closing']).update(purpose='sales_scripts')


def backward(apps, schema_editor):
    # Can't recover the original split without extra metadata — map back to most likely value
    KBArticle = apps.get_model('knowledge_base', 'KBArticle')
    KBArticle.objects.filter(purpose='business').update(purpose='product_context')
    KBArticle.objects.filter(purpose='sales_scripts').update(purpose='objection')


class Migration(migrations.Migration):

    dependencies = [
        ('knowledge_base', '0003_purpose_product_context'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
