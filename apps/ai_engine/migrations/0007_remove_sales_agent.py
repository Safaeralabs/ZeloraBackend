# Generated migration: Remove SalesAgentLog and ContactMemory models

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ai_engine', '0006_sales_agent_log_evaluation_dimensions'),
    ]

    operations = [
        migrations.DeleteModel(
            name='SalesAgentLog',
        ),
        migrations.DeleteModel(
            name='ContactMemory',
        ),
    ]
