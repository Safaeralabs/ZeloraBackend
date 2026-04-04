from django.contrib import admin
from .models import RouterDecisionLog


@admin.register(RouterDecisionLog)
class RouterDecisionLogAdmin(admin.ModelAdmin):
    list_display = ['intent', 'route_type', 'risk_level', 'confidence', 'agent', 'organization', 'created_at']
    list_filter = ['intent', 'route_type', 'risk_level', 'organization']
    search_fields = ['decision_id', 'intent']
    readonly_fields = ['id', 'decision_id', 'full_decision', 'created_at']
