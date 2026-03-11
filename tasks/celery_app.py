"""
Celery application factory for Vendly.

Usage:
  Worker:    celery -A tasks.celery_app worker --loglevel=info -Q default,ai,channels,campaigns
  Beat:      celery -A tasks.celery_app beat   --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
  Flower:    celery -A tasks.celery_app flower
"""
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('vendly')

# Read config from Django settings with the CELERY_ namespace prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all INSTALLED_APPS
app.autodiscover_tasks()

# ─── Periodic Tasks (registered at startup; can also be managed via Django admin) ─
@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    from celery.schedules import crontab

    # Compute daily metrics snapshot — runs every night at 01:00 COT
    sender.add_periodic_task(
        crontab(hour=1, minute=0),
        compute_daily_metrics.s(),
        name='compute-daily-metrics',
    )

    # Generate AI insights — every day at 02:00 COT
    sender.add_periodic_task(
        crontab(hour=2, minute=0),
        generate_daily_insights.s(),
        name='generate-daily-insights',
    )


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Diagnostic task — prints request info."""
    print(f'Request: {self.request!r}')


@app.task(name='tasks.celery_app.compute_daily_metrics')
def compute_daily_metrics():
    """
    Compute and store DailyMetric snapshots for all active organizations.
    Called nightly at 01:00 COT.
    """
    import structlog
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count, Avg

    logger = structlog.get_logger(__name__)
    yesterday = (timezone.now() - timedelta(days=1)).date()

    try:
        from apps.accounts.models import Organization
        from apps.conversations.models import Conversation
        from apps.analytics.models import MetricsSnapshot

        orgs = Organization.objects.filter(is_active=True)
        created_count = 0

        for org in orgs:
            convs = Conversation.objects.filter(
                organization=org,
                created_at__date=yesterday,
            )
            channels = convs.values('canal').annotate(
                total=Count('id'),
                resolved=Count('id', filter=__import__('django.db.models', fromlist=['Q']).Q(estado='resuelto')),
                escalated=Count('id', filter=__import__('django.db.models', fromlist=['Q']).Q(estado='escalado')),
            )

            for ch in channels:
                MetricsSnapshot.objects.update_or_create(
                    organization=org,
                    date=yesterday,
                    canal=ch['canal'],
                    defaults={
                        'total_conversations': ch['total'],
                        'resolved': ch['resolved'],
                        'escalated': ch['escalated'],
                    },
                )
                created_count += 1

        logger.info('daily_metrics_computed', date=str(yesterday), snapshots=created_count)
        return {'status': 'ok', 'date': str(yesterday), 'snapshots': created_count}

    except Exception as e:
        logger.error('daily_metrics_error', error=str(e))
        raise


@app.task(name='tasks.celery_app.generate_daily_insights')
def generate_daily_insights():
    """
    Generate AI insights for each active organization based on yesterday's metrics.
    """
    import structlog
    from django.utils import timezone
    from datetime import timedelta

    logger = structlog.get_logger(__name__)
    yesterday = (timezone.now() - timedelta(days=1)).date()

    try:
        from apps.accounts.models import Organization
        from apps.ai_engine.models import AIInsight
        from apps.analytics.models import MetricsSnapshot
        from django.db.models import Sum

        orgs = Organization.objects.filter(is_active=True)
        insights_created = 0

        for org in orgs:
            snapshots = MetricsSnapshot.objects.filter(organization=org, date=yesterday)
            if not snapshots.exists():
                continue

            totals = snapshots.aggregate(
                total=Sum('total_conversations'),
                resolved=Sum('resolved'),
                escalated=Sum('escalated'),
            )
            total = totals['total'] or 0
            if total == 0:
                continue

            escalation_rate = (totals['escalated'] or 0) / total * 100
            resolution_rate = (totals['resolved'] or 0) / total * 100

            # Insight: high escalation rate
            if escalation_rate > 20:
                AIInsight.objects.create(
                    organization=org,
                    category='performance',
                    severity='warning',
                    title=f'Alta tasa de escalamiento: {escalation_rate:.1f}%',
                    description=(
                        f'Ayer se escaló el {escalation_rate:.1f}% de las conversaciones. '
                        'Revise los motivos de escalamiento y ajuste el flujo de atención.'
                    ),
                    metric_value=escalation_rate,
                    action_suggested='Revisar flujos de escalamiento y entrenar base de conocimiento.',
                )
                insights_created += 1

            # Insight: good resolution rate
            if resolution_rate > 80:
                AIInsight.objects.create(
                    organization=org,
                    category='performance',
                    severity='positive',
                    title=f'Excelente tasa de resolución: {resolution_rate:.1f}%',
                    description=f'El {resolution_rate:.1f}% de las conversaciones de ayer fueron resueltas.',
                    metric_value=resolution_rate,
                )
                insights_created += 1

        logger.info('daily_insights_generated', date=str(yesterday), insights=insights_created)
        return {'status': 'ok', 'insights_created': insights_created}

    except Exception as e:
        logger.error('generate_insights_error', error=str(e))
        raise
