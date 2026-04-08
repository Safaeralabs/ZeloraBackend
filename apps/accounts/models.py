"""
Accounts models — Organization, User (Agent), Contact.

Organization is defined here (not in a separate app) to avoid circular imports
since User has a FK to Organization.
"""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


# ─── Organization ──────────────────────────────────────────────────────────────

class Organization(models.Model):
    PLAN_CHOICES = [
        ('pilot', 'Pilot'),
        ('basic', 'Basic'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    industry = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='Colombia')
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)

    # Plan / billing
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='pilot')
    max_agents = models.PositiveIntegerField(default=3)
    monthly_message_limit = models.PositiveIntegerField(default=1000)

    # WhatsApp / channel credentials (stored at org level for quick access)
    whatsapp_number = models.CharField(max_length=30, blank=True)
    whatsapp_api_token = models.TextField(blank=True)  # Encrypted at rest in production

    # Settings
    timezone = models.CharField(max_length=50, default='America/Bogota')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organizations'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def active_agent_count(self):
        return self.users.filter(is_active=True).count()


# ─── User (Agent) ──────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('rol', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROL_CHOICES = [
        ('admin', 'Admin'),
        ('supervisor', 'Supervisor'),
        ('asesor', 'Asesor'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True,
    )

    # Auth
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)  # Handled by AbstractBaseUser

    # Profile
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    # Role
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default='asesor')

    # Availability (for real-time routing)
    is_available = models.BooleanField(default=True)
    max_concurrent_chats = models.PositiveSmallIntegerField(default=5)

    # Status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # MFA (future)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=64, blank=True)

    # Activity
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre']

    class Meta:
        db_table = 'users'
        ordering = ['nombre', 'apellido']
        indexes = [
            models.Index(fields=['organization', 'rol']),
            models.Index(fields=['organization', 'is_available']),
        ]

    def __str__(self):
        return f'{self.full_name} <{self.email}>'

    @property
    def full_name(self) -> str:
        return f'{self.nombre} {self.apellido}'.strip()

    def mark_seen(self):
        """Update last_seen timestamp — call on every authenticated request."""
        self.last_seen = timezone.now()
        self.save(update_fields=['last_seen'])


# ─── Contact ────────────────────────────────────────────────────────────────────

class Contact(models.Model):
    TIPO_CHOICES = [
        ('trabajador', 'Trabajador'),
        ('empleador', 'Empleador'),
        ('pensionado', 'Pensionado'),
        ('independiente', 'Independiente'),
        ('cliente', 'Cliente'),
    ]
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
        Organization, on_delete=models.CASCADE, related_name='contacts'
    )

    # Identity
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=30, blank=True, db_index=True)
    cedula = models.CharField(max_length=20, blank=True)

    # Classification
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='cliente')
    tipo_afiliado = models.CharField(max_length=30, blank=True)
    canal = models.CharField(
        max_length=20, choices=CHANNEL_CHOICES, default='whatsapp',
        help_text='Last known channel for this contact',
    )

    # Extra data
    metadata = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contacts'
        ordering = ['nombre', 'apellido']
        indexes = [
            models.Index(fields=['organization', 'tipo']),
            models.Index(fields=['organization', 'telefono']),
        ]

    def __str__(self):
        return f'{self.nombre} {self.apellido}'.strip()

    @property
    def full_name(self) -> str:
        return f'{self.nombre} {self.apellido}'.strip()


# ─── Security Audit Log ─────────────────────────────────────────────────────────

class SecurityAuditLog(models.Model):
    EVENT_CHOICES = [
        ('login_success', 'Login exitoso'),
        ('login_failed', 'Login fallido'),
        ('login_blocked_ip', 'Login bloqueado por IP'),
        ('password_changed', 'Contrasena cambiada'),
        ('security_settings_changed', 'Configuracion de seguridad cambiada'),
        ('agent_created', 'Agente creado'),
        ('agent_deleted', 'Agente eliminado'),
        ('ip_allowlist_changed', 'Lista blanca IP cambiada'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='audit_logs'
    )
    actor = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs'
    )
    actor_email = models.EmailField(blank=True)
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES)
    event_description = models.CharField(max_length=500)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'security_audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at'], name='sec_audit_org_date_idx'),
            models.Index(fields=['organization', 'event_type'], name='sec_audit_org_type_idx'),
        ]

    def __str__(self):
        return f'{self.event_type} — {self.actor_email} — {self.created_at}'
