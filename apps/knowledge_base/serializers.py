from rest_framework import serializers
from .models import KBArticle, KBDocument


class KBArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = KBArticle
        fields = [
            'id', 'title', 'content', 'category', 'tags',
            'status', 'visits', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'visits', 'created_at', 'updated_at']


class KBDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KBDocument
        fields = ['id', 'filename', 'file', 'file_size', 'mime_type', 'processed', 'uploaded_at']
        read_only_fields = ['id', 'processed', 'uploaded_at']
