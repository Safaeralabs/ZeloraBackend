from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Plan, Subscription
from .serializers import PlanSerializer, SubscriptionSerializer
from core.permissions import IsOrganizationMember


class PlanViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PlanSerializer
    queryset = Plan.objects.filter(is_active=True)


class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        return Subscription.objects.filter(
            organization=self.request.user.organization
        ).select_related('plan')
