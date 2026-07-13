from django.contrib import admin
from .models import Product, ProductVariant, Order, OrderLineItem, OrderEvent, InventoryMovement


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ['sku', 'name', 'price', 'cost', 'stock']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['title', 'brand', 'category', 'status', 'is_active', 'organization', 'updated_at']
    list_filter = ['status', 'is_active', 'category', 'organization']
    search_fields = ['title', 'brand', 'category']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [ProductVariantInline]


class OrderLineItemInline(admin.TabularInline):
    model = OrderLineItem
    extra = 0
    fields = ['title', 'sku', 'quantity', 'unit_price', 'discount', 'offer_type']
    readonly_fields = ['id']


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    fields = ['event_type', 'message', 'actor', 'created_at']
    readonly_fields = ['id', 'created_at']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['display_number', 'customer_name', 'channel', 'status', 'payment_status', 'total', 'currency', 'organization', 'created_at']
    list_filter = ['status', 'payment_status', 'fulfillment_status', 'channel', 'organization']
    search_fields = ['customer_name', 'tracking_number']
    readonly_fields = ['id', 'order_number', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    inlines = [OrderLineItemInline, OrderEventInline]

    def display_number(self, obj):
        return f'#{obj.order_number:04d}' if obj.order_number else str(obj.id)[:8]
    display_number.short_description = '#'


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ['variant', 'type', 'quantity', 'reason', 'actor', 'created_at']
    list_filter = ['type', 'organization']
    readonly_fields = ['id', 'created_at']
