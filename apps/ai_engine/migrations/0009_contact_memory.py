# Re-adds ContactMemory (deleted in 0007_remove_sales_agent) for the v2
# architecture: soft, cross-conversation customer signals kept in sync from
# SessionManager.update(), read by CustomerHistoryService's sibling
# ContactMemoryService and by conversations/serializers.py::get_contact_memory
# (which already expected this exact shape and silently returned None since
# the model was removed).
#
# Scoped to ONLY this model: unrelated drift detected by makemigrations
# (OpenAIUsageLog fields, SalesSession index renames) is pre-existing and
# out of scope here.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_email_verification'),
        ('ai_engine', '0008_sales_session'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContactMemory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('inferred_budget_min', models.DecimalField(blank=True, decimal_places=2, help_text='Min budget inferred from conversation (e.g., "presupuesto 50k")', max_digits=12, null=True)),
                ('inferred_budget_max', models.DecimalField(blank=True, decimal_places=2, help_text='Max budget inferred', max_digits=12, null=True)),
                ('style_cues', models.JSONField(blank=True, default=dict, help_text='Inferred style patterns: {"tone": "casual", "urgency": "high"}')),
                ('occasion_hints', models.JSONField(blank=True, default=list, help_text='e.g. ["boda", "trabajo"]')),
                ('category_preferences', models.JSONField(blank=True, default=list, help_text='Categories shown/mentioned')),
                ('last_products_shown', models.JSONField(blank=True, default=list, help_text='Last product IDs shown')),
                ('last_intent', models.CharField(blank=True, default='', max_length=50)),
                ('last_objection', models.CharField(blank=True, default='', max_length=50)),
                ('conversation_count', models.PositiveIntegerField(default=0)),
                ('last_conversation_at', models.DateTimeField(blank=True, null=True)),
                ('total_products_viewed', models.PositiveIntegerField(default=0)),
                ('converted', models.BooleanField(default=False, help_text='Has this contact purchased?')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('contact', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='memory', to='accounts.contact')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contact_memories', to='accounts.organization')),
            ],
            options={
                'db_table': 'contact_memories',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='contactmemory',
            index=models.Index(fields=['organization', 'updated_at'], name='contact_mem_organiz_90903a_idx'),
        ),
    ]
