from django.contrib import admin
from .models import ChannelConfig


@admin.register(ChannelConfig)
class ChannelConfigAdmin(admin.ModelAdmin):
    list_display = ['organization', 'channel', 'is_active', 'webhook_url', 'created_at']
    list_filter = ['channel', 'is_active']
    search_fields = ['organization__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    # Credentials field hidden from admin for security
    exclude = ['credentials']
