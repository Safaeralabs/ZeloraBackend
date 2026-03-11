from django.contrib import admin
from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'tipo', 'price_cop', 'max_agents', 'is_active', 'highlight']
    list_filter = ['tipo', 'is_active']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['organization', 'plan', 'status', 'conversations_used', 'started_at', 'expires_at']
    list_filter = ['status', 'plan']
    search_fields = ['organization__name']
    readonly_fields = ['id', 'started_at']
