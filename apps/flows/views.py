from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Flow, CustomIntent
from .serializers import FlowSerializer
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin


class FlowViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = FlowSerializer
    filterset_fields = ['is_active', 'channel']

    def get_queryset(self):
        return Flow.objects.filter(organization=self.request.user.organization)


_SYSTEM_INTENT_LABELS: dict[str, str] = {
    'check_subsidy': 'Consulta de subsidio',
    'request_certificate': 'Solicitud de certificado',
    'book_appointment': 'Agendar cita',
    'buy_intent': 'Intención de compra',
    'order_status': 'Estado de pedido',
    'product_inquiry': 'Consulta de producto',
    'price_inquiry': 'Consulta de precio',
    'return_request': 'Solicitud de devolución',
    'general_faq': 'Pregunta general (FAQ)',
}


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def flow_intents_list(request):
    """
    GET  — system intents + org custom intents
    POST — create a custom intent for this org
    """
    org = request.user.organization

    if request.method == 'GET':
        from apps.ai_router.schemas import IntentName
        system = [
            {'id': None, 'value': i.value, 'label': _SYSTEM_INTENT_LABELS.get(i.value, i.value), 'is_custom': False}
            for i in IntentName
            if i.value not in ('prompt_injection_attempt', 'unknown')
        ]
        custom = [
            {'id': str(ci.id), 'value': ci.name, 'label': ci.label, 'is_custom': True, 'keywords': ci.keywords}
            for ci in CustomIntent.objects.filter(organization=org, is_active=True)
        ]
        return Response(system + custom)

    # POST — create custom intent
    data = request.data
    name = (data.get('name') or '').strip().lower().replace(' ', '_')
    label = (data.get('label') or '').strip()
    keywords = [k.strip() for k in (data.get('keywords') or []) if str(k).strip()]

    if not name or not label:
        return Response({'error': 'name and label are required'}, status=status.HTTP_400_BAD_REQUEST)

    ci, created = CustomIntent.objects.get_or_create(
        organization=org,
        name=name,
        defaults={'label': label, 'keywords': keywords},
    )
    if not created:
        ci.label = label
        ci.keywords = keywords
        ci.is_active = True
        ci.save(update_fields=['label', 'keywords', 'is_active', 'updated_at'])

    return Response(
        {'id': str(ci.id), 'value': ci.name, 'label': ci.label, 'is_custom': True, 'keywords': ci.keywords},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def flow_intent_delete(request, intent_id):
    """Soft-delete (deactivate) a custom intent."""
    org = request.user.organization
    try:
        ci = CustomIntent.objects.get(id=intent_id, organization=org)
        ci.is_active = False
        ci.save(update_fields=['is_active', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)
    except CustomIntent.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
