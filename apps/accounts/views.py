"""
Accounts views — Auth, Agent management, Contact CRUD, Organization settings.
"""
import structlog
from django.utils.text import slugify
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Organization, Contact, SecurityAuditLog
from .serializers import (
    CustomTokenObtainPairSerializer,
    OrganizationSerializer,
    OnboardingProfileSerializer,
    OnboardingQuickKnowledgeUploadSerializer,
    SignupAvailabilitySerializer,
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    UserPasswordSerializer,
    ContactSerializer,
    ContactListSerializer,
    SecurityAuditLogSerializer,
)
from core.permissions import IsOrganizationAdmin, IsOrganizationMember, IsOrganizationAccountAdmin
from core.mixins import OrgScopedMixin
from apps.knowledge_base.upload_security import validate_kb_upload

User = get_user_model()
logger = structlog.get_logger(__name__)


def _build_company_slug(company_name: str) -> str:
    return slugify(company_name or '') or 'org'


def _merge_nested(existing: dict | None, patch: dict | None) -> dict:
    return {**(existing or {}), **(patch or {})}


def _default_general_agent_profile() -> dict:
    return {
        'agent_persona': '',
        'mission_statement': '',
        'scope_notes': '',
        'allowed_topics': [],
        'blocked_topics': [],
        'handoff_to_sales_when': [],
        'handoff_to_human_when': [],
        'greeting_message': '',
        'response_language': 'auto',
    }


def _hydrate_general_agent_profile(settings_payload: dict | None) -> dict:
    settings_payload = settings_payload or {}
    base = _default_general_agent_profile()
    stored = settings_payload.get('general_agent_profile') or {}
    return {
        **base,
        **stored,
    }


def _hydrate_sales_agent_profile(settings_payload: dict | None) -> dict:
    settings_payload = settings_payload or {}
    stored = settings_payload.get('sales_agent_profile') or {}
    return {
        'agent_persona': '',
        'mission_statement': '',
        'greeting_message': '',
        'response_language': 'auto',
        'competitor_response': '',
        'brand_profile': _merge_nested(settings_payload.get('brand_profile'), stored.get('brand_profile')),
        'sales_playbook': _merge_nested(settings_payload.get('sales_playbook'), stored.get('sales_playbook')),
        'buyer_model': _merge_nested(settings_payload.get('buyer_model'), stored.get('buyer_model')),
        'commerce_rules': _merge_nested(settings_payload.get('commerce_rules'), stored.get('commerce_rules')),
        **stored,
    }


def _merge_org_profile_block(existing: dict | None, patch: dict | None) -> dict:
    existing = existing or {}
    patch = patch or {}
    return {
        **existing,
        **patch,
        'brand': _merge_nested(existing.get('brand'), patch.get('brand')),
    }


def _sync_legacy_org_profile_fields(settings_payload: dict, org_profile: dict) -> dict:
    settings_payload['org_profile'] = org_profile
    settings_payload['what_you_sell'] = org_profile.get('what_you_sell', '')
    settings_payload['who_you_sell_to'] = org_profile.get('who_you_sell_to', '')
    settings_payload['payment_methods'] = org_profile.get('payment_methods', []) or []
    settings_payload['brand_profile'] = org_profile.get('brand', {}) or {}
    return settings_payload


def _sync_sales_agent_fields(settings_payload: dict, sales_agent: dict) -> dict:
    sales_agent = sales_agent or {}
    existing_profile = _hydrate_sales_agent_profile(settings_payload)
    next_profile = {
        **existing_profile,
        'agent_persona': sales_agent.get('persona', existing_profile.get('agent_persona', '')) or '',
        'mission_statement': sales_agent.get('mission_statement', existing_profile.get('mission_statement', '')) or '',
        'greeting_message': sales_agent.get('greeting_message', existing_profile.get('greeting_message', '')) or '',
        'response_language': sales_agent.get('response_language', existing_profile.get('response_language', 'auto')) or 'auto',
        'competitor_response': sales_agent.get('competitor_response', existing_profile.get('competitor_response', '')) or '',
        'sales_playbook': _merge_nested(
            existing_profile.get('sales_playbook'),
            sales_agent.get('playbook'),
        ),
        'buyer_model': _merge_nested(
            existing_profile.get('buyer_model'),
            sales_agent.get('buyer_model'),
        ),
        'commerce_rules': _merge_nested(
            existing_profile.get('commerce_rules'),
            sales_agent.get('commerce_rules'),
        ),
    }

    settings_payload['settings_version'] = 2
    settings_payload['sales_agent'] = sales_agent
    settings_payload['sales_agent_name'] = sales_agent.get('name') or settings_payload.get('sales_agent_name') or 'Sales Agent'
    settings_payload['sales_agent_profile'] = next_profile
    settings_payload['sales_playbook'] = next_profile.get('sales_playbook') or {}
    settings_payload['buyer_model'] = next_profile.get('buyer_model') or {}
    settings_payload['commerce_rules'] = next_profile.get('commerce_rules') or {}

    ai_preferences = dict(settings_payload.get('ai_preferences') or {})
    ai_sales_agent = dict(ai_preferences.get('sales_agent') or {})
    ai_preferences['sales_agent'] = {
        **ai_sales_agent,
        'enabled': sales_agent.get('enabled', ai_sales_agent.get('enabled', True)),
        'model_name': sales_agent.get('model_name', ai_sales_agent.get('model_name', 'gpt-4.1-nano')),
        'autonomy_level': sales_agent.get('autonomy_level', ai_sales_agent.get('autonomy_level', 'semi_autonomo')),
        'followup_mode': sales_agent.get('followup_mode', ai_sales_agent.get('followup_mode', 'suave')),
        'max_followups': sales_agent.get('max_followups', ai_sales_agent.get('max_followups', 1)),
        'recommendation_depth': sales_agent.get('recommendation_depth', ai_sales_agent.get('recommendation_depth', 2)),
        'handoff_mode': sales_agent.get('handoff_mode', ai_sales_agent.get('handoff_mode', 'balanceado')),
        'max_response_length': sales_agent.get('max_response_length', ai_sales_agent.get('max_response_length', 'standard')),
    }
    settings_payload['ai_preferences'] = ai_preferences
    return settings_payload


PAYMENT_METHOD_REQUIRED_FIELDS: dict[str, list[str]] = {
    'nequi': ['nequi_number', 'nequi_holder'],
    'transferencia bancaria': ['bank_name', 'account_number', 'account_holder'],
    'efectivo': ['cash_instructions'],
}


def _validate_payment_methods_configured(methods: list[str], payment_settings: dict | None) -> None:
    """A payment method can't go active until its required details are filled in.

    Methods outside PAYMENT_METHOD_REQUIRED_FIELDS (free-text/custom entries) pass
    through unchecked since there's no known schema to validate them against.
    """
    payment_settings = payment_settings or {}
    incomplete = [
        method for method in methods
        if method in PAYMENT_METHOD_REQUIRED_FIELDS
        and any(
            not str(payment_settings.get(field) or '').strip()
            for field in PAYMENT_METHOD_REQUIRED_FIELDS[method]
        )
    ]
    if incomplete:
        raise ValidationError({
            'payment_methods': (
                f"Completa los datos de {', '.join(incomplete)} antes de activarlo como metodo de pago."
            ),
        })


def _compute_activation_tasks(organization, settings_payload: dict) -> dict:
    from apps.channels_config.models import ChannelConfig
    from apps.knowledge_base.models import KBArticle, KBDocument

    quick_text = (settings_payload.get('quick_knowledge_text') or '').strip()
    quick_links = settings_payload.get('quick_knowledge_links') or []
    quick_files = settings_payload.get('quick_knowledge_files') or []
    has_quick_knowledge = bool(quick_text or quick_links or quick_files)
    has_kb_content = (
        KBArticle.objects.filter(organization=organization, is_active=True).exists()
        or KBDocument.objects.filter(organization=organization, is_active=True).exists()
    )

    channel_active = ChannelConfig.objects.filter(
        organization=organization,
        channel__in=['whatsapp', 'web', 'app'],
        is_active=True,
    ).exists()

    current_tasks = settings_payload.get('activation_tasks') or {}
    return {
        'knowledge_status': 'completed' if (has_quick_knowledge or has_kb_content) else 'pending',
        'channels_status': 'completed' if channel_active else 'pending',
        'payment_status': 'completed' if (settings_payload.get('payment_methods') or []) else 'pending',
        'agent_test_status': current_tasks.get('agent_test_status', 'pending'),
        'agent_tested_at': current_tasks.get('agent_tested_at'),
    }


# ─── Security Helpers ───────────────────────────────────────────────────────────

def _get_client_ip(request) -> str:
    """Extract real client IP from request (handles proxies)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _get_org_security_settings(org) -> dict:
    """Return the security_settings dict stored in the org's onboarding ChannelConfig."""
    try:
        from apps.channels_config.models import ChannelConfig
        config = ChannelConfig.objects.get(organization=org, channel='onboarding')
        return (config.settings or {}).get('security_settings', {})
    except Exception:
        return {}


def _check_ip_blocked(security_settings: dict, client_ip: str) -> bool:
    """Return True if client_ip should be blocked according to the org IP allowlist.

    Logic: if there are active allowlist entries, the IP must match at least one CIDR.
    Empty or all-inactive allowlist → no restriction (returns False).
    """
    import ipaddress
    allowlist = security_settings.get('ip_allowlist', [])
    active_entries = [e for e in allowlist if e.get('activo', True)]
    if not active_entries:
        return False
    try:
        client_addr = ipaddress.ip_address(client_ip)
        for entry in active_entries:
            try:
                network = ipaddress.ip_network(entry.get('cidr', ''), strict=False)
                if client_addr in network:
                    return False
            except ValueError:
                continue
        return True
    except ValueError:
        return False  # Can't parse IP → allow


def _validate_password_policy(security_settings: dict, password: str) -> list[str]:
    """Return list of human-readable error strings. Empty → password is valid."""
    import re
    errors = []
    min_len = security_settings.get('min_password_length', 8)
    if len(password) < min_len:
        errors.append(f'La contrasena debe tener al menos {min_len} caracteres.')
    if security_settings.get('require_special_chars'):
        if not re.search(r'[^A-Za-z0-9]', password):
            errors.append('La contrasena debe incluir al menos un caracter especial (!@#$...).')
    if security_settings.get('require_numbers'):
        if not re.search(r'[0-9]', password):
            errors.append('La contrasena debe incluir al menos un numero.')
    return errors


def _log_security_event(
    org,
    event_type: str,
    description: str,
    request=None,
    actor=None,
    actor_email: str = '',
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Create a SecurityAuditLog entry. Never raises — audit failures must not break normal flow."""
    try:
        resolved_ip = ip_address
        if resolved_ip is None and request is not None:
            resolved_ip = _get_client_ip(request) or None
        user_agent = ''
        if request is not None:
            user_agent = (request.META.get('HTTP_USER_AGENT', '') or '')[:300]
        resolved_email = actor_email or (actor.email if actor else '')
        SecurityAuditLog.objects.create(
            organization=org,
            actor=actor,
            actor_email=resolved_email,
            event_type=event_type,
            event_description=description,
            ip_address=resolved_ip or None,
            user_agent=user_agent,
            metadata=metadata or {},
        )
    except Exception:
        pass


# ─── Authentication ─────────────────────────────────────────────────────────────

class LoginView(TokenObtainPairView):
    """
    POST /api/auth/login/
    Returns JWT access + refresh tokens with custom claims (org_id, rol, nombre).
    """
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        email = (request.data.get('email', '') or '').strip().lower()
        client_ip = _get_client_ip(request)

        # Pre-fetch user for org context (needed for audit log even on failure)
        try:
            target_user = User.objects.select_related('organization').get(email__iexact=email)
            org = target_user.organization
        except User.DoesNotExist:
            target_user = None
            org = None

        try:
            response = super().post(request, *args, **kwargs)
        except Exception:
            if org:
                _log_security_event(
                    org=org,
                    event_type='login_failed',
                    description=f'Credenciales invalidas para {email}',
                    ip_address=client_ip or None,
                    actor_email=email,
                )
            raise

        if response.status_code == 200 and target_user and org:
            # Block unverified users (staff bypass for internal access)
            if not target_user.email_verified and not target_user.is_staff:
                return Response(
                    {'detail': 'email_not_verified'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Check IP allowlist
            security_settings = _get_org_security_settings(org)
            if _check_ip_blocked(security_settings, client_ip):
                _log_security_event(
                    org=org,
                    event_type='login_blocked_ip',
                    description=f'Acceso bloqueado desde IP no autorizada: {client_ip}',
                    ip_address=client_ip or None,
                    actor=target_user,
                    actor_email=email,
                )
                return Response(
                    {'detail': 'Acceso denegado: su direccion IP no esta en la lista blanca de la organizacion.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Log successful login
            _log_security_event(
                org=org,
                event_type='login_success',
                description=f'Login exitoso desde {client_ip}',
                request=request,
                ip_address=client_ip or None,
                actor=target_user,
                actor_email=email,
            )

            try:
                target_user.last_seen = timezone.now()
                target_user.save(update_fields=['last_seen'])
            except Exception:
                pass
            logger.info('user_login', email=email)

        return response


class SignupView(generics.CreateAPIView):
    """
    POST /api/auth/signup/
    Create a new Organization + initial Admin user.
    Used for the public onboarding flow.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        data = request.data
        email = data.get('email', '').strip()
        password = data.get('password', '')
        nombre = data.get('name', data.get('nombre', ''))
        company_name = data.get('company', data.get('organization', 'My Organization'))
        plan = data.get('plan', 'pilot')
        requested_role = (data.get('role') or data.get('rol') or '').strip().lower()
        company_name = (company_name or '').strip()
        company_slug = _build_company_slug(company_name)

        # Validate required fields
        if not email or not password or not nombre or not company_name:
            return Response(
                {'error': 'email, password, name and company are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email=email).exists():
            return Response(
                {'error': 'An account with this email already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if requested_role and requested_role != 'admin':
            return Response(
                {'error': 'Public signup only creates the initial admin account for an organization'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company_taken = Organization.objects.filter(slug=company_slug).exists() or Organization.objects.filter(name__iexact=company_name).exists()
        if company_taken:
            return Response(
                {'error': 'This brand name is no longer available'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org = Organization.objects.create(
            name=company_name,
            slug=company_slug,
            plan=plan,
        )

        # Create admin user
        user = User.objects.create_user(
            email=email,
            password=password,
            nombre=nombre,
            rol='admin',
            organization=org,
        )

        logger.info('user_signup', user_id=str(user.id), org_id=str(org.id), org=company_name)

        try:
            from .tasks import send_verification_email_task
            send_verification_email_task.delay(str(user.id))
        except Exception as exc:
            logger.warning('verification_email_queue_failed', user_id=str(user.id), error=str(exc))

        return Response(
            {
                'message': 'verification_email_sent',
                'email': email,
                'org_id': str(org.id),
                'user_id': str(user.id),
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(generics.GenericAPIView):
    """
    POST /api/auth/verify-email/
    Verifies the token from the email link and activates the user account.
    Returns JWT tokens on success (auto-login).
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        from rest_framework_simplejwt.tokens import RefreshToken
        from .models import EmailVerificationToken

        token_str = (request.data.get('token', '') or '').strip()
        if not token_str:
            return Response({'error': 'token is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_obj = EmailVerificationToken.objects.select_related('user').get(token=token_str)
        except (EmailVerificationToken.DoesNotExist, Exception):
            return Response({'error': 'Invalid or expired verification link'}, status=status.HTTP_400_BAD_REQUEST)

        if not token_obj.is_valid():
            return Response(
                {'error': 'Este enlace ya fue usado o ha expirado. Solicita uno nuevo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token_obj.user
        token_obj.used = True
        token_obj.save(update_fields=['used'])

        user.email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=['email_verified', 'email_verified_at'])

        refresh = RefreshToken.for_user(user)
        refresh['nombre'] = user.nombre
        refresh['apellido'] = user.apellido
        refresh['rol'] = user.rol
        refresh['org_id'] = str(user.organization_id) if user.organization_id else None
        refresh['org_name'] = user.organization.name if user.organization_id else ''
        refresh['is_available'] = user.is_available

        logger.info('email_verified', user_id=str(user.id))
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': str(user.id),
                'nombre': user.nombre,
                'apellido': user.apellido,
                'email': user.email,
                'rol': user.rol,
            },
        })


class ResendVerificationView(generics.GenericAPIView):
    """
    POST /api/auth/resend-verification/
    Resends the verification email. Rate-limited to 1 per 60 seconds per user.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        from .models import EmailVerificationToken
        from .tasks import send_verification_email_task

        email = (request.data.get('email', '') or '').strip().lower()
        if not email:
            return Response({'error': 'email is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Always return 200 to prevent email enumeration
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({'message': 'If the email exists and is unverified, a new link has been sent.'})

        if user.email_verified:
            return Response({'message': 'If the email exists and is unverified, a new link has been sent.'})

        # 60-second rate limit
        from datetime import timedelta
        recent = EmailVerificationToken.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(seconds=60),
        ).exists()
        if recent:
            return Response(
                {'error': 'Espera un momento antes de solicitar un nuevo enlace.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            send_verification_email_task.delay(str(user.id))
        except Exception as exc:
            logger.warning('resend_verification_queue_failed', user_id=str(user.id), error=str(exc))

        return Response({'message': 'If the email exists and is unverified, a new link has been sent.'})


class PasswordResetRequestView(generics.GenericAPIView):
    """
    POST /api/auth/password-reset/request/
    Sends a password reset email if the address matches an account.
    Always returns 200 with a generic message to prevent email enumeration.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        from datetime import timedelta
        from .models import PasswordResetToken
        from .tasks import send_password_reset_email_task

        generic_response = Response({'message': 'If the email exists, a reset link has been sent.'})

        email = (request.data.get('email', '') or '').strip().lower()
        if not email:
            return Response({'error': 'email is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return generic_response

        # 60-second rate limit, mirrors resend-verification
        recent = PasswordResetToken.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(seconds=60),
        ).exists()
        if recent:
            return generic_response

        try:
            send_password_reset_email_task.delay(str(user.id))
        except Exception as exc:
            logger.warning('password_reset_email_queue_failed', user_id=str(user.id), error=str(exc))

        return generic_response


class PasswordResetConfirmView(generics.GenericAPIView):
    """
    POST /api/auth/password-reset/confirm/
    Verifies the token from the reset email and sets a new password.
    Does not auto-login — the user re-authenticates with the new password.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        from .models import PasswordResetToken

        token_str = (request.data.get('token', '') or '').strip()
        new_password = request.data.get('new_password', '') or request.data.get('password', '')

        if not token_str:
            return Response({'error': 'token is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not new_password:
            return Response({'error': 'new_password is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_obj = PasswordResetToken.objects.select_related('user', 'user__organization').get(token=token_str)
        except (PasswordResetToken.DoesNotExist, ValueError, Exception):
            return Response({'error': 'Este enlace no es válido o ya expiró.'}, status=status.HTTP_400_BAD_REQUEST)

        if not token_obj.is_valid():
            return Response(
                {'error': 'Este enlace ya fue usado o ha expirado. Solicita uno nuevo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token_obj.user
        org = user.organization
        security_settings = _get_org_security_settings(org) if org else {}
        policy_errors = _validate_password_policy(security_settings, new_password)
        if policy_errors:
            return Response({'error': policy_errors[0]}, status=status.HTTP_400_BAD_REQUEST)

        token_obj.used = True
        token_obj.save(update_fields=['used'])

        user.set_password(new_password)
        user.save(update_fields=['password'])

        # Any other outstanding reset tokens for this user are now moot.
        PasswordResetToken.objects.filter(user=user, used=False).exclude(id=token_obj.id).update(used=True)

        if org:
            _log_security_event(
                org=org,
                event_type='password_reset',
                description=f'Contrasena restablecida via enlace de recuperacion para {user.email}',
                request=request,
                actor=user,
                actor_email=user.email,
            )

        logger.info('password_reset_completed', user_id=str(user.id))
        return Response({'message': 'password_reset_successful'})


class SignupAvailabilityView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = SignupAvailabilitySerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        email = data.get('email', '').strip().lower()
        name = data.get('name', '').strip()
        company = data.get('company', '').strip()
        company_slug = _build_company_slug(company) if company else ''
        company_exists = bool(
            company
            and (
                Organization.objects.filter(slug=company_slug).exists()
                or Organization.objects.filter(name__iexact=company).exists()
            )
        )

        return Response({
            'email_exists': bool(email and User.objects.filter(email__iexact=email).exists()),
            'name_exists': bool(name and User.objects.filter(nombre__iexact=name).exists()),
            'company_slug': company_slug,
            'company_available': bool(company and not company_exists),
        })


# ─── Agent Management ──────────────────────────────────────────────────────────

class AgentViewSet(viewsets.ModelViewSet):
    """
    CRUD for agents (users) within an organization.
    Only admins and supervisors can create/update/delete agents.
    """
    permission_classes = [IsOrganizationAdmin]

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsOrganizationAccountAdmin()]
        if self.action in ('me', 'change_password'):
            return [IsOrganizationMember()]
        return [IsOrganizationAdmin()]

    def get_queryset(self):
        return User.objects.filter(
            organization=self.request.user.organization
        ).select_related('organization').order_by('nombre', 'apellido')

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        if self.action in ('update', 'partial_update'):
            return UserUpdateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        org = self.request.user.organization
        if org.active_agent_count >= org.max_agents:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                f'Agent limit reached ({org.max_agents}). Upgrade your plan to add more agents.'
            )
        agent = serializer.save(organization=org)
        logger.info('agent_created', org_id=str(org.id), email=serializer.validated_data.get('email'))
        _log_security_event(
            org=org,
            event_type='agent_created',
            description=f'Agente creado: {agent.email}',
            request=self.request,
            actor=self.request.user,
            actor_email=self.request.user.email,
        )

    def perform_destroy(self, instance):
        org = instance.organization
        email = instance.email
        instance.delete()
        if org:
            _log_security_event(
                org=org,
                event_type='agent_deleted',
                description=f'Agente eliminado: {email}',
                request=self.request,
                actor=self.request.user,
                actor_email=self.request.user.email,
            )

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[IsOrganizationMember])
    def me(self, request):
        """
        GET  /api/auth/agents/me/  → Current agent profile
        PUT  /api/auth/agents/me/  → Update profile
        PATCH /api/auth/agents/me/ → Partial update
        """
        if request.method == 'GET':
            return Response(UserSerializer(request.user, context={'request': request}).data)

        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user, context={'request': request}).data)

    @action(detail=False, methods=['post'], permission_classes=[IsOrganizationMember])
    def change_password(self, request):
        """POST /api/auth/agents/change_password/"""
        serializer = UserPasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        new_password = serializer.validated_data['new_password']

        # Validate against org password policy
        org = request.user.organization
        if org:
            security_settings = _get_org_security_settings(org)
            policy_errors = _validate_password_policy(security_settings, new_password)
            if policy_errors:
                return Response({'detail': policy_errors[0]}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])

        if org:
            _log_security_event(
                org=org,
                event_type='password_changed',
                description=f'Contrasena cambiada por {request.user.email}',
                request=request,
                actor=request.user,
                actor_email=request.user.email,
            )

        logger.info('password_changed', user_id=str(request.user.id))
        return Response({'message': 'Password changed successfully'})

    @action(detail=True, methods=['post'])
    def toggle_availability(self, request, pk=None):
        """Toggle agent availability for routing."""
        agent = self.get_object()
        agent.is_available = not agent.is_available
        agent.save(update_fields=['is_available'])
        return Response({'is_available': agent.is_available})


# ─── Contact Management ────────────────────────────────────────────────────────

class ContactViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    """
    CRUD for contacts within an organization.
    Contacts are created automatically when webhooks arrive; agents can also
    create/edit them manually.
    """
    permission_classes = [IsOrganizationMember]
    filterset_fields = ['tipo', 'tipo_afiliado', 'canal']
    search_fields = ['nombre', 'apellido', 'email', 'telefono', 'cedula']
    ordering_fields = ['nombre', 'created_at', 'updated_at']

    def get_queryset(self):
        return Contact.objects.filter(
            organization=self.request.user.organization
        ).order_by('nombre', 'apellido')

    def get_serializer_class(self):
        if self.action == 'list':
            return ContactListSerializer
        return ContactSerializer

    @action(detail=True, methods=['get'])
    def conversations(self, request, pk=None):
        """GET /api/auth/contacts/{id}/conversations/ — Contact's conversation history."""
        contact = self.get_object()
        from apps.conversations.models import Conversation
        from apps.conversations.serializers import ConversationListSerializer
        convs = Conversation.objects.filter(
            contact=contact,
            organization=request.user.organization,
        ).order_by('-updated_at')[:20]
        return Response(ConversationListSerializer(convs, many=True).data)


# ─── Organization ──────────────────────────────────────────────────────────────

class OrganizationView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/auth/organization/ → Current org settings
    PUT  /api/auth/organization/ → Update org settings (admin only)
    """
    permission_classes = [IsOrganizationMember]
    serializer_class = OrganizationSerializer

    def get_object(self):
        return self.request.user.organization

    def update(self, request, *args, **kwargs):
        # Only admins can update organization settings
        if request.user.rol not in ('admin', 'supervisor'):
            return Response(
                {'error': 'Only admins can update organization settings'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)


class OnboardingProfileView(generics.GenericAPIView):
    permission_classes = [IsOrganizationMember]
    serializer_class = OnboardingProfileSerializer

    @staticmethod
    def _get_or_create_onboarding_config(organization):
        from apps.channels_config.models import ChannelConfig

        config, _ = ChannelConfig.objects.get_or_create(
            organization=organization,
            channel='onboarding',
            defaults={
                'is_active': True,
                'settings': {
                    'what_you_sell': '',
                    'who_you_sell_to': '',
                    'general_agent_name': 'General Agent',
                    'general_agent_profile': _default_general_agent_profile(),
                    'quick_knowledge_text': '',
                    'quick_knowledge_links': [],
                    'quick_knowledge_files': [],
                    'tax_id': '',
                    'contact_email': '',
                    'contact_phone': '',
                    'payment_methods': [],
                    'payment_settings': {
                        'nequi_enabled': True,
                        'nequi_number': '',
                        'nequi_holder': '',
                        'nequi_note': '',
                        'bank_transfer_enabled': True,
                        'cash_enabled': True,
                        'bank_name': '',
                        'account_type': '',
                        'account_number': '',
                        'account_holder': '',
                        'payment_reference_note': '',
                        'cash_instructions': '',
                        'payment_link_enabled': False,
                        'payment_link_url': '',
                    },
                    'locale_settings': {
                        'language': 'es',
                        'date_format': 'DD/MM/YYYY',
                        'default_response_language': True,
                        'session_timeout_minutes': 480,
                    },
                    'notification_settings': {
                        'items': [],
                    },
                    'ai_preferences': {
                        'provider': 'gpt4',
                        'copilot_model': 'gpt-4o',
                        'summary_model': 'gpt-4.1-nano',
                        'temperature': 0.55,
                        'max_tokens': 350,
                        'confidence_threshold': 75,
                        'copilot_suggestions': 3,
                        'sentiment_analysis': True,
                        'auto_summary': True,
                        'qa_scoring': True,
                        'general_agent': {
                            'enabled': True,
                            'trial_mode': True,
                            'model_name': 'gpt-4.1-nano',
                            'handoff_mode': 'balanceado',
                            'max_response_length': 'brief',
                        },
                    },
                    'activation_tasks': {
                        'knowledge_status': 'pending',
                        'channels_status': 'pending',
                        'agent_test_status': 'pending',
                        'agent_tested_at': None,
                    },
                    'initial_onboarding_completed': False,
                    'brand_profile': {
                        'tone_of_voice': '',
                        'formality_level': 'balanced',
                        'brand_personality': '',
                        'value_proposition': '',
                        'key_differentiators': [],
                        'preferred_closing_style': '',
                        'urgency_style': 'soft',
                        'recommended_phrases': [],
                        'avoid_phrases': [],
                    },
                    'sales_playbook': {
                        'opening_style': '',
                        'recommendation_style': '',
                        'objection_style': '',
                        'closing_style': '',
                        'follow_up_style': '',
                        'upsell_style': '',
                        'escalate_conditions': [],
                    },
                    'buyer_model': {
                        'ideal_buyers': [],
                        'common_objections': [],
                        'purchase_signals': [],
                        'low_intent_signals': [],
                        'bulk_buyer_signals': [],
                    },
                    'commerce_rules': {
                        'discount_policy': '',
                        'negotiation_policy': '',
                        'inventory_promise_rule': '',
                        'delivery_promise_rule': '',
                        'return_policy_summary': '',
                        'forbidden_claims': [],
                        'forbidden_promises': [],
                    },
                    'optimization_profile': {
                        'status': 'not_started',
                        'last_updated_at': None,
                    },
                    'onboarding_status': 'draft',
                    'completed_step': 1,
                },
            },
        )
        return config

    def get(self, request, *args, **kwargs):
        from apps.channels_config.settings_schema import normalise_settings

        org = request.user.organization
        config = self._get_or_create_onboarding_config(org)
        settings_payload = {**(config.settings or {})}
        settings_payload['activation_tasks'] = _compute_activation_tasks(org, settings_payload)
        settings_payload.update(normalise_settings(settings_payload))
        settings_payload['general_agent_name'] = settings_payload.get('general_agent_name') or 'General Agent'
        settings_payload['general_agent_profile'] = _hydrate_general_agent_profile(settings_payload)
        settings_payload['sales_agent_name'] = settings_payload.get('sales_agent_name') or settings_payload.get('sales_agent', {}).get('name') or 'Sales Agent'
        settings_payload['sales_agent_profile'] = _hydrate_sales_agent_profile(settings_payload)
        payload = {
            'organization_name': org.name,
            'website': org.website,
            'timezone': getattr(org, 'timezone', ''),
            **settings_payload,
        }
        return Response(self.get_serializer(payload).data)

    def patch(self, request, *args, **kwargs):
        from apps.channels_config.settings_schema import normalise_settings

        if request.user.rol not in ('admin', 'supervisor'):
            return Response(
                {'error': 'Only admins can update onboarding settings'},
                status=status.HTTP_403_FORBIDDEN,
            )

        org = request.user.organization
        config = self._get_or_create_onboarding_config(org)
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        incoming_methods = data.get('payment_methods')
        if incoming_methods is None and 'org_profile' in data:
            incoming_methods = (data.get('org_profile') or {}).get('payment_methods')
        if incoming_methods is not None:
            existing_payment_settings = (config.settings or {}).get('payment_settings') or {}
            incoming_payment_settings = data.get('payment_settings')
            effective_payment_settings = (
                {**existing_payment_settings, **incoming_payment_settings}
                if incoming_payment_settings is not None
                else existing_payment_settings
            )
            methods = [str(item).strip() for item in (incoming_methods or []) if str(item).strip()]
            _validate_payment_methods_configured(methods, effective_payment_settings)

        org_changed = False
        if 'organization_name' in data and data['organization_name'] != org.name:
            org.name = data['organization_name']
            org_changed = True
        if 'website' in data:
            org.website = data['website']
            org_changed = True
        if 'timezone' in data and data['timezone'] != getattr(org, 'timezone', ''):
            org.timezone = data['timezone']
            org_changed = True
        if org_changed:
            org.save(update_fields=['name', 'website', 'timezone', 'updated_at'])

        settings_payload = {**(config.settings or {})}
        for key in [
            'settings_version',
            'tax_id',
            'contact_email',
            'contact_phone',
            'payment_methods',
            'payment_settings',
            'what_you_sell',
            'who_you_sell_to',
            'general_agent_name',
            'quick_knowledge_text',
            'quick_knowledge_links',
            'quick_knowledge_files',
            'onboarding_status',
            'completed_step',
            'initial_onboarding_completed',
        ]:
            if key in data:
                settings_payload[key] = data[key]

        for key in [
            'brand_profile',
            'sales_playbook',
            'buyer_model',
            'commerce_rules',
            'locale_settings',
            'notification_settings',
            'ai_preferences',
            'optimization_profile',
            'activation_tasks',
            'security_settings',
        ]:
            if key in data:
                settings_payload[key] = _merge_nested(settings_payload.get(key), data[key])

        normalized_settings = normalise_settings(settings_payload)

        if 'payment_methods' in data:
            methods = [str(item).strip() for item in (data.get('payment_methods') or []) if str(item).strip()]
            settings_payload['payment_methods'] = methods
            next_org_profile = _merge_org_profile_block(
                normalized_settings.get('org_profile'),
                {'payment_methods': methods},
            )
            settings_payload = _sync_legacy_org_profile_fields(settings_payload, next_org_profile)
            settings_payload['settings_version'] = 2
            normalized_settings['org_profile'] = next_org_profile

        if 'org_profile' in data:
            next_org_profile = _merge_org_profile_block(normalized_settings.get('org_profile'), data['org_profile'])
            settings_payload = _sync_legacy_org_profile_fields(settings_payload, next_org_profile)
            settings_payload['settings_version'] = 2
            normalized_settings['org_profile'] = next_org_profile

        if 'ai_platform' in data:
            settings_payload['ai_platform'] = _merge_nested(normalized_settings.get('ai_platform'), data['ai_platform'])
            settings_payload['settings_version'] = 2

        if 'general_agent_profile' in data:
            current_general_agent_profile = _hydrate_general_agent_profile(settings_payload)
            incoming_profile = data['general_agent_profile'] or {}
            settings_payload['general_agent_profile'] = {
                **current_general_agent_profile,
                **incoming_profile,
            }

        if 'sales_agent_profile' in data:
            current_sales_agent_profile = _hydrate_sales_agent_profile(settings_payload)
            incoming_profile = data['sales_agent_profile'] or {}
            settings_payload['sales_agent_profile'] = {
                **current_sales_agent_profile,
                **incoming_profile,
            }

        if 'sales_agent_name' in data:
            settings_payload['sales_agent_name'] = data['sales_agent_name']

        if 'sales_agent' in data:
            merged_sales_agent = _merge_nested(normalized_settings.get('sales_agent'), data['sales_agent'])
            settings_payload = _sync_sales_agent_fields(settings_payload, merged_sales_agent)
            normalized_settings['sales_agent'] = merged_sales_agent

        settings_payload['general_agent_name'] = settings_payload.get('general_agent_name') or 'General Agent'
        settings_payload['general_agent_profile'] = _hydrate_general_agent_profile(settings_payload)
        settings_payload['sales_agent_name'] = settings_payload.get('sales_agent_name') or settings_payload.get('sales_agent', {}).get('name') or 'Sales Agent'
        settings_payload['sales_agent_profile'] = _hydrate_sales_agent_profile(settings_payload)
        settings_payload.update(normalise_settings(settings_payload))

        settings_payload['activation_tasks'] = _compute_activation_tasks(org, settings_payload)

        config.is_active = True
        config.settings = settings_payload
        config.save(update_fields=['is_active', 'settings', 'updated_at'])

        # Audit security settings changes
        if 'security_settings' in data:
            _log_security_event(
                org=org,
                event_type='security_settings_changed',
                description=f'Configuracion de seguridad actualizada por {request.user.email}',
                request=request,
                actor=request.user,
                actor_email=request.user.email,
            )

        response_payload = {
            'organization_name': org.name,
            'website': org.website,
            'timezone': getattr(org, 'timezone', ''),
            **settings_payload,
        }
        return Response(self.get_serializer(response_payload).data)


class OnboardingQuickKnowledgeUploadView(generics.GenericAPIView):
    permission_classes = [IsOrganizationMember]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = OnboardingQuickKnowledgeUploadSerializer

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get('file')
        if uploaded_file is None:
            return Response({'error': 'file is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_kb_upload(uploaded_file)
        except ValidationError as exc:
            return Response({'error': exc.detail[0] if isinstance(exc.detail, list) else exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        from apps.knowledge_base.models import KBDocument

        organization = request.user.organization
        document = KBDocument.objects.create(
            organization=organization,
            filename=uploaded_file.name,
            file=uploaded_file,
            file_size=uploaded_file.size or 0,
            mime_type=getattr(uploaded_file, 'content_type', '') or '',
            processing_status='pending',
        )

        onboarding_config = OnboardingProfileView._get_or_create_onboarding_config(organization)
        settings_payload = {**(onboarding_config.settings or {})}
        quick_files = settings_payload.get('quick_knowledge_files') or []
        quick_files.append({
            'id': str(document.id),
            'filename': document.filename,
            'file_size': document.file_size,
            'mime_type': document.mime_type,
            'uploaded_at': document.uploaded_at.isoformat(),
        })
        settings_payload['quick_knowledge_files'] = quick_files
        settings_payload['activation_tasks'] = _compute_activation_tasks(organization, settings_payload)
        onboarding_config.settings = settings_payload
        onboarding_config.save(update_fields=['settings', 'updated_at'])

        return Response(
            OnboardingQuickKnowledgeUploadSerializer({
                'id': str(document.id),
                'filename': document.filename,
                'file_size': document.file_size,
                'mime_type': document.mime_type,
                'uploaded_at': document.uploaded_at,
            }).data,
            status=status.HTTP_201_CREATED,
        )


# ─── Security Audit Log ─────────────────────────────────────────────────────────

class SecurityAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/auth/audit-log/            → Paginated audit log for the org (admin only)
    GET /api/auth/audit-log/export_csv/ → Download CSV
    """
    permission_classes = [IsOrganizationAdmin]
    serializer_class = SecurityAuditLogSerializer

    def get_queryset(self):
        return SecurityAuditLog.objects.filter(
            organization=self.request.user.organization
        ).order_by('-created_at')[:200]

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        import csv
        from django.http import HttpResponse
        qs = SecurityAuditLog.objects.filter(
            organization=request.user.organization
        ).order_by('-created_at')[:500]
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="security_audit_log.csv"'
        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'Tipo', 'Descripcion', 'Usuario', 'IP', 'User Agent'])
        for log in qs:
            writer.writerow([
                log.created_at.isoformat(),
                log.event_type,
                log.event_description,
                log.actor_email,
                log.ip_address or '',
                log.user_agent or '',
            ])
        return response
