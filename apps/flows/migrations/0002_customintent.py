import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flows', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomIntent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='custom_intents',
                    to='accounts.organization',
                )),
                ('name', models.SlugField(max_length=80)),
                ('label', models.CharField(max_length=120)),
                ('keywords', models.JSONField(default=list)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'flows_custom_intents',
                'ordering': ['label'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='customintent',
            unique_together={('organization', 'name')},
        ),
    ]
