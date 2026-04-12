# P3.3/P2.4: Persist evaluator dimensions in SalesAgentLog for robust analytics

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_engine', '0005_contact_memory'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesagentlog',
            name='evaluation_brand_fit',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='salesagentlog',
            name='evaluation_coherencia',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='salesagentlog',
            name='evaluation_cta_quality',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='salesagentlog',
            name='evaluation_naturalidad',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
