from rest_framework import serializers
from .models import AITask, AIInsight, AIPerformanceLog


class AITaskSerializer(serializers.ModelSerializer):
    created_by_nombre = serializers.CharField(source='created_by.full_name', read_only=True)
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = AITask
        fields = [
            'id', 'name', 'description', 'task_type', 'status', 'priority',
            'celery_task_id', 'input_data', 'result', 'error', 'progress_pct',
            'created_by_nombre', 'duration_seconds',
            'created_at', 'started_at', 'completed_at',
        ]
        read_only_fields = [
            'id', 'celery_task_id', 'result', 'error', 'progress_pct',
            'status', 'created_at', 'started_at', 'completed_at',
        ]

    def get_duration_seconds(self, obj):
        if obj.started_at and obj.completed_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        return None


class AIInsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIInsight
        fields = [
            'id', 'category', 'severity', 'title', 'description',
            'metric_value', 'metric_delta', 'action_suggested',
            'is_read', 'generated_at', 'expires_at',
        ]
        read_only_fields = ['id', 'generated_at']


class AIPerformanceLogSerializer(serializers.ModelSerializer):
    success_rate = serializers.SerializerMethodField()

    class Meta:
        model = AIPerformanceLog
        fields = [
            'id', 'date', 'model_name', 'total_calls', 'successful_calls',
            'failed_calls', 'avg_latency_ms', 'total_tokens_in', 'total_tokens_out',
            'estimated_cost_usd', 'bot_resolution_rate', 'avg_confidence', 'success_rate',
        ]

    def get_success_rate(self, obj):
        if obj.total_calls:
            return round(obj.successful_calls / obj.total_calls * 100, 1)
        return 0.0
