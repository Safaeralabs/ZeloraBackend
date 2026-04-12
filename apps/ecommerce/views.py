import os
import uuid

from django.core.files.storage import default_storage
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Product, Order, InventoryMovement, Promotion, ProductRelation
from .serializers import (
    ProductSerializer,
    PublicProductSerializer,
    OrderSerializer,
    InventoryMovementSerializer,
    PromotionSerializer,
    ProductRelationSerializer,
)
from .upload_security import validate_product_image_upload
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin


class ProductViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = ProductSerializer
    filterset_fields = [
        'status',
        'category',
        'subcategory',  # P1.1
        'is_active',
        'offer_type',
        'price_type',
        'style',  # P1.1
        'formality',  # P1.1
        'target_audience',  # P1.1
        'is_bestseller',  # P1.1
    ]
    search_fields = ['title', 'brand', 'category', 'description', 'fulfillment_notes']

    def get_queryset(self):
        return Product.objects.filter(
            organization=self.request.user.organization
        ).prefetch_related('variants')

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)

    @action(detail=False, methods=['post'], url_path='upload-image', parser_classes=[MultiPartParser, FormParser])
    def upload_image(self, request):
        uploaded_file = request.FILES.get('file')
        validate_product_image_upload(uploaded_file)

        extension = os.path.splitext(uploaded_file.name)[1].lower() or '.jpg'
        organization_id = str(request.user.organization_id)
        filename = f'{uuid.uuid4().hex}{extension}'
        storage_path = f'products/{organization_id}/{filename}'
        stored_path = default_storage.save(storage_path, uploaded_file)
        public_url = request.build_absolute_uri(default_storage.url(stored_path))

        return Response(
            {
                'url': public_url,
                'path': stored_path,
                'name': os.path.basename(stored_path),
                'size': uploaded_file.size,
                'content_type': uploaded_file.content_type,
            },
            status=status.HTTP_201_CREATED,
        )

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

        return Response(PublicProductSerializer(products, many=True).data)

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

        return Response(PublicProductSerializer(product).data)


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


# P1.1: New ViewSets for Promotion and ProductRelation


class PromotionViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    """P1.1: ViewSet for managing promotions and discounts."""

    permission_classes = [IsOrganizationMember]
    serializer_class = PromotionSerializer
    filterset_fields = ['applies_to', 'discount_type', 'is_active']
    search_fields = ['title', 'description']

    def get_queryset(self):
        return Promotion.objects.filter(organization=self.request.user.organization)

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class ProductRelationViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    """P1.1: ViewSet for managing product relationships and graphs."""

    permission_classes = [IsOrganizationMember]
    serializer_class = ProductRelationSerializer
    filterset_fields = ['relation_type', 'source_product', 'target_product']

    def get_queryset(self):
        return ProductRelation.objects.filter(organization=self.request.user.organization).select_related(
            'source_product', 'target_product'
        )

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)
