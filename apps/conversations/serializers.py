from rest_framework import serializers
from .models import Conversation, Message, TimelineEvent, QAScore
from apps.workspace.serializers import CollabNoteSerializer


DEFAULT_OPERATOR_STATE = {
    'owner': 'ia',
    'active_ai_agent': '',
    'commercial_status': 'nuevo',
    'priority': 'media',
    'follow_up': False,
    'opportunity': False,
    'next_step': '',
    'conversation_summary': '',
    'escalation_reason': '',
}

FLOW_LABELS = {
    'comfaguajira_affiliation': 'Afiliacion y categoria',
    'comfaguajira_nutrition_quote': 'Cotizacion nutricion',
    'comfaguajira_education_quote': 'Cotizacion educacion',
    'comfaguajira_space_booking': 'Reserva de espacio',
    'comfaguajira_theater_booking': 'Reserva de teatro',
}


def _clean_text_output(value):
    if not isinstance(value, str) or not value:
        return value
    if 'Ã' not in value and 'Â' not in value:
        return value
    try:
        repaired = value.encode('latin1').decode('utf-8')
        if repaired:
            return repaired
    except Exception:
        pass
    return value.replace('Â', '')


def serialize_active_flow(metadata):
    active_flow = (metadata or {}).get('active_flow') or {}
    if not active_flow or not (active_flow.get('name') or active_flow.get('flow_id')):
        return None
    name = active_flow.get('name') or ''
    # DB flows expose flow_id; legacy hardcoded flows only have name
    return {
        'flow_id': active_flow.get('flow_id') or None,
        'name': name,
        'label': FLOW_LABELS.get(name, name),
        'step': active_flow.get('current_node_id') or active_flow.get('step') or '',
        'status': active_flow.get('status') or 'active',
        'data': active_flow.get('variables') or active_flow.get('data') or {},
    }


def serialize_sales_state(metadata):
    sales_state = (metadata or {}).get('sales_state') or {}
    if not sales_state:
        return None
    return {
        'stage': sales_state.get('stage') or '',
        'close_signals': sales_state.get('close_signals') or [],
        'closing_ready': bool(sales_state.get('closing_ready')),
        'decision': sales_state.get('decision') or '',
        'buyer_profile': sales_state.get('buyer_profile') or {},
    }


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'role', 'content', 'media_url', 'media_type', 'timestamp']
        read_only_fields = ['id', 'timestamp']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['content'] = _clean_text_output(data.get('content', ''))
        return data


class TimelineEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimelineEvent
        fields = ['id', 'tipo', 'descripcion', 'timestamp']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['descripcion'] = _clean_text_output(data.get('descripcion', ''))
        return data


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
    owner = serializers.SerializerMethodField()
    active_ai_agent = serializers.SerializerMethodField()
    commercial_status = serializers.SerializerMethodField()
    priority = serializers.SerializerMethodField()
    follow_up = serializers.SerializerMethodField()
    opportunity = serializers.SerializerMethodField()
    next_step = serializers.SerializerMethodField()
    conversation_summary = serializers.SerializerMethodField()
    escalation_reason = serializers.SerializerMethodField()
    note_count = serializers.SerializerMethodField()
    unread = serializers.SerializerMethodField()
    active_flow = serializers.SerializerMethodField()
    qualification = serializers.SerializerMethodField()
    sales_stage = serializers.SerializerMethodField()
    close_signals = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'canal', 'estado', 'intent', 'sentimiento',
            'contact_nombre', 'contact_apellido', 'contact_cedula',
            'contact_telefono', 'contact_email', 'contact_tipo_afiliado',
            'agent_nombre', 'last_message', 'last_message_at',
            'owner', 'active_ai_agent', 'commercial_status', 'priority', 'follow_up',
            'opportunity', 'next_step', 'conversation_summary',
            'escalation_reason', 'note_count', 'unread', 'active_flow', 'qualification',
            'sales_stage', 'close_signals',
            'created_at', 'updated_at',
        ]

    def get_agent_nombre(self, obj):
        if obj.assigned_agent:
            return obj.assigned_agent.full_name
        return None

    def get_last_message(self, obj):
        msg = obj.messages.last()
        return _clean_text_output(msg.content[:120]) if msg else ''

    def get_last_message_at(self, obj):
        msg = obj.messages.last()
        return msg.timestamp.isoformat() if msg else obj.updated_at.isoformat()

    def _operator_state(self, obj):
        metadata = obj.metadata or {}
        return {**DEFAULT_OPERATOR_STATE, **(metadata.get('operator_state') or {})}

    def get_owner(self, obj):
        return self._operator_state(obj)['owner']

    def get_active_ai_agent(self, obj):
        return self._operator_state(obj)['active_ai_agent']

    def get_commercial_status(self, obj):
        return self._operator_state(obj)['commercial_status']

    def get_priority(self, obj):
        return self._operator_state(obj)['priority']

    def get_follow_up(self, obj):
        return self._operator_state(obj)['follow_up']

    def get_opportunity(self, obj):
        return self._operator_state(obj)['opportunity']

    def get_next_step(self, obj):
        return self._operator_state(obj)['next_step']

    def get_conversation_summary(self, obj):
        summary = self._operator_state(obj)['conversation_summary']
        if summary:
            return _clean_text_output(summary)
        msg = obj.messages.last()
        return _clean_text_output((msg.content[:160] if msg else '').strip())

    def get_escalation_reason(self, obj):
        return self._operator_state(obj)['escalation_reason']

    def get_note_count(self, obj):
        return getattr(obj, 'collab_notes', []).count() if hasattr(obj, 'collab_notes') else 0

    def get_unread(self, obj):
        inbox_state = (obj.metadata or {}).get('inbox_state') or {}
        last_customer_message_at = inbox_state.get('last_customer_message_at')
        last_read_at = inbox_state.get('last_read_at')
        if not last_customer_message_at:
            return False
        if not last_read_at:
            return True
        return last_customer_message_at > last_read_at

    def get_active_flow(self, obj):
        return serialize_active_flow(obj.metadata)

    def get_qualification(self, obj):
        return (obj.metadata or {}).get('qualification') or {}

    def get_sales_stage(self, obj):
        sales_state = serialize_sales_state(obj.metadata)
        return sales_state.get('stage') if sales_state else ''

    def get_close_signals(self, obj):
        sales_state = serialize_sales_state(obj.metadata)
        return sales_state.get('close_signals') if sales_state else []


class ConversationDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    timeline = TimelineEventSerializer(many=True, read_only=True)
    notes = serializers.SerializerMethodField()
    contact_nombre = serializers.CharField(source='contact.nombre', read_only=True)
    contact_apellido = serializers.CharField(source='contact.apellido', read_only=True)
    contact_cedula = serializers.CharField(source='contact.cedula', read_only=True)
    contact_telefono = serializers.CharField(source='contact.telefono', read_only=True)
    contact_email = serializers.CharField(source='contact.email', read_only=True)
    contact_tipo_afiliado = serializers.CharField(source='contact.tipo_afiliado', read_only=True)
    agent_nombre = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
    active_ai_agent = serializers.SerializerMethodField()
    commercial_status = serializers.SerializerMethodField()
    priority = serializers.SerializerMethodField()
    follow_up = serializers.SerializerMethodField()
    opportunity = serializers.SerializerMethodField()
    next_step = serializers.SerializerMethodField()
    conversation_summary = serializers.SerializerMethodField()
    escalation_reason = serializers.SerializerMethodField()
    unread = serializers.SerializerMethodField()
    active_flow = serializers.SerializerMethodField()
    qualification = serializers.SerializerMethodField()
    sales_stage = serializers.SerializerMethodField()
    close_signals = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'organization', 'contact', 'assigned_agent',
            'canal', 'estado', 'intent', 'sentimiento', 'external_id',
            'metadata', 'sla_deadline', 'last_message_at', 'resolved_at',
            'created_at', 'updated_at',
            'contact_nombre', 'contact_apellido', 'contact_cedula',
            'contact_telefono', 'contact_email', 'contact_tipo_afiliado',
            'agent_nombre', 'owner', 'active_ai_agent', 'commercial_status', 'priority',
            'follow_up', 'opportunity', 'next_step', 'conversation_summary',
            'escalation_reason', 'unread', 'active_flow', 'qualification', 'sales_stage', 'close_signals', 'messages', 'timeline', 'notes',
        ]

    def get_agent_nombre(self, obj):
        if obj.assigned_agent:
            return obj.assigned_agent.full_name
        return None

    def _operator_state(self, obj):
        metadata = obj.metadata or {}
        return {**DEFAULT_OPERATOR_STATE, **(metadata.get('operator_state') or {})}

    def get_owner(self, obj):
        return self._operator_state(obj)['owner']

    def get_active_ai_agent(self, obj):
        return self._operator_state(obj)['active_ai_agent']

    def get_commercial_status(self, obj):
        return self._operator_state(obj)['commercial_status']

    def get_priority(self, obj):
        return self._operator_state(obj)['priority']

    def get_follow_up(self, obj):
        return self._operator_state(obj)['follow_up']

    def get_opportunity(self, obj):
        return self._operator_state(obj)['opportunity']

    def get_next_step(self, obj):
        return self._operator_state(obj)['next_step']

    def get_conversation_summary(self, obj):
        summary = self._operator_state(obj)['conversation_summary']
        if summary:
            return _clean_text_output(summary)
        last_messages = list(obj.messages.order_by('-timestamp')[:3])
        text = ' '.join(message.content.strip() for message in reversed(last_messages) if message.content)
        return _clean_text_output(text[:220])

    def get_escalation_reason(self, obj):
        return self._operator_state(obj)['escalation_reason']

    def get_notes(self, obj):
        notes = obj.collab_notes.order_by('-is_pinned', '-created_at')[:20]
        return CollabNoteSerializer(notes, many=True).data

    def get_unread(self, obj):
        inbox_state = (obj.metadata or {}).get('inbox_state') or {}
        last_customer_message_at = inbox_state.get('last_customer_message_at')
        last_read_at = inbox_state.get('last_read_at')
        if not last_customer_message_at:
            return False
        if not last_read_at:
            return True
        return last_customer_message_at > last_read_at

    def get_active_flow(self, obj):
        return serialize_active_flow(obj.metadata)

    def get_qualification(self, obj):
        return (obj.metadata or {}).get('qualification') or {}

    def get_sales_stage(self, obj):
        sales_state = serialize_sales_state(obj.metadata)
        return sales_state.get('stage') if sales_state else ''

    def get_close_signals(self, obj):
        sales_state = serialize_sales_state(obj.metadata)
        return sales_state.get('close_signals') if sales_state else []
