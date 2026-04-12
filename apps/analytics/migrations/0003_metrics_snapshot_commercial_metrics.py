# P3.3: Add commercial metrics to MetricsSnapshot

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0002_metrics_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='metricssnapshot',
            name='aov',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Average order value', max_digits=12),
        ),
        migrations.AddField(
            model_name='metricssnapshot',
            name='brand_fit_score',
            field=models.FloatField(default=0, help_text='Avg brand_fit from evaluator (0-1)'),
        ),
        migrations.AddField(
            model_name='metricssnapshot',
            name='conversations_with_order',
            field=models.IntegerField(default=0, help_text='conversations that converted to orders'),
        ),
        migrations.AddField(
            model_name='metricssnapshot',
            name='cvr',
            field=models.FloatField(default=0, help_text='Conversion rate: conversations_with_order / total_conversations'),
        ),
        migrations.AddField(
            model_name='metricssnapshot',
            name='naturalness_score',
            field=models.FloatField(default=0, help_text='Avg naturalness from evaluator (0-1)'),
        ),
        migrations.AddField(
            model_name='metricssnapshot',
            name='reply_rate',
            field=models.FloatField(default=0, help_text='% conversations where bot replied'),
        ),
        migrations.AddField(
            model_name='metricssnapshot',
            name='total_order_value',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]
