from django.db import migrations


def rename_purposes_forward(apps, schema_editor):
    KBArticle = apps.get_model('knowledge_base', 'KBArticle')
    # product_context → product
    KBArticle.objects.filter(purpose='product_context').update(purpose='product')
    # brand_voice → why_us (brand voice content fits "por qué elegirnos")
    KBArticle.objects.filter(purpose='brand_voice').update(purpose='why_us')


def rename_purposes_backward(apps, schema_editor):
    KBArticle = apps.get_model('knowledge_base', 'KBArticle')
    KBArticle.objects.filter(purpose='product').update(purpose='product_context')
    KBArticle.objects.filter(purpose='why_us').update(purpose='brand_voice')


class Migration(migrations.Migration):

    dependencies = [
        ('knowledge_base', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(rename_purposes_forward, rename_purposes_backward),
    ]
