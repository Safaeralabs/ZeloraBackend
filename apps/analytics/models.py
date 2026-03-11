import uuid
from django.db import models


class MetricsSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='metrics'
    )
    date = models.DateField()
    canal = models.CharField(max_length=20)
    total_conversations = models.IntegerField(default=0)
    resolved = models.IntegerField(default=0)
    escalated = models.IntegerField(default=0)
    avg_response_time_s = models.FloatField(default=0)
    csat_score = models.FloatField(default=0)
    ai_handled = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'metrics_snapshots'
        unique_together = ['organization', 'date', 'canal']
        ordering = ['-date']
        indexes = [models.Index(fields=['organization', 'date'])]
