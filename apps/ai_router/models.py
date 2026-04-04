"""
RouterDecisionLog — persists every AI Router decision for auditability.
"""
import uuid
from django.db import models


class RouterDecisionLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='router_decisions'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation', on_delete=models.CASCADE, related_name='router_decisions'
    )
    message = models.ForeignKey(
        'conversations.Message', on_delete=models.CASCADE, related_name='router_decisions'
    )
    decision_id = models.CharField(max_length=100)
    intent = models.CharField(max_length=100)
    confidence = models.FloatField(default=0.0)
    risk_level = models.CharField(max_length=20)
    route_type = models.CharField(max_length=60)
    agent = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    post_actions = models.JSONField(default=list)
    full_decision = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'router_decision_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['conversation']),
            models.Index(fields=['intent']),
        ]

    def __str__(self):
        return f'[{self.route_type}] {self.intent} @ {str(self.conversation_id)[:8]}'
