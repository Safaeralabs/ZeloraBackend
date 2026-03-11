from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Template, Campaign
from .serializers import TemplateSerializer, CampaignSerializer
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin


class TemplateViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = TemplateSerializer

    def get_queryset(self):
        return Template.objects.filter(organization=self.request.user.organization)


class CampaignViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = CampaignSerializer
    filterset_fields = ['status', 'channel']

    def get_queryset(self):
        return Campaign.objects.filter(organization=self.request.user.organization)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status not in ('draft', 'scheduled'):
            return Response(
                {'error': 'Campaign already sent'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        campaign.status = 'sending'
        campaign.save(update_fields=['status'])
        try:
            from tasks.campaign_tasks import send_campaign
            send_campaign.delay(str(campaign.id))
        except Exception:
            pass
        return Response({'status': 'sending'})
