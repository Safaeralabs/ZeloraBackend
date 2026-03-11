"""
Workspace models — Collaborative notes, agent performance, shared context panels.
Supports the AI Workspace > Collab & Performance tabs in the frontend.
"""
import uuid
from django.db import models
from django.conf import settings


class CollabNote(models.Model):
    """
    Shared notes/annotations that agents can attach to a conversation.
    Visible to all agents in the organization.
    """
    NOTE_TYPE_CHOICES = [
        ('note', 'Note'),
        ('escalation_reason', 'Escalation Reason'),
        ('resolution_note', 'Resolution Note'),
        ('handoff', 'Handoff'),
        ('warning', 'Warning'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='collab_notes'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation', on_delete=models.CASCADE,
        related_name='collab_notes', null=True, blank=True
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='authored_notes'
    )
    note_type = models.CharField(max_length=30, choices=NOTE_TYPE_CHOICES, default='note')
    content = models.TextField()
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'collab_notes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'conversation']),
        ]

    def __str__(self):
        return f'{self.note_type}: {self.content[:80]}'


class AgentPerformanceSnapshot(models.Model):
    """
    Daily performance snapshot per agent.
    Powers the AI Workspace > Performance dashboard.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='agent_performance'
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='performance_snapshots'
    )
    date = models.DateField()
    conversations_handled = models.PositiveIntegerField(default=0)
    conversations_resolved = models.PositiveIntegerField(default=0)
    avg_response_time_s = models.FloatField(default=0.0)
    avg_resolution_time_s = models.FloatField(default=0.0)
    escalations_caused = models.PositiveIntegerField(default=0)
    csat_score = models.FloatField(default=0.0)
    messages_sent = models.PositiveIntegerField(default=0)
    online_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'agent_performance_snapshots'
        unique_together = ['agent', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['organization', 'date']),
        ]
