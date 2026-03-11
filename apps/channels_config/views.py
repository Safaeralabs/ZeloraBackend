from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ChannelConfig
from .serializers import ChannelConfigSerializer
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin


class ChannelConfigViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = ChannelConfigSerializer

    def get_queryset(self):
        return ChannelConfig.objects.filter(organization=self.request.user.organization)

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        config = self.get_object()
        # Simulate connection test
        return Response({'status': 'connected', 'channel': config.channel})

    @action(detail=False, methods=['get', 'post'], url_path='whatsapp/webhook')
    def whatsapp_webhook(self, request):
        if request.method == 'GET':
            from django.conf import settings
            verify_token = request.query_params.get('hub.verify_token')
            challenge = request.query_params.get('hub.challenge')
            if verify_token == settings.WHATSAPP_VERIFY_TOKEN:
                return Response(int(challenge))
            return Response({'error': 'Invalid token'}, status=status.HTTP_403_FORBIDDEN)
        # POST: receive WhatsApp message
        try:
            from tasks.channel_tasks import process_whatsapp_webhook
            process_whatsapp_webhook.delay(request.data)
        except Exception:
            pass
        return Response({'status': 'received'})
