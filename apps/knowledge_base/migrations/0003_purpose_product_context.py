from django.db import migrations


def forward(apps, schema_editor):
    KBArticle = apps.get_model('knowledge_base', 'KBArticle')
    # 0002 renamed product_context → product; restore the canonical name
    KBArticle.objects.filter(purpose='product').update(purpose='product_context')


def backward(apps, schema_editor):
    KBArticle = apps.get_model('knowledge_base', 'KBArticle')
    KBArticle.objects.filter(purpose='product_context').update(purpose='product')


class Migration(migrations.Migration):

    dependencies = [
        ('knowledge_base', '0002_rename_purposes'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
