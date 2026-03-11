from django.contrib import admin
from .models import AIMemoryEntry, AITask, AIInsight, AIPerformanceLog


@admin.register(AIMemoryEntry)
class AIMemoryEntryAdmin(admin.ModelAdmin):
    list_display = ['key', 'memory_type', 'confidence', 'is_active', 'organization', 'updated_at']
    list_filter = ['memory_type', 'is_active', 'organization']
    search_fields = ['key', 'value']
    readonly_fields = ['id', 'created_at', 'updated_at']


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
