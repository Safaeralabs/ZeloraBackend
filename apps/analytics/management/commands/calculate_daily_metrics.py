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
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.accounts.models import Organization
from apps.analytics.models import MetricsSnapshot
from apps.conversations.models import Conversation
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
            channel_orders = self._orders_for_channel(
                org=org,
                channel_convs=channel_convs,
                canal=canal,
                start_of_day=start_of_day,
                end_of_day=end_of_day,
            )
            contact_ids_with_orders = set(
                channel_orders.exclude(contact_id__isnull=True).values_list('contact_id', flat=True)
            )
            conversations_with_orders = channel_convs.filter(
                contact_id__in=contact_ids_with_orders
            ).exclude(contact_id__isnull=True).distinct().count()
            # CVR ratio in 0-1 range (not percentage)
            cvr = (conversations_with_orders / channel_total) if channel_total > 0 else 0

            # P3.3: AOV (Average Order Value)
            avg_order_value = channel_orders.aggregate(avg_total=Avg('total'))['avg_total'] or Decimal(0)
            total_revenue = channel_orders.aggregate(sum_total=Sum('total'))['sum_total'] or Decimal(0)

            # P3.3: Reply Rate (% conversations where bot replied)
            bot_replied = channel_convs.filter(
                messages__role='bot'
            ).distinct().count()
            reply_rate = (bot_replied / channel_total * 100) if channel_total > 0 else 0

            # P3.3: Quality scores from evaluator (from SalesAgentLog)
            agent_logs = SalesAgentLog.objects.filter(
                conversation__in=channel_convs,
                channel=canal,
                evaluation_score__isnull=False,
            )

            avg_naturalidad = agent_logs.aggregate(avg_nat=Avg('evaluation_naturalidad'))['avg_nat']
            avg_brand_fit = agent_logs.aggregate(avg_brand=Avg('evaluation_brand_fit'))['avg_brand']
            avg_eval_score = agent_logs.aggregate(avg_score=Avg('evaluation_score'))['avg_score']

            naturalness_score = (
                float(avg_naturalidad) if avg_naturalidad is not None
                else (float(avg_eval_score) if avg_eval_score is not None else 0.7)
            )
            brand_fit_score = (
                float(avg_brand_fit) if avg_brand_fit is not None
                else (float(avg_eval_score) if avg_eval_score is not None else 0.75)
            )

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
                    'aov': Decimal(str(avg_order_value or 0)),
                    'reply_rate': reply_rate,
                    'naturalness_score': naturalness_score,
                    'brand_fit_score': brand_fit_score,
                },
            )

            action = 'Created' if created else 'Updated'
            self.stdout.write(
                f'  {org.name} / {canal}: {action} '
                f'(CVR={cvr:.3f}, AOV={avg_order_value or 0:.2f}, '
                f'Reply={reply_rate:.1f}%, Naturalness={naturalness_score:.2f})'
            )

    def _orders_for_channel(self, *, org, channel_convs, canal: str, start_of_day, end_of_day):
        """
        Build an Order queryset that can be linked to channel conversations via contact + day window.
        Orders currently do not have a direct FK to Conversation.
        """
        contact_ids = list(
            channel_convs.exclude(contact_id__isnull=True)
            .values_list('contact_id', flat=True)
            .distinct()
        )
        if not contact_ids:
            return Order.objects.none()

        channel_map = {
            'whatsapp': ['whatsapp'],
            'instagram': ['instagram'],
            'web': ['web', 'ecommerce'],
            'app': ['app'],
        }
        order_channels = channel_map.get(canal)

        orders = Order.objects.filter(
            organization=org,
            created_at__gte=start_of_day,
            created_at__lte=end_of_day,
            contact_id__in=contact_ids,
        )
        if order_channels:
            orders = orders.filter(channel__in=order_channels)
        return orders
