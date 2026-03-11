from django.contrib import admin
from .models import Template, Campaign


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'tipo', 'channel', 'status', 'organization', 'created_at']
    list_filter = ['tipo', 'channel', 'status']
    search_fields = ['name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'channel', 'status', 'total_recipients',
        'delivered', 'failed', 'organization', 'created_at',
    ]
    list_filter = ['status', 'channel', 'organization']
    search_fields = ['name']
    readonly_fields = ['id', 'created_at', 'sent_at', 'delivered', 'read', 'failed']
