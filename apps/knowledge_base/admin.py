from django.contrib import admin
from .models import KBArticle, KBDocument


@admin.register(KBArticle)
class KBArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'status', 'visits', 'organization', 'updated_at']
    list_filter = ['status', 'category', 'organization']
    search_fields = ['title', 'content']
    readonly_fields = ['id', 'visits', 'created_at', 'updated_at']


@admin.register(KBDocument)
class KBDocumentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'organization', 'mime_type', 'processed', 'uploaded_at']
    list_filter = ['processed', 'organization']
    search_fields = ['filename']
    readonly_fields = ['id', 'uploaded_at']
