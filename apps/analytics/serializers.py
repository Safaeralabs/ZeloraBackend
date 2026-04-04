from rest_framework import serializers
from .models import MetricsSnapshot, LearningCandidate, DocumentExtractionCandidate


class MetricsSnapshotSerializer(serializers.ModelSerializer):
    resolution_rate = serializers.SerializerMethodField()
    escalation_rate = serializers.SerializerMethodField()
    ai_rate = serializers.SerializerMethodField()

    class Meta:
        model = MetricsSnapshot
        fields = [
            'id', 'date', 'canal', 'total_conversations', 'resolved', 'escalated',
            'avg_response_time_s', 'csat_score', 'ai_handled',
            'resolution_rate', 'escalation_rate', 'ai_rate',
        ]

    def get_resolution_rate(self, obj):
        if obj.total_conversations:
            return round(obj.resolved / obj.total_conversations * 100, 1)
        return 0.0

    def get_escalation_rate(self, obj):
        if obj.total_conversations:
            return round(obj.escalated / obj.total_conversations * 100, 1)
        return 0.0

    def get_ai_rate(self, obj):
        if obj.total_conversations:
            return round(obj.ai_handled / obj.total_conversations * 100, 1)
        return 0.0


class HistoricalImportUploadSerializer(serializers.Serializer):
    source_name = serializers.CharField(required=False, allow_blank=True, max_length=80)
    file = serializers.FileField()

    def validate_source_name(self, value):
        normalized = (value or '').strip().lower().replace(' ', '_')
        if not normalized:
            return 'historical_import'
        normalized = ''.join(char for char in normalized if char.isalnum() or char in {'_', '-'})
        return normalized[:80] or 'historical_import'

    def validate_file(self, value):
        name = getattr(value, 'name', '').lower()
        if not name.endswith('.jsonl'):
            raise serializers.ValidationError('El archivo debe ser .jsonl')
        if getattr(value, 'size', 0) > 20 * 1024 * 1024:
            raise serializers.ValidationError('El archivo supera el limite de 20 MB.')
        return value


class HistoricalImportKBSerializer(serializers.Serializer):
    source_name = serializers.CharField(max_length=80)


class LearningCandidateSerializer(serializers.ModelSerializer):
    suggested_destination = serializers.SerializerMethodField()

    class Meta:
        model = LearningCandidate
        fields = [
            'id', 'kind', 'status', 'title', 'source_question', 'proposed_answer',
            'confidence', 'evidence_count', 'metadata', 'approved_article', 'suggested_destination',
            'created_at', 'updated_at',
        ]

    def get_suggested_destination(self, obj):
        if obj.kind == 'objection':
            return 'kb_playbook'
        if obj.kind == 'winning_reply':
            return 'quick_reply'
        return 'kb_article'


class LearningGenerationSerializer(serializers.Serializer):
    limit = serializers.IntegerField(required=False, min_value=10, max_value=500, default=150)


class DocumentExtractionCandidateSerializer(serializers.ModelSerializer):
    source_document_name = serializers.CharField(source='source_document.filename', read_only=True)
    suggested_destination = serializers.SerializerMethodField()

    class Meta:
        model = DocumentExtractionCandidate
        fields = [
            'id', 'kind', 'status', 'title', 'body', 'confidence', 'metadata',
            'source_document', 'source_document_name', 'approved_article', 'approved_product', 'suggested_destination',
            'created_at', 'updated_at',
        ]

    def get_suggested_destination(self, obj):
        return {
            'service': 'catalog_service',
            'pricing_rule': 'kb_pricing',
            'policy': 'kb_policy',
            'flow_hint': 'flow_hint',
        }.get(obj.kind, 'kb_article')


class DocumentExtractionGenerationSerializer(serializers.Serializer):
    document_id = serializers.UUIDField(required=False)


class CandidateBatchActionSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
