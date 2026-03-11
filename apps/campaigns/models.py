import uuid
from django.db import models


class Template(models.Model):
    TYPE_CHOICES = [
        ('marketing', 'Marketing'),
        ('utility', 'Utility'),
        ('authentication', 'Authentication'),
    ]
    STATUS_CHOICES = [('draft', 'Draft'), ('approved', 'Approved'), ('rejected', 'Rejected')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='templates'
    )
    name = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TYPE_CHOICES)
    content = models.TextField()
    variables = models.JSONField(default=list, blank=True)
    channel = models.CharField(max_length=20, default='whatsapp')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    external_id = models.CharField(max_length=200, blank=True)  # WhatsApp template ID
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'templates'
        ordering = ['-created_at']


class Campaign(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='campaigns'
    )
    template = models.ForeignKey(Template, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    channel = models.CharField(max_length=20, default='whatsapp')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    target_filter = models.JSONField(default=dict, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    total_recipients = models.PositiveIntegerField(default=0)
    delivered = models.PositiveIntegerField(default=0)
    read = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'campaigns'
        ordering = ['-created_at']
