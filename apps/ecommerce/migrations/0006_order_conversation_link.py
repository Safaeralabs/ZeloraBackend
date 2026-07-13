import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0001_initial'),
        ('ecommerce', '0005_order_enhancements'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='conversation',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='orders',
                to='conversations.conversation',
            ),
        ),
    ]
