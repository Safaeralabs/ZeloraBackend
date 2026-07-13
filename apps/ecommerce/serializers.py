from django.db import transaction
from rest_framework import serializers
from .models import (
    Product, ProductVariant, Order, OrderLineItem, OrderEvent,
    InventoryMovement, Promotion, ProductRelation,
)


class ProductVariantSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        product = self.instance.product if self.instance else self.context.get('product')
        source_product = attrs.get('product') or product
        offer_type = getattr(source_product, 'offer_type', 'physical')
        stock = attrs.get('stock', getattr(self.instance, 'stock', 0))
        reserved = attrs.get('reserved', getattr(self.instance, 'reserved', 0))
        duration = attrs.get('duration_minutes', getattr(self.instance, 'duration_minutes', 0))
        capacity = attrs.get('capacity', getattr(self.instance, 'capacity', 0))

        if offer_type == 'service':
            attrs['stock'] = 0
            attrs['reserved'] = 0
            if duration <= 0:
                raise serializers.ValidationError({'duration_minutes': 'Services require a positive duration.'})
        if offer_type == 'physical':
            attrs['duration_minutes'] = 0
            attrs['capacity'] = 0
            if stock < 0 or reserved < 0:
                raise serializers.ValidationError('Stock values cannot be negative.')
        if offer_type == 'hybrid':
            if duration <= 0:
                raise serializers.ValidationError({'duration_minutes': 'Hybrid offers require a service duration.'})
            if stock < 0 or reserved < 0:
                raise serializers.ValidationError('Stock values cannot be negative.')
        if capacity < 0:
            raise serializers.ValidationError({'capacity': 'Capacity cannot be negative.'})
        if reserved > stock and offer_type in ('physical', 'hybrid'):
            raise serializers.ValidationError({'reserved': 'Reserved units cannot exceed stock.'})
        return attrs

    class Meta:
        model = ProductVariant
        fields = '__all__'
        read_only_fields = ['id']
        extra_kwargs = {
            'product': {'required': False},
        }


class ProductSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, required=False)

    def validate(self, attrs):
        offer_type = attrs.get('offer_type', getattr(self.instance, 'offer_type', 'physical'))
        requires_booking = attrs.get('requires_booking', getattr(self.instance, 'requires_booking', False))
        requires_shipping = attrs.get('requires_shipping', getattr(self.instance, 'requires_shipping', True))
        duration = attrs.get(
            'service_duration_minutes',
            getattr(self.instance, 'service_duration_minutes', 0),
        )
        capacity = attrs.get('capacity', getattr(self.instance, 'capacity', 0))
        service_mode = attrs.get('service_mode', getattr(self.instance, 'service_mode', 'not_applicable'))

        if offer_type == 'physical':
            attrs['requires_booking'] = False
            attrs['requires_shipping'] = True if 'requires_shipping' not in attrs else requires_shipping
            attrs['service_duration_minutes'] = 0
            attrs['capacity'] = 0
            attrs['service_mode'] = 'not_applicable'
        elif offer_type == 'service':
            attrs['requires_booking'] = True if 'requires_booking' not in attrs else requires_booking
            attrs['requires_shipping'] = False
            if duration <= 0:
                raise serializers.ValidationError({'service_duration_minutes': 'Services require a positive duration.'})
            if service_mode == 'not_applicable':
                raise serializers.ValidationError({'service_mode': 'Select how the service is delivered.'})
        elif offer_type == 'hybrid':
            attrs['requires_booking'] = True if 'requires_booking' not in attrs else requires_booking
            attrs['requires_shipping'] = True if 'requires_shipping' not in attrs else requires_shipping
            if duration <= 0:
                raise serializers.ValidationError({'service_duration_minutes': 'Hybrid offers require a positive service duration.'})

        if capacity < 0:
            raise serializers.ValidationError({'capacity': 'Capacity cannot be negative.'})

        images = attrs.get('images', getattr(self.instance, 'images', [])) or []
        if len(images) > 5:
            raise serializers.ValidationError({'images': 'A product can only have up to 5 images.'})
        for image in images:
            if not isinstance(image, str) or not image.strip():
                raise serializers.ValidationError({'images': 'Each product image must be a valid URL string.'})
            normalized_image = image.strip().lower()
            if normalized_image.startswith('data:') or normalized_image.startswith('javascript:'):
                raise serializers.ValidationError({'images': 'Inline or unsafe image sources are not allowed.'})

        variants = self.initial_data.get('variants') if hasattr(self, 'initial_data') else None
        if self.instance is None and not variants:
            raise serializers.ValidationError({'variants': 'At least one variant is required.'})
        if variants is not None:
            if not isinstance(variants, list) or len(variants) == 0:
                raise serializers.ValidationError({'variants': 'At least one variant is required.'})
            seen_skus: set[str] = set()
            for variant in variants:
                sku = str((variant or {}).get('sku', '')).strip().lower()
                if not sku:
                    continue
                if sku in seen_skus:
                    raise serializers.ValidationError({'variants': 'Variant SKUs must be unique within a product.'})
                seen_skus.add(sku)
        return attrs

    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

    def create(self, validated_data):
        variants_data = validated_data.pop('variants', [])
        product = Product.objects.create(**validated_data)
        self._save_variants(product, variants_data)
        return product

    def update(self, instance, validated_data):
        variants_data = validated_data.pop('variants', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if variants_data is not None:
            self._save_variants(instance, variants_data)
        return instance

    def _save_variants(self, product, variants_data):
        existing_by_id = {str(item.id): item for item in product.variants.all()}
        keep_ids: set[str] = set()

        for variant_data in variants_data:
            variant_id = str(variant_data.pop('id', '') or '')
            serializer = ProductVariantSerializer(
                instance=existing_by_id.get(variant_id) if variant_id else None,
                data=variant_data,
                partial=bool(variant_id),
                context={'product': product},
            )
            serializer.is_valid(raise_exception=True)
            variant = serializer.save(product=product)
            keep_ids.add(str(variant.id))

        for variant_id, variant in existing_by_id.items():
            if variant_id not in keep_ids:
                variant.delete()


class PublicProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'sku',
            'name',
            'price',
            'duration_minutes',
            'capacity',
            'delivery_mode',
        ]


class PublicProductSerializer(serializers.ModelSerializer):
    variants = PublicProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id',
            'title',
            'brand',
            'description',
            'category',
            'subcategory',  # P1.1
            'offer_type',
            'price_type',
            'service_mode',
            'requires_booking',
            'requires_shipping',
            'service_duration_minutes',
            'capacity',
            'fulfillment_notes',
            'attributes',
            'images',
            'tags',
            'occasion',  # P1.1
            'style',  # P1.1
            'color',  # P1.1
            'material',  # P1.1
            'fit',  # P1.1
            'formality',  # P1.1
            'target_audience',  # P1.1
            'is_bestseller',  # P1.1
            'status',
            'variants',
            'created_at',
            'updated_at',
        ]


class InventoryMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryMovement
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at']


class OrderLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLineItem
        fields = '__all__'
        read_only_fields = ['id']
        extra_kwargs = {'order': {'required': False}}


class OrderEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderEvent
        fields = ['id', 'event_type', 'message', 'actor', 'actor_name', 'metadata', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_actor_name(self, obj):
        if obj.actor:
            return f'{obj.actor.nombre} {obj.actor.apellido}'.strip() or obj.actor.email
        return ''


class OrderSerializer(serializers.ModelSerializer):
    line_items_data = serializers.ListField(child=serializers.DictField(), write_only=True, required=False)
    display_order_number = serializers.SerializerMethodField()
    conversation_id = serializers.UUIDField(source='conversation.id', read_only=True, allow_null=True)

    def get_display_order_number(self, obj):
        if obj.order_number:
            return f'#{obj.order_number:04d}'
        return f'#{str(obj.id)[:8]}'

    def validate(self, attrs):
        order_kind = attrs.get('order_kind', getattr(self.instance, 'order_kind', 'purchase'))
        scheduled_for = attrs.get('scheduled_for', getattr(self.instance, 'scheduled_for', None))
        service_location = attrs.get('service_location', getattr(self.instance, 'service_location', ''))
        line_items_data = attrs.get('line_items_data', [])
        items = attrs.get('items', getattr(self.instance, 'items', []))

        if self.instance is None and not line_items_data and not items:
            raise serializers.ValidationError({'line_items_data': 'At least one line item is required.'})
        if order_kind == 'booking' and scheduled_for is None:
            raise serializers.ValidationError({'scheduled_for': 'Bookings require a scheduled date/time.'})
        if order_kind == 'booking' and not service_location:
            raise serializers.ValidationError({'service_location': 'Bookings require a service location or mode.'})
        return attrs

    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'order_number', 'conversation_id', 'created_at', 'updated_at']

    @transaction.atomic
    def create(self, validated_data):
        line_items_data = validated_data.pop('line_items_data', [])
        org_id = validated_data['organization'].id if hasattr(validated_data.get('organization', None), 'id') else validated_data.get('organization_id')
        if not org_id:
            org_id = validated_data['organization']
        validated_data['order_number'] = Order.next_order_number(org_id)

        order = Order.objects.create(**validated_data)

        if line_items_data:
            self._create_line_items(order, line_items_data)
            self._sync_financials(order)

        OrderEvent.objects.create(
            order=order,
            event_type='created',
            message='Pedido creado',
            actor=self.context.get('request', None) and self.context['request'].user,
        )
        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        line_items_data = validated_data.pop('line_items_data', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if line_items_data is not None:
            instance.line_items.all().delete()
            self._create_line_items(instance, line_items_data)
            self._sync_financials(instance)

        return instance

    def _create_line_items(self, order, items_data):
        items_json = []
        for item in items_data:
            li = OrderLineItem.objects.create(
                order=order,
                product_id=item.get('product_id'),
                variant_id=item.get('variant_id'),
                title=item.get('title', ''),
                sku=item.get('sku', ''),
                quantity=item.get('quantity', 1),
                unit_price=item.get('unit_price', 0),
                discount=item.get('discount', 0),
                tax=item.get('tax', 0),
                offer_type=item.get('offer_type', 'physical'),
                properties=item.get('properties', {}),
            )
            items_json.append({
                'sku': li.sku,
                'qty': li.quantity,
                'unitPrice': float(li.unit_price),
                'title': li.title,
                'offerType': li.offer_type,
            })
        order.items = items_json
        order.save(update_fields=['items'])

    def _sync_financials(self, order):
        from decimal import Decimal
        line_items = order.line_items.all()
        subtotal = sum((li.unit_price * li.quantity) - li.discount for li in line_items)
        tax = sum(li.tax for li in line_items)
        order.subtotal = subtotal
        order.tax_amount = tax
        order.total = subtotal - order.discount_total + tax + order.shipping_cost
        order.save(update_fields=['subtotal', 'tax_amount', 'total'])


class OrderDetailSerializer(OrderSerializer):
    line_items = OrderLineItemSerializer(many=True, read_only=True)
    events = OrderEventSerializer(many=True, read_only=True)
    contact_name = serializers.SerializerMethodField()

    class Meta(OrderSerializer.Meta):
        pass

    def get_contact_name(self, obj):
        if obj.contact:
            return f'{obj.contact.nombre} {obj.contact.apellido}'.strip()
        return obj.customer_name


class PromotionSerializer(serializers.ModelSerializer):
    """P1.1: Promotion serializer for managing discounts and offers."""

    def validate(self, attrs):
        trigger_type = attrs.get('trigger_type', getattr(self.instance, 'trigger_type', 'automatic'))
        code = str(attrs.get('code', getattr(self.instance, 'code', '')) or '').strip()
        scope = attrs.get('scope', getattr(self.instance, 'scope', 'product'))
        discount_type = attrs.get('discount_type', getattr(self.instance, 'discount_type', 'percentage'))
        buy_x = int(attrs.get('buy_x_qty', getattr(self.instance, 'buy_x_qty', 0)) or 0)
        get_y = int(attrs.get('get_y_qty', getattr(self.instance, 'get_y_qty', 0)) or 0)

        if trigger_type == 'code' and not code:
            raise serializers.ValidationError({'code': 'Discount code is required when trigger_type=code.'})
        if trigger_type != 'code':
            attrs['code'] = ''
        if scope == 'shipping' and discount_type not in ('free_shipping', 'fixed_amount', 'percentage'):
            raise serializers.ValidationError({'discount_type': 'Shipping scope only supports free_shipping, fixed_amount, or percentage.'})
        if discount_type == 'bundle' and (buy_x <= 0 or get_y <= 0):
            raise serializers.ValidationError({'buy_x_qty': 'Bundle promotions require buy_x_qty and get_y_qty greater than 0.'})
        return attrs

    class Meta:
        model = Promotion
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class ProductRelationSerializer(serializers.ModelSerializer):
    """P1.1: ProductRelation serializer for managing product graphs."""

    class Meta:
        model = ProductRelation
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at']
