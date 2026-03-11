from django.contrib import admin
from .models import CollabNote, AgentPerformanceSnapshot


@admin.register(CollabNote)
class CollabNoteAdmin(admin.ModelAdmin):
    list_display = ['note_type', 'author', 'conversation', 'is_pinned', 'organization', 'created_at']
    list_filter = ['note_type', 'is_pinned', 'organization']
    search_fields = ['content']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(AgentPerformanceSnapshot)
class AgentPerformanceSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        'agent', 'date', 'conversations_handled', 'conversations_resolved',
        'csat_score', 'escalations_caused',
    ]
    list_filter = ['organization', 'date']
    search_fields = ['agent__nombre', 'agent__email']
    readonly_fields = ['id']
    date_hierarchy = 'date'
