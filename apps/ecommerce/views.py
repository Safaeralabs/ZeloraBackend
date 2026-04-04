from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Product, Order, InventoryMovement
from .serializers import ProductSerializer, OrderSerializer, InventoryMovementSerializer
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin


class ProductViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = ProductSerializer
    filterset_fields = ['status', 'category', 'is_active', 'offer_type', 'price_type']
    search_fields = ['title', 'brand', 'category', 'description', 'fulfillment_notes']

    def get_queryset(self):
        return Product.objects.filter(
            organization=self.request.user.organization
        ).prefetch_related('variants')

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)

    @action(
        detail=False,
        methods=['get'],
        url_path=r'public/(?P<org_slug>[^/.]+)',
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def public_list(self, request, org_slug=None):
        from apps.accounts.models import Organization

        organization = Organization.objects.filter(slug=org_slug, is_active=True).first()
        if organization is None:
            return Response({'detail': 'Marca no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        products = Product.objects.filter(
            organization=organization,
            is_active=True,
            status='active',
        ).prefetch_related('variants').order_by('-updated_at', '-created_at')[:12]

        return Response(ProductSerializer(products, many=True).data)

    @action(
        detail=False,
        methods=['get'],
        url_path=r'public/(?P<org_slug>[^/.]+)/(?P<product_id>[^/.]+)',
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def public_detail(self, request, org_slug=None, product_id=None):
        from apps.accounts.models import Organization

        organization = Organization.objects.filter(slug=org_slug, is_active=True).first()
        if organization is None:
            return Response({'detail': 'Marca no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        product = Product.objects.filter(
            organization=organization,
            id=product_id,
            is_active=True,
            status='active',
        ).prefetch_related('variants').first()
        if product is None:
            return Response({'detail': 'Producto no disponible.'}, status=status.HTTP_404_NOT_FOUND)

        return Response(ProductSerializer(product).data)


class OrderViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = OrderSerializer
    filterset_fields = ['status', 'channel', 'order_kind']
    search_fields = ['customer_name', 'notes', 'service_location']

    def get_queryset(self):
        return Order.objects.filter(organization=self.request.user.organization)

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)

    @action(detail=True, methods=['post'])
    def ship(self, request, pk=None):
        order = self.get_object()
        if order.status not in ('paid', 'processing'):
            return Response(
                {'error': f'Cannot ship order in status {order.status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from django.utils import timezone
        order.status = 'shipped'
        order.save(update_fields=['status', 'updated_at'])
        return Response({
            'id': str(order.id),
            'status': order.status,
            'updated_at': order.updated_at.isoformat(),
        })

    @action(detail=False, methods=['post'], url_path='inventory/reserve')
    def reserve_inventory(self, request):
        order_id = request.data.get('order_id')
        items = request.data.get('items', [])
        # Simulate reservation
        reservation_id = f'res_{order_id[:8]}' if order_id else 'res_manual'
        return Response({'success': True, 'reservation_id': reservation_id})


class InventoryMovementViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = InventoryMovementSerializer
    filterset_fields = ['type']

    def get_queryset(self):
        return InventoryMovement.objects.filter(organization=self.request.user.organization)
