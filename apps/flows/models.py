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
