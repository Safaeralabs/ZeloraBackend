import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('ai_engine', '0002_create_missing_tables'),
    ]

    operations = [
        migrations.CreateModel(
            name='OpenAIUsageLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('feature', models.CharField(choices=[
                    ('learning', 'Learning Engine'),
                    ('style_extraction', 'Style Extraction'),
                    ('embedding', 'Embedding'),
                    ('playbook_synthesis', 'Playbook Synthesis'),
                    ('direct_reply', 'Direct Reply'),
                    ('other', 'Other'),
                ], db_index=True, default='other', max_length=40)),
                ('model_name', models.CharField(max_length=100)),
                ('prompt_tokens', models.PositiveIntegerField(default=0)),
                ('completion_tokens', models.PositiveIntegerField(default=0)),
                ('total_tokens', models.PositiveIntegerField(default=0)),
                ('cost_usd', models.DecimalField(decimal_places=6, default=0, max_digits=10)),
                ('latency_ms', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='openai_usage_logs',
                    to='accounts.organization',
                )),
            ],
            options={
                'db_table': 'openai_usage_logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='openaiusagelog',
            index=models.Index(fields=['organization', 'created_at'], name='openai_usag_organiz_91a2aa_idx'),
        ),
        migrations.AddIndex(
            model_name='openaiusagelog',
            index=models.Index(fields=['organization', 'feature', 'created_at'], name='openai_usag_organiz_138f03_idx'),
        ),
    ]
