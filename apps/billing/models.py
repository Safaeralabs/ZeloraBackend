import uuid
from django.db import models


class Plan(models.Model):
    PLAN_TYPES = [('pilot', 'Pilot'), ('base', 'Base'), ('pro', 'Pro'), ('enterprise', 'Enterprise')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    tipo = models.CharField(max_length=20, choices=PLAN_TYPES, default='base')
    price_cop = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_channels = models.IntegerField(default=1)
    max_agents = models.IntegerField(default=1)
    max_conversations_month = models.IntegerField(default=500)
    extra_conversation_price_cop = models.DecimalField(max_digits=10, decimal_places=0, default=0)
    features = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    highlight = models.BooleanField(default=False)

    class Meta:
        db_table = 'plans'
        ordering = ['price_cop']


class Subscription(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('cancelled', 'Cancelled'), ('past_due', 'Past Due')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='subscriptions'
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    conversations_used = models.IntegerField(default=0)

    class Meta:
        db_table = 'subscriptions'
        ordering = ['-started_at']
