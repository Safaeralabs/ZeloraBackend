# P3.1: Add ContactMemory model for per-contact persistent memory

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('ai_engine', '0004_sales_agent_log_evaluation_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContactMemory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('inferred_budget_min', models.DecimalField(blank=True, decimal_places=2, help_text='Min budget inferred from conversation (e.g., "presupuesto 50k")', max_digits=12, null=True)),
                ('inferred_budget_max', models.DecimalField(blank=True, decimal_places=2, help_text='Max budget inferred', max_digits=12, null=True)),
                ('style_cues', models.JSONField(blank=True, default=dict, help_text='Inferred style patterns: {"tone": "casual", "urgency": "high", "decision_speed": "quick"}')),
                ('occasion_hints', models.JSONField(blank=True, default=list, help_text='e.g., ["boda", "trabajo", "casual"]')),
                ('category_preferences', models.JSONField(blank=True, default=list, help_text='Categories shown/mentioned: ["clothing", "electronics"]')),
                ('last_products_shown', models.JSONField(blank=True, default=list, help_text='Last 5 product IDs shown to this contact')),
                ('last_intent', models.CharField(blank=True, help_text='Last detected intent: discovering, considering, intent_to_buy, checkout_blocked, etc.', max_length=50)),
                ('last_objection', models.CharField(blank=True, help_text='Last detected objection: price, shipping, availability, trust, quality, urgency', max_length=50)),
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
            index=models.Index(fields=['organization', 'contact'], name='contact_memories_org_contact_idx'),
        ),
        migrations.AddIndex(
            model_name='contactmemory',
            index=models.Index(fields=['organization', 'updated_at'], name='contact_memories_org_updated_idx'),
        ),
    ]
