from django.contrib import admin
from .models import MetricsSnapshot


@admin.register(MetricsSnapshot)
class MetricsSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        'organization', 'date', 'canal', 'total_conversations',
        'resolved', 'escalated', 'csat_score', 'ai_handled',
    ]
    list_filter = ['canal', 'organization', 'date']
    readonly_fields = ['id', 'created_at']
    date_hierarchy = 'date'
