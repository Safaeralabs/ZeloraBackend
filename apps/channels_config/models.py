import uuid
from django.db import models


class ChannelConfig(models.Model):
    CHANNEL_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('instagram', 'Instagram'),
        ('web', 'Web Chat'),
        ('tiktok', 'TikTok'),
        ('email', 'Email'),
        ('telegram', 'Telegram'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='channel_configs'
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    is_active = models.BooleanField(default=False)
    credentials = models.JSONField(default=dict, blank=True)  # Encrypted in production
    webhook_url = models.URLField(blank=True)
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'channel_configs'
        unique_together = ['organization', 'channel']
