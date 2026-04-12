"""
P3.3: Management command to calculate daily commercial metrics for all organizations.

Usage:
  python manage.py calculate_daily_metrics [--date YYYY-MM-DD] [--org <org_id>]

This command calculates:
- CVR (conversion rate)
- AOV (average order value)
- Reply rate
- Naturalness score
- Brand fit score

Can be scheduled as a Celery beat task or cron job.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Count, Avg, Q
from django.utils import timezone

from apps.accounts.models import Organization
from apps.analytics.models import MetricsSnapshot
from apps.conversations.models import Conversation, ConversationMessage
from apps.ecommerce.models import Order
from apps.ai_engine.models import SalesAgentLog


class Command(BaseCommand):
    help = 'Calculate daily commercial metrics for organizations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Calculate for specific date (YYYY-MM-DD). Default: yesterday',
        )
        parser.add_argument(
            '--org',
            type=str,
            default=None,
            help='Limit to specific organization UUID',
        )

    def handle(self, *args, **options):
        # Determine target date
        if options['date']:
            try:
                target_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
            except ValueError:
                self.stderr.write(self.style.ERROR('Invalid date format. Use YYYY-MM-DD'))
                return
        else:
            target_date = (timezone.now() - timedelta(days=1)).date()

        self.stdout.write(f'Calculating metrics for {target_date}')

        # Get organizations
        orgs = Organization.objects.all()
        if options['org']:
            orgs = orgs.filter(id=options['org'])

        for org in orgs:
            self._calculate_org_metrics(org, target_date)

        self.stdout.write(self.style.SUCCESS('Metrics calculation complete'))

    def _calculate_org_metrics(self, org: Organization, target_date):
        """Calculate metrics for a single organization on a specific date."""
        # Date range: start of day to end of day
        start_of_day = timezone.make_aware(
            datetime.combine(target_date, datetime.min.time())
        )
        end_of_day = timezone.make_aware(
            datetime.combine(target_date, datetime.max.time())
        )

        # Get conversations for this day
        conversations = Conversation.objects.filter(
            organization=org,
            created_at__gte=start_of_day,
            created_at__lte=end_of_day,
        )

        total = conversations.count()
        if total == 0:
            self.stdout.write(f'  {org.name}: No conversations on {target_date}')
            return

        # Metrics by channel
        by_channel = conversations.values('canal').annotate(count=Count('id'))

        for channel_data in by_channel:
            canal = channel_data.get('canal', 'unknown')
            channel_convs = conversations.filter(canal=canal)
            channel_total = channel_data['count']

            # Calculate commercial metrics
            resolved = channel_convs.filter(estado='resuelto').count()
            escalated = channel_convs.filter(estado='escalado').count()

            # P3.3: CVR (Conversion Rate)
            conversations_with_orders = channel_convs.filter(
                orders__isnull=False
            ).distinct().count()
            cvr = (conversations_with_orders / channel_total * 100) if channel_total > 0 else 0

            # P3.3: AOV (Average Order Value)
            orders = Order.objects.filter(conversation__in=channel_convs)
            total_order_value = orders.aggregate(Avg('total'))['total__avg'] or 0
            total_revenue = orders.aggregate(Sum=Sum('total'))['Sum'] or Decimal(0)

            # P3.3: Reply Rate (% conversations where bot replied)
            bot_replied = channel_convs.filter(
                messages__role='bot'
            ).distinct().count()
            reply_rate = (bot_replied / channel_total * 100) if channel_total > 0 else 0

            # P3.3: Quality scores from evaluator (from SalesAgentLog)
            agent_logs = SalesAgentLog.objects.filter(
                conversation__in=channel_convs,
                evaluation_score__isnull=False,
            )

            naturalness_scores = agent_logs.filter(
                evaluation_flags__contains='unnatural'  # TODO: better extraction
            ).aggregate(Avg('evaluation_score'))['evaluation_score__avg']
            naturalness_score = float(naturalness_scores) if naturalness_scores else 0.7

            brand_fit_scores = agent_logs.filter(
                evaluation_flags__contains='brand_fit'  # TODO: better extraction
            ).aggregate(Avg('evaluation_score'))['evaluation_score__avg']
            brand_fit_score = float(brand_fit_scores) if brand_fit_scores else 0.75

            # Create or update MetricsSnapshot
            snapshot, created = MetricsSnapshot.objects.update_or_create(
                organization=org,
                date=target_date,
                canal=canal,
                defaults={
                    'total_conversations': channel_total,
                    'resolved': resolved,
                    'escalated': escalated,
                    'ai_handled': bot_replied,
                    'conversations_with_order': conversations_with_orders,
                    'cvr': cvr,
                    'total_order_value': total_revenue,
                    'aov': Decimal(str(total_order_value or 0)),
                    'reply_rate': reply_rate,
                    'naturalness_score': naturalness_score,
                    'brand_fit_score': brand_fit_score,
                },
            )

            action = 'Created' if created else 'Updated'
            self.stdout.write(
                f'  {org.name} / {canal}: {action} '
                f'(CVR={cvr:.1f}%, AOV={total_order_value or 0:.2f}, '
                f'Reply={reply_rate:.1f}%, Naturalness={naturalness_score:.2f})'
            )


def Sum(field):
    """Helper to aggregate sum."""
    from django.db.models import Sum as DjangoSum
    return DjangoSum(field)
