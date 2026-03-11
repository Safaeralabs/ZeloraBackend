"""
Analytics views — Overview, channel breakdown, intent analysis, hourly charts.
Powers the Analytics module and the live Dashboard metrics in the frontend.
"""
import structlog
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from datetime import timedelta

from .models import MetricsSnapshot
from .serializers import MetricsSnapshotSerializer
from apps.conversations.models import Conversation
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin

logger = structlog.get_logger(__name__)


class OverviewView(APIView):
    """
    GET /api/analytics/overview/?days=30
    Returns top-level KPIs for the Dashboard.
    Response matches frontend MetricsOverview shape.
    """
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        org = request.user.organization
        days = int(request.query_params.get('days', 30))
        since = timezone.now() - timedelta(days=days)

        conversations = Conversation.objects.filter(organization=org, created_at__gte=since)
        total = conversations.count()
        resolved = conversations.filter(estado='resuelto').count()
        escalated = conversations.filter(estado='escalado').count()
        bot_handled = conversations.filter(
            messages__role='bot'
        ).distinct().count()

        # By-channel breakdown
        by_channel = list(
            conversations.values('canal')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Agent workload
        by_agent = list(
            conversations.exclude(assigned_agent=None)
            .values('assigned_agent__nombre', 'assigned_agent__apellido')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        automation_pct = round(bot_handled / total * 100, 1) if total else 0.0
        escalation_pct = round(escalated / total * 100, 1) if total else 0.0
        resolution_rate = round(resolved / total * 100, 1) if total else 0.0

        return Response({
            # Frontend MetricsOverview fields
            'total_conversaciones': total,
            'automatizacion_pct': automation_pct,
            'escalamiento_pct': escalation_pct,
            'satisfaccion_pct': 91.0,  # TODO: calculate from CSAT when surveys are implemented
            'tiempo_promedio_seg': 38,  # TODO: calculate from message timestamps
            # Extended fields
            'total_conversations': total,
            'resolved': resolved,
            'escalated': escalated,
            'bot_handled': bot_handled,
            'resolution_rate': resolution_rate,
            'by_channel': by_channel,
            'by_agent': by_agent,
            'period_days': days,
        })


class SummaryView(OverviewView):
    """
    GET /api/analytics/summary/
    Alias for OverviewView — used by the Dashboard component.
    """
    pass


class HourlyView(APIView):
    """
    GET /api/analytics/hourly/?days=7
    Returns conversation counts grouped by hour of day for chart rendering.
    """
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        from django.db.models.functions import TruncHour
        org = request.user.organization
        days = int(request.query_params.get('days', 7))
        since = timezone.now() - timedelta(days=days)

        hourly = (
            Conversation.objects
            .filter(organization=org, created_at__gte=since)
            .annotate(hour=TruncHour('created_at'))
            .values('hour')
            .annotate(count=Count('id'))
            .order_by('hour')
        )

        return Response({
            'data': [
                {'hour': item['hour'].isoformat(), 'count': item['count']}
                for item in hourly
            ],
            'period_days': days,
        })


class ChannelMetricsView(APIView):
    """
    GET /api/analytics/channels/?days=30
    Returns per-channel metrics from MetricsSnapshot aggregates.
    """
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        org = request.user.organization
        days = int(request.query_params.get('days', 30))
        since = timezone.now().date() - timedelta(days=days)
        snapshots = MetricsSnapshot.objects.filter(organization=org, date__gte=since)

        by_channel = list(
            snapshots.values('canal').annotate(
                total=Sum('total_conversations'),
                resolved_sum=Sum('resolved'),
                escalated_sum=Sum('escalated'),
                ai_handled_sum=Sum('ai_handled'),
                avg_csat=Avg('csat_score'),
                avg_response_time=Avg('avg_response_time_s'),
            ).order_by('-total')
        )

        return Response({
            'channels': by_channel,
            'period_days': days,
        })


class IntentMetricsView(APIView):
    """
    GET /api/analytics/intents/?days=30
    Returns top intents from resolved conversations.
    """
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        org = request.user.organization
        days = int(request.query_params.get('days', 30))
        since = timezone.now() - timedelta(days=days)

        intents = (
            Conversation.objects
            .filter(organization=org, created_at__gte=since)
            .exclude(intent='')
            .values('intent')
            .annotate(count=Count('id'))
            .order_by('-count')[:15]
        )
        total = sum(i['count'] for i in intents)

        result = [
            {
                'nombre': i['intent'],
                'count': i['count'],
                'porcentaje': round(i['count'] / total * 100, 1) if total else 0,
            }
            for i in intents
        ]
        return Response(result)


class MetricsSnapshotViewSet(OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only access to raw MetricsSnapshot records."""
    permission_classes = [IsOrganizationMember]
    serializer_class = MetricsSnapshotSerializer
    filterset_fields = ['date', 'canal']

    def get_queryset(self):
        return MetricsSnapshot.objects.filter(
            organization=self.request.user.organization
        ).order_by('-date')
