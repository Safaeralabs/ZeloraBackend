"""
Analytics views — Overview, channel breakdown, intent analysis, hourly charts.
Powers the Analytics module and the live Dashboard metrics in the frontend.
"""
import structlog
from pathlib import Path
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

from .models import MetricsSnapshot
from .serializers import (
    MetricsSnapshotSerializer,
    HistoricalImportUploadSerializer,
    HistoricalImportKBSerializer,
    LearningCandidateSerializer,
    LearningGenerationSerializer,
    DocumentExtractionCandidateSerializer,
    DocumentExtractionGenerationSerializer,
    CandidateBatchActionSerializer,
)
from .historical_import import import_historical_chats, list_historical_imports, get_historical_imports_root
from .kb_seed_import import import_kb_seed_for_organization
from .learning import approve_learning_candidate, generate_learning_candidates_for_org
from .document_extraction import approve_document_extraction_candidate, generate_document_extraction_candidates
from apps.conversations.models import Conversation
from apps.ai_engine.models import SalesAgentLog, AITask
from .models import LearningCandidate, DocumentExtractionCandidate
from apps.knowledge_base.models import KBDocument
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin

logger = structlog.get_logger(__name__)


class HistoricalImportView(APIView):
    permission_classes = [IsOrganizationMember]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        imports = list_historical_imports(org_slug=request.user.organization.slug)
        return Response(imports)

    def post(self, request):
        serializer = HistoricalImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        upload = serializer.validated_data['file']
        source_name = serializer.validated_data['source_name']
        org_slug = request.user.organization.slug
        output_root = get_historical_imports_root()
        upload_dir = output_root / org_slug / '_uploads'
        upload_dir.mkdir(parents=True, exist_ok=True)
        upload_path = upload_dir / f'{source_name}.jsonl'

        with upload_path.open('wb') as destination:
            for chunk in upload.chunks():
                destination.write(chunk)

        result = import_historical_chats(
            org_slug=org_slug,
            chats_path=upload_path,
            output_dir=output_root,
            source_name=source_name,
        )
        return Response(result, status=201)


class HistoricalImportKBView(APIView):
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        serializer = HistoricalImportKBSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org = request.user.organization
        source_name = serializer.validated_data['source_name']
        seed_path = get_historical_imports_root() / org.slug / source_name / 'kb_seed.json'
        if not seed_path.exists():
            return Response({'detail': 'No existe kb_seed para ese import.'}, status=404)

        result = import_kb_seed_for_organization(
            organization=org,
            seed_path=seed_path,
            author_email=request.user.email,
        )
        return Response(result)


class LearningCandidateView(APIView):
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        queryset = LearningCandidate.objects.filter(organization=request.user.organization).order_by('-updated_at')
        kind = request.query_params.get('kind')
        status_value = request.query_params.get('status')
        if kind:
            queryset = queryset.filter(kind=kind)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return Response(LearningCandidateSerializer(queryset[:200], many=True).data)

    def post(self, request):
        serializer = LearningGenerationSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        result = generate_learning_candidates_for_org(
            organization=request.user.organization,
            limit=serializer.validated_data['limit'],
        )
        return Response(result, status=201)


class LearningCandidateApproveView(APIView):
    permission_classes = [IsOrganizationMember]

    def post(self, request, pk):
        candidate = LearningCandidate.objects.filter(organization=request.user.organization, pk=pk).first()
        if candidate is None:
            return Response({'detail': 'Learning candidate not found.'}, status=404)
        article = approve_learning_candidate(candidate=candidate, author=request.user)
        return Response({'status': 'approved', 'article_id': str(article.id)})


class LearningCandidateRejectView(APIView):
    permission_classes = [IsOrganizationMember]

    def post(self, request, pk):
        updated = LearningCandidate.objects.filter(organization=request.user.organization, pk=pk).update(status='rejected')
        if not updated:
            return Response({'detail': 'Learning candidate not found.'}, status=404)
        return Response({'status': 'rejected'})


class LearningCandidateBatchView(APIView):
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        serializer = CandidateBatchActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = request.query_params.get('action', 'approve')
        queryset = LearningCandidate.objects.filter(
            organization=request.user.organization,
            pk__in=serializer.validated_data['ids'],
            status='pending',
        )
        if action == 'reject':
            updated = queryset.update(status='rejected')
            return Response({'status': 'rejected', 'count': updated})

        approved = 0
        for candidate in queryset:
            approve_learning_candidate(candidate=candidate, author=request.user)
            approved += 1
        return Response({'status': 'approved', 'count': approved})


class DocumentExtractionCandidateView(APIView):
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        queryset = DocumentExtractionCandidate.objects.filter(organization=request.user.organization).order_by('-updated_at')
        kind = request.query_params.get('kind')
        status_value = request.query_params.get('status')
        if kind:
            queryset = queryset.filter(kind=kind)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return Response(DocumentExtractionCandidateSerializer(queryset[:250], many=True).data)

    def post(self, request):
        serializer = DocumentExtractionGenerationSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        queryset = KBDocument.objects.filter(
            organization=request.user.organization,
            processing_status='ready',
            is_active=True,
        )
        if serializer.validated_data.get('document_id'):
            queryset = queryset.filter(id=serializer.validated_data['document_id'])

        created = 0
        updated = 0
        processed_documents = 0
        for document in queryset[:25]:
            result = generate_document_extraction_candidates(document=document)
            created += result['created']
            updated += result['updated']
            processed_documents += result['processed_documents']

        return Response(
            {'created': created, 'updated': updated, 'processed_documents': processed_documents},
            status=201,
        )


class DocumentExtractionCandidateApproveView(APIView):
    permission_classes = [IsOrganizationMember]

    def post(self, request, pk):
        candidate = DocumentExtractionCandidate.objects.filter(organization=request.user.organization, pk=pk).first()
        if candidate is None:
            return Response({'detail': 'Document extraction candidate not found.'}, status=404)
        result = approve_document_extraction_candidate(candidate=candidate, author=request.user)
        return Response({'status': 'approved', **result})


class DocumentExtractionCandidateRejectView(APIView):
    permission_classes = [IsOrganizationMember]

    def post(self, request, pk):
        updated = DocumentExtractionCandidate.objects.filter(
            organization=request.user.organization,
            pk=pk,
        ).update(status='rejected')
        if not updated:
            return Response({'detail': 'Document extraction candidate not found.'}, status=404)
        return Response({'status': 'rejected'})


class DocumentExtractionCandidateBatchView(APIView):
    permission_classes = [IsOrganizationMember]

    def post(self, request):
        serializer = CandidateBatchActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = request.query_params.get('action', 'approve')
        queryset = DocumentExtractionCandidate.objects.filter(
            organization=request.user.organization,
            pk__in=serializer.validated_data['ids'],
            status='pending',
        )
        if action == 'reject':
            updated = queryset.update(status='rejected')
            return Response({'status': 'rejected', 'count': updated})

        approved = 0
        for candidate in queryset:
            approve_document_extraction_candidate(candidate=candidate, author=request.user)
            approved += 1
        return Response({'status': 'approved', 'count': approved})


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


class SalesAgentMetricsView(APIView):
    """
    GET /api/analytics/sales-agent/?days=30
    Returns focused KPIs for the Sales Agent card in admin/agents.
    """
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        org = request.user.organization
        days = int(request.query_params.get('days', 30))
        since = timezone.now() - timedelta(days=days)

        logs = SalesAgentLog.objects.filter(organization=org, created_at__gte=since)
        executions = logs.count()
        conversations_count = logs.values('conversation_id').distinct().count()
        qualified_leads = logs.filter(
            stage__in=['considering', 'intent_to_buy', 'checkout_blocked', 'follow_up_needed']
        ).values('conversation_id').distinct().count()
        handoffs = logs.filter(handoff_needed=True).count()
        avg_confidence = logs.aggregate(value=Avg('confidence')).get('value') or 0.0
        product_recommendations = logs.exclude(products_shown=[]).count()
        out_of_scope = logs.filter(context_used__out_of_scope=True).count()
        followups_created = AITask.objects.filter(
            organization=org,
            task_type='sales_followup',
            created_at__gte=since,
        ).count()

        return Response({
            'period_days': days,
            'executions': executions,
            'conversations': conversations_count,
            'qualified_leads': qualified_leads,
            'followups_created': followups_created,
            'handoffs': handoffs,
            'product_recommendations': product_recommendations,
            'out_of_scope': out_of_scope,
            'avg_confidence_pct': round(avg_confidence * 100, 1) if avg_confidence <= 1 else round(avg_confidence, 1),
        })


class MetricsSnapshotViewSet(OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only access to raw MetricsSnapshot records."""
    permission_classes = [IsOrganizationMember]
    serializer_class = MetricsSnapshotSerializer
    filterset_fields = ['date', 'canal']

    def get_queryset(self):
        return MetricsSnapshot.objects.filter(
            organization=self.request.user.organization
        ).order_by('-date')
