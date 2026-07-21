import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone


class Plan(models.Model):
    PLAN_TYPES = [('pilot', 'Pilot'), ('base', 'Base'), ('pro', 'Pro'), ('enterprise', 'Enterprise')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    tipo = models.CharField(max_length=20, choices=PLAN_TYPES, default='base')
    price_cop = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    annual_price_cop = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    # ── Límites del plan ──
    max_channels = models.IntegerField(default=1)
    max_agents = models.IntegerField(default=1)
    max_conversations_month = models.IntegerField(default=500)
    max_products = models.IntegerField(default=0)  # 0 = ilimitado
    extra_conversation_price_cop = models.DecimalField(max_digits=10, decimal_places=0, default=0)

    trial_days = models.PositiveIntegerField(default=7)
    features = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    highlight = models.BooleanField(default=False)

    class Meta:
        db_table = 'plans'
        ordering = ['price_cop']

    def __str__(self):
        return self.name

    @property
    def is_unlimited_products(self) -> bool:
        return self.max_products == 0


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('trialing', 'Trialing'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='subscriptions'
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trialing')
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # ── Prueba gratis ──
    is_trial = models.BooleanField(default=False)
    trial_ends_at = models.DateTimeField(null=True, blank=True)

    # ── Ciclo de facturación actual ──
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    conversations_used = models.IntegerField(default=0)

    # ── Pay as you go (excedente sobre el cupo del plan) ──
    overage_conversations = models.PositiveIntegerField(default=0)
    overage_amount_cop = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    spend_ceiling_cop = models.DecimalField(max_digits=12, decimal_places=0, default=0)  # 0 = sin tope

    # ── Enlace con la pasarela de pago (uso futuro: Wompi / Bold) ──
    gateway = models.CharField(max_length=20, blank=True)
    gateway_customer_id = models.CharField(max_length=120, blank=True)
    gateway_subscription_id = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = 'subscriptions'
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.organization} · {self.plan}'

    # ── Estado / límites ─────────────────────────────────────────────
    @property
    def included_conversations(self) -> int:
        return self.plan.max_conversations_month

    @property
    def conversations_remaining(self) -> int:
        return max(self.included_conversations - self.conversations_used, 0)

    @property
    def in_payg(self) -> bool:
        """True cuando ya se agotó el cupo incluido del ciclo."""
        return bool(self.included_conversations) and self.conversations_used >= self.included_conversations

    @property
    def is_trial_active(self) -> bool:
        if not self.is_trial or self.trial_ends_at is None:
            return False
        return timezone.now() < self.trial_ends_at

    @property
    def spend_ceiling_reached(self) -> bool:
        if not self.spend_ceiling_cop:
            return False
        return self.overage_amount_cop >= self.spend_ceiling_cop

    # ── Mutadores (la medición atómica se cablea en el paso siguiente) ─
    def register_conversation(self, *, count: int = 1) -> None:
        """
        Registra `count` conversaciones del ciclo y acumula el excedente (PAYG)
        cuando se pasa del cupo. NO cobra ni corta: solo lleva la cuenta.

        El caller DEBE envolver esto en transaction.atomic() + select_for_update()
        para evitar doble conteo bajo concurrencia (se hace en el paso de medición).
        """
        if count <= 0:
            return
        included = self.included_conversations
        before = self.conversations_used
        self.conversations_used = before + count

        # Solo las unidades que caen por encima del cupo generan excedente.
        over_units = self.conversations_used - max(before, included)
        if included and over_units > 0 and not self.is_trial:
            price = self.plan.extra_conversation_price_cop or Decimal('0')
            self.overage_conversations += over_units
            self.overage_amount_cop = (self.overage_amount_cop or Decimal('0')) + price * over_units

    def reset_cycle(self, *, period_start=None, period_end=None) -> None:
        """Reinicia los contadores del ciclo (tarea mensual)."""
        self.conversations_used = 0
        self.overage_conversations = 0
        self.overage_amount_cop = Decimal('0')
        if period_start is not None:
            self.period_start = period_start
        if period_end is not None:
            self.period_end = period_end
