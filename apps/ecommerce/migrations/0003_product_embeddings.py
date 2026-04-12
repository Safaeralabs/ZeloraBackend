# P1.2: Product embeddings — add embedding_vector for semantic search

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ecommerce', '0002_product_enrichment'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='embedding_vector',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
