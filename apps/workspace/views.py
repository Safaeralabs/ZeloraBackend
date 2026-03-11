"""
Workspace views — Collab notes and agent performance snapshots.
"""
import structlog
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin
from .models import CollabNote, AgentPerformanceSnapshot
from .serializers import CollabNoteSerializer, AgentPerformanceSnapshotSerializer

logger = structlog.get_logger(__name__)


class CollabNoteViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    """Collaborative conversation notes."""
    permission_classes = [IsOrganizationMember]
    serializer_class = CollabNoteSerializer
    filterset_fields = ['note_type', 'is_pinned', 'conversation']
    search_fields = ['content']

    def get_queryset(self):
        return CollabNote.objects.filter(
            organization=self.request.user.organization
        ).select_related('author')

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            author=self.request.user,
        )

    @action(detail=True, methods=['post'])
    def pin(self, request, pk=None):
        note = self.get_object()
        note.is_pinned = not note.is_pinned
        note.save(update_fields=['is_pinned'])
        return Response({'is_pinned': note.is_pinned})


class AgentPerformanceViewSet(OrgScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Agent performance snapshots (read-only — populated by Celery)."""
    permission_classes = [IsOrganizationMember]
    serializer_class = AgentPerformanceSnapshotSerializer
    filterset_fields = ['agent', 'date']

    def get_queryset(self):
        return AgentPerformanceSnapshot.objects.filter(
            organization=self.request.user.organization
        ).select_related('agent').order_by('-date')

    @action(detail=False, methods=['get'], url_path='me')
    def my_performance(self, request):
        """Performance snapshots for the currently authenticated agent."""
        qs = self.get_queryset().filter(agent=request.user)
        serializer = self.get_serializer(qs[:30], many=True)
        return Response(serializer.data)
