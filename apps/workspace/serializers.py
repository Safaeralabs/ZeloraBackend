from rest_framework import serializers
from .models import CollabNote, AgentPerformanceSnapshot


class CollabNoteSerializer(serializers.ModelSerializer):
    author_nombre = serializers.CharField(source='author.full_name', read_only=True)

    class Meta:
        model = CollabNote
        fields = [
            'id', 'conversation', 'note_type', 'content', 'is_pinned',
            'author_nombre', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AgentPerformanceSnapshotSerializer(serializers.ModelSerializer):
    agent_nombre = serializers.CharField(source='agent.full_name', read_only=True)
    resolution_rate = serializers.SerializerMethodField()

    class Meta:
        model = AgentPerformanceSnapshot
        fields = [
            'id', 'agent', 'agent_nombre', 'date',
            'conversations_handled', 'conversations_resolved',
            'avg_response_time_s', 'avg_resolution_time_s',
            'escalations_caused', 'csat_score', 'messages_sent',
            'online_minutes', 'resolution_rate',
        ]
        read_only_fields = ['id']

    def get_resolution_rate(self, obj):
        if obj.conversations_handled:
            return round(obj.conversations_resolved / obj.conversations_handled * 100, 1)
        return 0.0
