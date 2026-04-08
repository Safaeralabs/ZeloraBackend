from rest_framework import serializers
from .models import Product, ProductVariant, Order, InventoryMovement


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


class OrderSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        order_kind = attrs.get('order_kind', getattr(self.instance, 'order_kind', 'purchase'))
        scheduled_for = attrs.get('scheduled_for', getattr(self.instance, 'scheduled_for', None))
        service_location = attrs.get('service_location', getattr(self.instance, 'service_location', ''))

        if order_kind in ('booking', 'quote_request') and not attrs.get('items', getattr(self.instance, 'items', [])):
            raise serializers.ValidationError({'items': 'Bookings and quote requests require at least one line item.'})
        if order_kind == 'booking' and scheduled_for is None:
            raise serializers.ValidationError({'scheduled_for': 'Bookings require a scheduled date/time.'})
        if order_kind == 'booking' and not service_location:
            raise serializers.ValidationError({'service_location': 'Bookings require a service location or mode.'})
        return attrs

    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
