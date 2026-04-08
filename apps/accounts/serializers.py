"""
Accounts serializers — JWT, Organization, User (Agent), Contact.
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from .models import Organization, Contact, SecurityAuditLog

User = get_user_model()


# ─── JWT Custom Claims ──────────────────────────────────────────────────────────

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends the standard JWT payload with Vendly-specific claims:
      - nombre, apellido, rol, org_id, is_available
    Also returns user metadata alongside the tokens in the response body.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Custom claims embedded in the JWT (available without DB lookup)
        token['nombre'] = user.nombre
        token['apellido'] = user.apellido or ''
        token['rol'] = user.rol
        token['org_id'] = str(user.organization_id) if user.organization_id else None
        token['org_name'] = user.organization.name if user.organization else None
        token['is_available'] = user.is_available
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Augment response with full user profile (so frontend doesn't need an extra /me/ call)
        data['user'] = {
            'id': str(self.user.id),
            'nombre': self.user.nombre,
            'apellido': self.user.apellido or '',
            'email': self.user.email,
            'rol': self.user.rol,
            'is_available': self.user.is_available,
            'avatar': self.user.avatar.url if self.user.avatar else None,
            'organization_id': str(self.user.organization_id) if self.user.organization_id else None,
            'organization_name': self.user.organization.name if self.user.organization else None,
        }
        return data


# ─── Organization ──────────────────────────────────────────────────────────────

class OrganizationSerializer(serializers.ModelSerializer):
    active_agent_count = serializers.ReadOnlyField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'slug', 'industry', 'country', 'website', 'logo',
            'plan', 'max_agents', 'monthly_message_limit',
            'whatsapp_number', 'timezone', 'is_active',
            'active_agent_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at', 'active_agent_count']
        extra_kwargs = {
            # Never expose the raw API token in responses
            'whatsapp_api_token': {'write_only': True},
        }


class OnboardingProfileSerializer(serializers.Serializer):
    organization_name = serializers.CharField(max_length=200)
    website = serializers.CharField(allow_blank=True, required=False)
    timezone = serializers.CharField(allow_blank=True, required=False)
    tax_id = serializers.CharField(allow_blank=True, required=False)
    contact_email = serializers.EmailField(allow_blank=True, required=False)
    contact_phone = serializers.CharField(allow_blank=True, required=False)
    payment_methods = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
    )
    payment_settings = serializers.JSONField(required=False)
    what_you_sell = serializers.CharField(allow_blank=True, required=False)
    who_you_sell_to = serializers.CharField(allow_blank=True, required=False)
    general_agent_name = serializers.CharField(allow_blank=True, required=False)
    general_agent_profile = serializers.JSONField(required=False)
    sales_agent_name = serializers.CharField(allow_blank=True, required=False)
    sales_agent_profile = serializers.JSONField(required=False)
    quick_knowledge_text = serializers.CharField(allow_blank=True, required=False)
    quick_knowledge_links = serializers.ListField(
        child=serializers.CharField(max_length=500),
        required=False,
    )
    quick_knowledge_files = serializers.ListField(
        child=serializers.JSONField(),
        required=False,
    )
    activation_tasks = serializers.JSONField(required=False)
    initial_onboarding_completed = serializers.BooleanField(required=False)
    brand_profile = serializers.JSONField(required=False)
    sales_playbook = serializers.JSONField(required=False)
    buyer_model = serializers.JSONField(required=False)
    commerce_rules = serializers.JSONField(required=False)
    locale_settings = serializers.JSONField(required=False)
    notification_settings = serializers.JSONField(required=False)
    ai_preferences = serializers.JSONField(required=False)
    optimization_profile = serializers.JSONField(required=False)
    security_settings = serializers.JSONField(required=False)
    onboarding_status = serializers.CharField(max_length=30, allow_blank=True, required=False)
    completed_step = serializers.IntegerField(min_value=1, max_value=3, required=False)

    def validate_website(self, value):
        if value and not (value.startswith('http://') or value.startswith('https://')):
            return f'https://{value}'
        return value

    def to_representation(self, instance):
        if not isinstance(instance, dict):
            return super().to_representation(instance)

        return {
            'organization_name': instance.get('organization_name', ''),
            'website': instance.get('website', ''),
            'timezone': instance.get('timezone', ''),
            'tax_id': instance.get('tax_id', ''),
            'contact_email': instance.get('contact_email', ''),
            'contact_phone': instance.get('contact_phone', ''),
            'payment_methods': instance.get('payment_methods', []),
            'payment_settings': instance.get('payment_settings', {}),
            'what_you_sell': instance.get('what_you_sell', ''),
            'who_you_sell_to': instance.get('who_you_sell_to', ''),
            'general_agent_name': instance.get('general_agent_name', ''),
            'general_agent_profile': instance.get('general_agent_profile', {}),
            'sales_agent_name': instance.get('sales_agent_name', ''),
            'sales_agent_profile': instance.get('sales_agent_profile', {}),
            'quick_knowledge_text': instance.get('quick_knowledge_text', ''),
            'quick_knowledge_links': instance.get('quick_knowledge_links', []),
            'quick_knowledge_files': instance.get('quick_knowledge_files', []),
            'activation_tasks': instance.get('activation_tasks', {}),
            'initial_onboarding_completed': instance.get('initial_onboarding_completed', False),
            'brand_profile': instance.get('brand_profile', {}),
            'sales_playbook': instance.get('sales_playbook', {}),
            'buyer_model': instance.get('buyer_model', {}),
            'commerce_rules': instance.get('commerce_rules', {}),
            'locale_settings': instance.get('locale_settings', {}),
            'notification_settings': instance.get('notification_settings', {}),
            'ai_preferences': instance.get('ai_preferences', {}),
            'optimization_profile': instance.get('optimization_profile', {}),
            'security_settings': instance.get('security_settings', {}),
            'onboarding_status': instance.get('onboarding_status', 'draft'),
            'completed_step': instance.get('completed_step', 1),
        }


class OnboardingQuickKnowledgeUploadSerializer(serializers.Serializer):
    id = serializers.CharField()
    filename = serializers.CharField()
    file_size = serializers.IntegerField()
    mime_type = serializers.CharField(allow_blank=True)
    uploaded_at = serializers.DateTimeField()


class SignupAvailabilitySerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    company = serializers.CharField(required=False, allow_blank=True, max_length=200)


# ─── User (Agent) ──────────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'nombre', 'apellido', 'telefono', 'avatar', 'avatar_url',
            'rol', 'is_active', 'is_available', 'max_concurrent_chats',
            'last_seen', 'full_name', 'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'last_seen']

    def get_avatar_url(self, obj):
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None


class UserCreateSerializer(serializers.ModelSerializer):
    """Used by admins when creating new agents for their organization."""
    password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = [
            'email', 'nombre', 'apellido', 'telefono', 'rol',
            'is_available', 'max_concurrent_chats', 'password',
        ]

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Used by agents to update their own profile."""

    class Meta:
        model = User
        fields = [
            'nombre', 'apellido', 'telefono', 'avatar',
            'is_available', 'max_concurrent_chats',
        ]


class UserPasswordSerializer(serializers.Serializer):
    """Change password endpoint."""
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect')
        return value


# ─── Contact ────────────────────────────────────────────────────────────────────

class ContactSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = Contact
        fields = [
            'id', 'nombre', 'apellido', 'full_name', 'email', 'telefono', 'cedula',
            'tipo', 'tipo_afiliado', 'canal', 'metadata', 'tags',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at', 'full_name']


class ContactListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = Contact
        fields = ['id', 'full_name', 'telefono', 'email', 'tipo', 'canal', 'metadata', 'created_at']


# ─── Security Audit Log ─────────────────────────────────────────────────────────

class SecurityAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurityAuditLog
        fields = [
            'id', 'actor_email', 'event_type', 'event_description',
            'ip_address', 'user_agent', 'metadata', 'created_at',
        ]
        read_only_fields = fields
