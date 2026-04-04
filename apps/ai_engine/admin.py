from django.contrib import admin
from .models import AIAgent, AITask, AIInsight, AIPerformanceLog, SalesAgentLog


@admin.register(AITask)
class AITaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'task_type', 'status', 'priority', 'progress_pct', 'organization', 'created_at']
    list_filter = ['status', 'task_type', 'priority']
    search_fields = ['name']
    readonly_fields = ['id', 'celery_task_id', 'created_at', 'started_at', 'completed_at']


@admin.register(AIInsight)
class AIInsightAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'severity', 'is_read', 'organization', 'generated_at']
    list_filter = ['category', 'severity', 'is_read']
    search_fields = ['title', 'description']
    readonly_fields = ['id', 'generated_at']


@admin.register(AIPerformanceLog)
class AIPerformanceLogAdmin(admin.ModelAdmin):
    list_display = ['organization', 'date', 'model_name', 'total_calls', 'bot_resolution_rate']
    list_filter = ['model_name', 'organization']
    date_hierarchy = 'date'


@admin.register(SalesAgentLog)
class SalesAgentLogAdmin(admin.ModelAdmin):
    list_display = ['stage', 'decision', 'confidence', 'handoff_needed', 'organization', 'created_at']
    list_filter = ['stage', 'decision', 'handoff_needed', 'organization']
    readonly_fields = ['id', 'products_shown', 'recommended_actions', 'context_used', 'created_at']


@admin.register(AIAgent)
class AIAgentAdmin(admin.ModelAdmin):
    list_display = ['name', 'agent_type', 'provider', 'model', 'is_active', 'organization', 'created_at']
    list_filter = ['agent_type', 'provider', 'is_active']
    search_fields = ['name', 'system_prompt']
    readonly_fields = ['id', 'created_at', 'updated_at']
