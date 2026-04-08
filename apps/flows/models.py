import uuid
from django.db import models


class Flow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='flows'
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    nodes = models.JSONField(default=list)
    edges = models.JSONField(default=list)
    trigger = models.CharField(max_length=100, blank=True)  # intent, keyword, channel
    channel = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'flows'
        ordering = ['-updated_at']


class CustomIntent(models.Model):
    """
    Org-specific intent defined by keywords.
    Extends the system IntentName enum with business-specific triggers.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='custom_intents'
    )
    name = models.SlugField(max_length=80)       # e.g. "cotizar_material"
    label = models.CharField(max_length=120)     # "Cotizar material"
    keywords = models.JSONField(default=list)    # ["cotizar", "presupuesto de material"]
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'flows_custom_intents'
        unique_together = [('organization', 'name')]
        ordering = ['label']

    def __str__(self) -> str:
        return f'{self.label} ({self.name})'
