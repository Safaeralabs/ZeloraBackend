from rest_framework import serializers
from .models import MetricsSnapshot


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
