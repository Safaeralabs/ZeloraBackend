import os
import uuid

from django.core.files.storage import default_storage
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Product, Order, OrderEvent, InventoryMovement, Promotion, ProductRelation
from .serializers import (
    ProductSerializer,
    PublicProductSerializer,
    OrderSerializer,
    OrderDetailSerializer,
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
        product = serializer.save(organization=self.request.user.organization)
        self._refresh_embedding(product)

    def perform_update(self, serializer):
        product = serializer.save()
        self._refresh_embedding(product)

    @staticmethod
    def _refresh_embedding(product):
        """Best-effort embedding so the sales agent can find this product semantically."""
        try:
            from django.conf import settings
            if not settings.OPENAI_API_KEY or not getattr(settings, 'ENABLE_REAL_AI', False):
                return
            from apps.ai_engine.sales.catalog import CatalogService
            from apps.ai_engine.sales_kb import _embed_query
            vector = _embed_query(CatalogService.build_embedding_text(product), str(product.organization_id))
            if vector:
                product.embedding_vector = vector
                product.save(update_fields=['embedding_vector', 'updated_at'])
        except Exception:
            pass  # embeddings are an enhancement, never block saving

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
    filterset_fields = ['status', 'channel', 'order_kind', 'payment_status', 'fulfillment_status']
    search_fields = ['customer_name', 'notes', 'service_location', 'tracking_number']
    ordering_fields = ['created_at', 'total', 'order_number']
    ordering = ['-created_at']

    def get_queryset(self):
        return (
            Order.objects.filter(organization=self.request.user.organization)
            .select_related('contact', 'created_by', 'conversation')
            .prefetch_related('line_items', 'line_items__product', 'line_items__variant', 'events')
        )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return OrderDetailSerializer
        return OrderSerializer

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            created_by=self.request.user,
        )

    def _transition(self, request, pk, valid_from, new_status, event_type, extra_fields=None):
        order = self.get_object()
        if order.status not in valid_from:
            return Response(
                {'error': f'Cannot transition from {order.status} to {new_status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = new_status
        update_fields = ['status', 'updated_at']
        if extra_fields:
            for field, value in extra_fields.items():
                setattr(order, field, value)
                update_fields.append(field)
        order.save(update_fields=update_fields)
        OrderEvent.objects.create(
            order=order, event_type=event_type, actor=request.user,
        )
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        return self._transition(
            request, pk,
            valid_from=('new',),
            new_status='paid',
            event_type='paid',
            extra_fields={'payment_status': 'paid'},
        )

    @action(detail=True, methods=['post'], url_path='mark-processing')
    def mark_processing(self, request, pk=None):
        return self._transition(
            request, pk,
            valid_from=('paid',),
            new_status='processing',
            event_type='processing',
        )

    @action(detail=True, methods=['post'], url_path='mark-shipped')
    def mark_shipped(self, request, pk=None):
        extra = {'fulfillment_status': 'fulfilled'}
        tracking = request.data.get('tracking_number', '')
        if tracking:
            extra['tracking_number'] = tracking
        return self._transition(
            request, pk,
            valid_from=('paid', 'processing'),
            new_status='shipped',
            event_type='shipped',
            extra_fields=extra,
        )

    @action(detail=True, methods=['post'], url_path='mark-delivered')
    def mark_delivered(self, request, pk=None):
        return self._transition(
            request, pk,
            valid_from=('shipped',),
            new_status='delivered',
            event_type='delivered',
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        return self._transition(
            request, pk,
            valid_from=('new', 'paid', 'processing'),
            new_status='cancelled',
            event_type='cancelled',
        )

    # Legacy action kept for backward compat
    @action(detail=True, methods=['post'])
    def ship(self, request, pk=None):
        return self.mark_shipped(request, pk)

    @action(detail=True, methods=['post'], url_path='add-note')
    def add_note(self, request, pk=None):
        order = self.get_object()
        message = request.data.get('message', '').strip()
        if not message:
            return Response({'error': 'Message is required'}, status=status.HTTP_400_BAD_REQUEST)
        event = OrderEvent.objects.create(
            order=order, event_type='note_added', message=message, actor=request.user,
        )
        from .serializers import OrderEventSerializer
        return Response(OrderEventSerializer(event).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='add-tag')
    def add_tag(self, request, pk=None):
        order = self.get_object()
        tag = request.data.get('tag', '').strip()
        if not tag:
            return Response({'error': 'Tag is required'}, status=status.HTTP_400_BAD_REQUEST)
        tags = list(order.tags or [])
        if tag not in tags:
            tags.append(tag)
            order.tags = tags
            order.save(update_fields=['tags', 'updated_at'])
            OrderEvent.objects.create(
                order=order, event_type='tag_added', message=tag, actor=request.user,
            )
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=['post'], url_path='remove-tag')
    def remove_tag(self, request, pk=None):
        order = self.get_object()
        tag = request.data.get('tag', '').strip()
        tags = list(order.tags or [])
        if tag in tags:
            tags.remove(tag)
            order.tags = tags
            order.save(update_fields=['tags', 'updated_at'])
            OrderEvent.objects.create(
                order=order, event_type='tag_removed', message=tag, actor=request.user,
            )
        return Response(OrderDetailSerializer(order).data)

    @action(detail=False, methods=['post'], url_path='inventory/reserve')
    def reserve_inventory(self, request):
        order_id = request.data.get('order_id')
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
    filterset_fields = ['scope', 'trigger_type', 'applies_to', 'discount_type', 'is_active']
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
