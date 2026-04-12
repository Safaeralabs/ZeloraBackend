"""
Conversations models — Conversation, Message, TimelineEvent, QAScore.
"""
import uuid
from django.db import models
from django.conf import settings


class Conversation(models.Model):
    CHANNEL_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('instagram', 'Instagram'),
        ('web', 'Web Chat'),
        ('tiktok', 'TikTok'),
        ('email', 'Email'),
        ('telegram', 'Telegram'),
    ]
    STATUS_CHOICES = [
        ('nuevo', 'Nuevo'),
        ('en_proceso', 'En Proceso'),
        ('escalado', 'Escalado'),
        ('resuelto', 'Resuelto'),
    ]
    SENTIMENT_CHOICES = [
        ('positivo', 'Positivo'),
        ('neutro', 'Neutro'),
        ('negativo', 'Negativo'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='conversations'
    )
    contact = models.ForeignKey(
        'accounts.Contact', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='conversations',
    )
    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_conversations',
    )

    # Channel & Status
    canal = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='web')
    estado = models.CharField(max_length=20, choices=STATUS_CHOICES, default='nuevo')

    # AI metadata
    intent = models.CharField(max_length=150, blank=True)
    sentimiento = models.CharField(max_length=20, choices=SENTIMENT_CHOICES, default='neutro')

    # L5: Commercial outcome tracking for learning feedback
    commercial_outcome = models.CharField(
        max_length=20,
        choices=[
            ('browsing', 'Browsing only'),
            ('abandoned', 'Abandoned'),
            ('purchased', 'Purchased'),
        ],
        null=True,
        blank=True,
        db_index=True,
        help_text='Whether conversation resulted in a purchase order'
    )

    # External reference (WhatsApp/Instagram thread ID)
    external_id = models.CharField(max_length=300, blank=True, db_index=True)

    # Extra data
    metadata = models.JSONField(default=dict, blank=True)

    # SLA
    sla_deadline = models.DateTimeField(null=True, blank=True)

    # Timestamps
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'conversations'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['organization', 'estado']),
            models.Index(fields=['organization', 'canal']),
            models.Index(fields=['organization', '-updated_at']),
            models.Index(fields=['organization', 'assigned_agent']),
        ]

    def __str__(self):
        contact_name = str(self.contact) if self.contact else 'Unknown'
        return f'{self.canal} | {contact_name} | {self.estado} ({str(self.id)[:8]})'


class Message(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('bot', 'Bot'),
        ('agent', 'Agent'),
        ('system', 'System'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()

    # Media attachment
    media_url = models.URLField(blank=True, max_length=2000)
    media_type = models.CharField(max_length=50, blank=True)  # image/png, audio/ogg, etc.

    # External platform message ID (for deduplication)
    external_id = models.CharField(max_length=300, blank=True, db_index=True)

    # Extra data (wa_id, delivery status, etc.)
    metadata = models.JSONField(default=dict, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'messages'
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['conversation', 'timestamp']),
            models.Index(fields=['conversation', 'role']),
        ]

    def __str__(self):
        return f'[{self.role}] {self.content[:80]}'


class TimelineEvent(models.Model):
    TIPO_CHOICES = [
        ('bot_start', 'Bot Start'),
        ('intent_detected', 'Intent Detected'),
        ('escalated', 'Escalated'),
        ('agent_reply', 'Agent Replied'),
        ('resolved', 'Resolved'),
        ('note', 'Note Added'),
        ('handoff', 'Handoff'),
        ('channel_change', 'Channel Change'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='timeline'
    )
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES)
    descripcion = models.TextField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'timeline_events'
        ordering = ['timestamp']

    def __str__(self):
        return f'{self.tipo}: {self.descripcion[:80]}'


class QAScore(models.Model):
    """Automated quality assurance score for a resolved conversation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.OneToOneField(
        Conversation, on_delete=models.CASCADE, related_name='qa_score'
    )
    score = models.IntegerField(help_text='0–100 QA score')
    feedback = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(auto_now_add=True)

    # Dimension breakdown (optional, for detailed reporting)
    response_time_score = models.IntegerField(default=0)
    sentiment_score = models.IntegerField(default=0)
    resolution_score = models.IntegerField(default=0)
    coverage_score = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'qa_scores'

    def __str__(self):
        return f'QA {self.score}/100 for {str(self.conversation_id)[:8]}'
