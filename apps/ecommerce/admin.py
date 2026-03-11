from django.contrib import admin
from .models import Product, ProductVariant, Order, InventoryMovement


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


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['short_id', 'customer_name', 'channel', 'status', 'total', 'currency', 'organization', 'created_at']
    list_filter = ['status', 'channel', 'organization']
    search_fields = ['customer_name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'

    def short_id(self, obj):
        return str(obj.id)[:8]
    short_id.short_description = 'ID'


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ['variant', 'type', 'quantity', 'reason', 'actor', 'created_at']
    list_filter = ['type', 'organization']
    readonly_fields = ['id', 'created_at']
