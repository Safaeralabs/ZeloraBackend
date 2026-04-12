# P1.1: Product enrichment — add attributes for recommendation engine & create Promotion & ProductRelation models

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ecommerce', '0001_initial'),
    ]

    operations = [
        # Add new fields to Product
        migrations.AddField(
            model_name='product',
            name='subcategory',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='product',
            name='occasion',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='product',
            name='style',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='product',
            name='color',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='product',
            name='material',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='product',
            name='fit',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='product',
            name='formality',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='product',
            name='target_audience',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='product',
            name='is_bestseller',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='product',
            name='popularity_score',
            field=models.FloatField(default=0.0),
        ),
        # Add indexes to Product
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['organization', 'is_bestseller'], name='prod_org_bestseller_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['organization', 'formality'], name='prod_org_formality_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['organization', 'is_active'], name='prod_org_active_idx'),
        ),
        # Create Promotion model
        migrations.CreateModel(
            name='Promotion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('discount_type', models.CharField(choices=[('percentage', 'Percentage off'), ('fixed_amount', 'Fixed amount off'), ('free_shipping', 'Free shipping'), ('bundle', 'Bundle deal')], max_length=20)),
                ('discount_value', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('applies_to', models.CharField(choices=[('all_products', 'All products'), ('category', 'Category'), ('specific_products', 'Specific products')], default='all_products', max_length=30)),
                ('category', models.CharField(blank=True, max_length=100)),
                ('starts_at', models.DateTimeField(blank=True, null=True)),
                ('ends_at', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='promotions', to='accounts.organization')),
                ('products', models.ManyToManyField(blank=True, related_name='promotions', to='ecommerce.product')),
            ],
            options={
                'db_table': 'promotions',
                'ordering': ['-updated_at'],
            },
        ),
        # Add index to Promotion
        migrations.AddIndex(
            model_name='promotion',
            index=models.Index(fields=['organization', 'is_active'], name='promo_org_active_idx'),
        ),
        # Create ProductRelation model
        migrations.CreateModel(
            name='ProductRelation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('relation_type', models.CharField(choices=[('combina_con', 'Combina con'), ('evita_con', 'Evita con'), ('bundle_con', 'Bundle con'), ('alternativa_barata', 'Alternativa barata'), ('alternativa_premium', 'Alternativa premium'), ('similar_a', 'Similar a')], max_length=30)),
                ('weight', models.FloatField(default=1.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='product_relations', to='accounts.organization')),
                ('source_product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relations_as_source', to='ecommerce.product')),
                ('target_product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relations_as_target', to='ecommerce.product')),
            ],
            options={
                'db_table': 'product_relations',
                'ordering': ['-created_at'],
            },
        ),
        # Add index to ProductRelation
        migrations.AddIndex(
            model_name='productrelation',
            index=models.Index(fields=['organization', 'source_product'], name='prodrel_org_source_idx'),
        ),
        # Add unique constraint to ProductRelation
        migrations.AddConstraint(
            model_name='productrelation',
            constraint=models.UniqueConstraint(fields=['source_product', 'target_product', 'relation_type'], name='uniq_product_relation'),
        ),
    ]
