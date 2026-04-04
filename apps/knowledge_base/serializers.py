from rest_framework import serializers
from .models import KBArticle, KBDocument


class KBArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = KBArticle
        fields = [
            'id', 'title', 'content', 'category', 'purpose', 'tags',
            'status', 'visits', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'visits', 'created_at', 'updated_at']


class KBDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KBDocument
        fields = [
            'id', 'article', 'filename', 'file_size', 'mime_type',
            'processing_status', 'processed', 'extracted_text', 'uploaded_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'filename', 'file_size', 'mime_type',
            'processing_status', 'processed', 'extracted_text', 'uploaded_at', 'updated_at',
        ]
