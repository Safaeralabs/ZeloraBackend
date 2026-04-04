from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from django.db.models import Q
from .models import KBArticle, KBDocument
from .serializers import KBArticleSerializer, KBDocumentSerializer
from .upload_security import validate_kb_upload
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin


class KBArticleViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = KBArticleSerializer
    filterset_fields = ['status', 'category']
    search_fields = ['title', 'content']

    def get_queryset(self):
        return KBArticle.objects.filter(organization=self.request.user.organization)

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            author=self.request.user,
        )

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
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return KBDocument.objects.filter(organization=self.request.user.organization)

    def perform_create(self, serializer):
        from django.conf import settings
        from tasks.ai_tasks import process_kb_document

        uploaded_file = self.request.FILES.get('file')
        validate_kb_upload(uploaded_file)
        doc = serializer.save(
            organization=self.request.user.organization,
            filename=getattr(uploaded_file, 'name', ''),
            file_size=getattr(uploaded_file, 'size', 0),
            mime_type=getattr(uploaded_file, 'content_type', ''),
            processing_status='processing',
        )

        # In local/dev flows we process inline so the document is usable immediately.
        try:
            if getattr(settings, 'DEBUG', False) or getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
                process_kb_document.apply(args=[str(doc.id)])
            else:
                process_kb_document.delay(str(doc.id))
        except Exception:
            doc.processing_status = 'failed'
            doc.save(update_fields=['processing_status', 'processed', 'updated_at'])
