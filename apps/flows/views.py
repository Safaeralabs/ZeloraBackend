from rest_framework import viewsets
from .models import Flow
from .serializers import FlowSerializer
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin


class FlowViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = FlowSerializer
    filterset_fields = ['is_active', 'channel']

    def get_queryset(self):
        return Flow.objects.filter(organization=self.request.user.organization)
