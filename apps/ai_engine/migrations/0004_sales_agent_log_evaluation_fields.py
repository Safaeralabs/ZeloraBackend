# P2.4: Add evaluation fields to SalesAgentLog for pre-send quality checks

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_engine', '0003_openai_usage_log'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesagentlog',
            name='channel',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='salesagentlog',
            name='evaluation_flags',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='salesagentlog',
            name='evaluation_score',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
