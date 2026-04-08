import re
from rest_framework import serializers
from .models import KBArticle, KBDocument

# Patterns that encourage redirecting users away from the chat.
# Articles containing these should be rewritten to include the info directly.
_REDIRECT_PATTERNS = re.compile(
    r'visita\s+(nuestra\s+)?p[aá]gina\s+web'
    r'|ll[aá]ma(nos)?\s+al?\s+n[uú]mero'
    r'|ac[eé]rc(ate|ese)\s+a\s+(la\s+)?oficina'
    r'|ingresa\s+a\s+www\.'
    r'|consulta\s+en\s+www\.'
    r'|www\.[a-z0-9\-]+\.(co|com|org)',
    re.IGNORECASE,
)


class KBArticleSerializer(serializers.ModelSerializer):
    redirect_warning = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = KBArticle
        fields = [
            'id', 'title', 'content', 'category', 'purpose', 'tags',
            'status', 'visits', 'created_at', 'updated_at', 'redirect_warning',
        ]
        read_only_fields = ['id', 'visits', 'created_at', 'updated_at', 'redirect_warning']

    def get_redirect_warning(self, obj: KBArticle) -> str | None:
        if _REDIRECT_PATTERNS.search(obj.content or ''):
            return (
                'Este artículo contiene frases que redirigen al usuario fuera del chat '
                '(ej. "visita nuestra página web", "llama al número", URLs). '
                'Reescríbelo para que el agente pueda responder directamente aquí.'
            )
        return None


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
