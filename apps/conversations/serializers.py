from rest_framework import serializers
from .models import Conversation, Message, TimelineEvent, QAScore


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'role', 'content', 'media_url', 'media_type', 'timestamp']
        read_only_fields = ['id', 'timestamp']


class TimelineEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimelineEvent
        fields = ['id', 'tipo', 'descripcion', 'timestamp']


class QAScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = QAScore
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class ConversationListSerializer(serializers.ModelSerializer):
    contact_nombre = serializers.CharField(source='contact.nombre', read_only=True)
    contact_apellido = serializers.CharField(source='contact.apellido', read_only=True)
    contact_cedula = serializers.CharField(source='contact.cedula', read_only=True)
    contact_telefono = serializers.CharField(source='contact.telefono', read_only=True)
    contact_email = serializers.CharField(source='contact.email', read_only=True)
    contact_tipo_afiliado = serializers.CharField(source='contact.tipo_afiliado', read_only=True)
    agent_nombre = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'canal', 'estado', 'intent', 'sentimiento',
            'contact_nombre', 'contact_apellido', 'contact_cedula',
            'contact_telefono', 'contact_email', 'contact_tipo_afiliado',
            'agent_nombre', 'last_message', 'last_message_at',
            'created_at', 'updated_at',
        ]

    def get_agent_nombre(self, obj):
        if obj.assigned_agent:
            return obj.assigned_agent.full_name
        return None

    def get_last_message(self, obj):
        msg = obj.messages.last()
        return msg.content[:120] if msg else ''

    def get_last_message_at(self, obj):
        msg = obj.messages.last()
        return msg.timestamp.isoformat() if msg else obj.updated_at.isoformat()


class ConversationDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    timeline = TimelineEventSerializer(many=True, read_only=True)
    contact_nombre = serializers.CharField(source='contact.nombre', read_only=True)
    contact_apellido = serializers.CharField(source='contact.apellido', read_only=True)
    contact_cedula = serializers.CharField(source='contact.cedula', read_only=True)
    contact_telefono = serializers.CharField(source='contact.telefono', read_only=True)
    contact_email = serializers.CharField(source='contact.email', read_only=True)
    contact_tipo_afiliado = serializers.CharField(source='contact.tipo_afiliado', read_only=True)
    agent_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = '__all__'

    def get_agent_nombre(self, obj):
        if obj.assigned_agent:
            return obj.assigned_agent.full_name
        return None
