"""
Accounts views — Auth, Agent management, Contact CRUD, Organization settings.
"""
import structlog
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Organization, Contact
from .serializers import (
    CustomTokenObtainPairSerializer,
    OrganizationSerializer,
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    UserPasswordSerializer,
    ContactSerializer,
    ContactListSerializer,
)
from core.permissions import IsOrganizationAdmin, IsOrganizationMember
from core.mixins import OrgScopedMixin

User = get_user_model()
logger = structlog.get_logger(__name__)


# ─── Authentication ─────────────────────────────────────────────────────────────

class LoginView(TokenObtainPairView):
    """
    POST /api/auth/login/
    Returns JWT access + refresh tokens with custom claims (org_id, rol, nombre).
    """
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Update last_seen
            try:
                email = request.data.get('email', '')
                User.objects.filter(email=email).update(last_seen=timezone.now())
            except Exception:
                pass
            logger.info('user_login', email=request.data.get('email', ''))
        return response


class SignupView(generics.CreateAPIView):
    """
    POST /api/auth/signup/
    Create a new Organization + initial Admin user.
    Used for the public onboarding flow.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        from django.utils.text import slugify
        import uuid

        data = request.data
        email = data.get('email', '').strip()
        password = data.get('password', '')
        nombre = data.get('name', data.get('nombre', ''))
        company_name = data.get('company', data.get('organization', 'My Organization'))
        plan = data.get('plan', 'pilot')

        # Validate required fields
        if not email or not password or not nombre:
            return Response(
                {'error': 'email, password, and name are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email=email).exists():
            return Response(
                {'error': 'An account with this email already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create organization with unique slug
        base_slug = slugify(company_name) or 'org'
        slug = f'{base_slug}-{str(uuid.uuid4())[:8]}'
        org = Organization.objects.create(
            name=company_name,
            slug=slug,
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

        return Response(
            {
                'message': 'Account created successfully',
                'org_id': str(org.id),
                'user_id': str(user.id),
            },
            status=status.HTTP_201_CREATED,
        )


# ─── Agent Management ──────────────────────────────────────────────────────────

class AgentViewSet(viewsets.ModelViewSet):
    """
    CRUD for agents (users) within an organization.
    Only admins and supervisors can create/update/delete agents.
    """
    permission_classes = [IsOrganizationAdmin]

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
        # Check agent limit
        if org.active_agent_count >= org.max_agents:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                f'Agent limit reached ({org.max_agents}). Upgrade your plan to add more agents.'
            )
        serializer.save(organization=org)
        logger.info('agent_created', org_id=str(org.id), email=serializer.validated_data.get('email'))

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
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password'])
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
    filterset_fields = ['tipo', 'tipo_afiliado', 'canal', 'is_active']
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
