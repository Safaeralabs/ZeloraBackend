import django.db.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ecommerce', '0002_product_enrichment'),
    ]

    operations = [
        migrations.AddField(
            model_name='promotion',
            name='scope',
            field=models.CharField(
                choices=[
                    ('product', 'Product discount'),
                    ('order', 'Order discount'),
                    ('shipping', 'Shipping discount'),
                ],
                default='product',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='promotion',
            name='trigger_type',
            field=models.CharField(
                choices=[('automatic', 'Automatic'), ('code', 'Discount code')],
                default='automatic',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='promotion',
            name='code',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='promotion',
            name='min_subtotal',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='promotion',
            name='min_qty',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='promotion',
            name='buy_x_qty',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='promotion',
            name='get_y_qty',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='promotion',
            name='combinable',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='promotion',
            name='priority',
            field=models.PositiveIntegerField(default=100),
        ),
        migrations.AddIndex(
            model_name='promotion',
            index=django.db.models.Index(fields=['organization', 'scope', 'is_active'], name='promo_org_scope_active_idx'),
        ),
    ]
