from django.contrib import admin
from .models import Conversation, Message, TimelineEvent, QAScore


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ['id', 'role', 'content', 'timestamp']
    fields = ['role', 'content', 'timestamp']
    max_num = 50
    ordering = ['timestamp']


class TimelineInline(admin.TabularInline):
    model = TimelineEvent
    extra = 0
    readonly_fields = ['tipo', 'descripcion', 'timestamp']
    fields = ['tipo', 'descripcion', 'timestamp']


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        'short_id', 'canal', 'estado', 'sentimiento', 'organization',
        'contact_display', 'assigned_agent', 'updated_at',
    ]
    list_filter = ['canal', 'estado', 'sentimiento', 'organization']
    search_fields = ['id', 'contact__nombre', 'contact__apellido', 'intent']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [MessageInline, TimelineInline]
    date_hierarchy = 'created_at'

    def short_id(self, obj):
        return str(obj.id)[:8] + '...'
    short_id.short_description = 'ID'

    def contact_display(self, obj):
        if obj.contact:
            return f'{obj.contact.nombre} {obj.contact.apellido}'
        return '-'
    contact_display.short_description = 'Contact'


@admin.register(QAScore)
class QAScoreAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'score', 'created_at']
    list_filter = ['score']
    readonly_fields = ['id', 'created_at']
