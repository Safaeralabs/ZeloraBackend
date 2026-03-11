from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import KBArticle, KBDocument
from .serializers import KBArticleSerializer, KBDocumentSerializer
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin


class KBArticleViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = KBArticleSerializer
    filterset_fields = ['status', 'category']
    search_fields = ['title', 'content']

    def get_queryset(self):
        return KBArticle.objects.filter(organization=self.request.user.organization)

    @action(detail=True, methods=['post'])
    def visit(self, request, pk=None):
        article = self.get_object()
        article.visits += 1
        article.save(update_fields=['visits'])
        return Response({'visits': article.visits})

    @action(detail=False, methods=['get'])
    def search(self, request):
        q = request.query_params.get('q', '')
        qs = self.get_queryset().filter(
            status='published'
        ).filter(Q(title__icontains=q) | Q(content__icontains=q))
        return Response(KBArticleSerializer(qs[:10], many=True).data)


class KBDocumentViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = KBDocumentSerializer

    def get_queryset(self):
        return KBDocument.objects.filter(organization=self.request.user.organization)

    def perform_create(self, serializer):
        doc = serializer.save(organization=self.request.user.organization)
        # Async: process document for RAG
        try:
            from tasks.ai_tasks import process_kb_document
            process_kb_document.delay(str(doc.id))
        except Exception:
            pass
