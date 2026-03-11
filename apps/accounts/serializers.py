"""
Accounts serializers — JWT, Organization, User (Agent), Contact.
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from .models import Organization, Contact

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
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at', 'full_name']


class ContactListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = Contact
        fields = ['id', 'full_name', 'telefono', 'email', 'tipo', 'canal', 'is_active', 'created_at']
