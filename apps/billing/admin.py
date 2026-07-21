from django.contrib import admin
from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'tipo', 'price_cop', 'annual_price_cop',
                    'max_conversations_month', 'max_agents', 'max_products',
                    'extra_conversation_price_cop', 'is_active', 'highlight']
    list_filter = ['tipo', 'is_active', 'highlight']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['organization', 'plan', 'status', 'is_trial', 'trial_ends_at',
                    'conversations_used', 'overage_conversations', 'overage_amount_cop',
                    'period_end']
    list_filter = ['status', 'is_trial', 'plan']
    search_fields = ['organization__name']
    readonly_fields = ['id', 'started_at']
