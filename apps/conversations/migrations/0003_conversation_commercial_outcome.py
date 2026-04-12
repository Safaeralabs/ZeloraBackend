# L5: Add commercial_outcome field to Conversation for learning feedback

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='commercial_outcome',
            field=models.CharField(
                blank=True,
                choices=[('browsing', 'Browsing only'), ('abandoned', 'Abandoned'), ('purchased', 'Purchased')],
                db_index=True,
                help_text='Whether conversation resulted in a purchase order',
                max_length=20,
                null=True,
            ),
        ),
    ]
