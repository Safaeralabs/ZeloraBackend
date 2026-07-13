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


def _serialize_cart_snapshot(raw) -> dict:
    """Sanitize a cart snapshot ({cart_items, total, currency})."""
    raw = raw if isinstance(raw, dict) else {}
    cart_items = []
    for item in raw.get('cart_items') or []:
        if not isinstance(item, dict) or not item.get('title'):
            continue
        cart_items.append({
            'product_id': str(item.get('product_id') or ''),
            'title': _clean_text_output(item.get('title', '')),
            'qty': int(item.get('qty') or 1),
            'unit_price': float(item.get('unit_price') or 0),
            'subtotal': float(item.get('subtotal') or 0),
            'currency': str(item.get('currency') or 'COP'),
        })
    return {
        'cart_items': cart_items,
        'total': float(raw.get('total') or 0),
        'currency': str(raw.get('currency') or 'COP'),
    }


def serialize_message_ui_payload(metadata):
    ui_payload = (metadata or {}).get('ui_payload') or {}
    if not isinstance(ui_payload, dict):
        return None

    if ui_payload.get('type') == 'checkout_compact':
        fields = []
        for item in ui_payload.get('fields') or []:
            if not isinstance(item, dict) or not item.get('key') or not item.get('label'):
                continue
            fields.append({
                'key': str(item.get('key')),
                'label': _clean_text_output(item.get('label', '')),
                'required': bool(item.get('required')),
                'placeholder': _clean_text_output(item.get('placeholder', '')),
                'input_type': item.get('input_type', 'text') or 'text',
            })

        cart_items = []
        for item in ui_payload.get('cart_items') or []:
            if not isinstance(item, dict) or not item.get('title'):
                continue
            cart_items.append({
                'product_id': str(item.get('product_id') or ''),
                'title': _clean_text_output(item.get('title', '')),
                'qty': int(item.get('qty') or 1),
                'unit_price': float(item.get('unit_price') or 0),
                'subtotal': float(item.get('subtotal') or 0),
                'currency': str(item.get('currency') or 'COP'),
            })

        initial_values = ui_payload.get('initial_values') or {}
        if not isinstance(initial_values, dict):
            initial_values = {}

        payment_options = []
        for item in ui_payload.get('payment_options') or []:
            if not isinstance(item, dict):
                continue
            option_id = str(item.get('id') or '').strip()
            label = str(item.get('label') or '').strip()
            if not option_id or not label:
                continue
            payment_options.append({
                'id': option_id,
                'label': _clean_text_output(label),
                'description': _clean_text_output(str(item.get('description') or '')),
                'instructions': _clean_text_output(str(item.get('instructions') or '')),
            })

        return {
            'type': 'checkout_compact',
            'title': _clean_text_output(ui_payload.get('title', 'Confirma tu pedido')),
            'submit_label': _clean_text_output(ui_payload.get('submit_label', 'Confirmar pedido')),
            'currency': str(ui_payload.get('currency') or 'COP'),
            'cart_items': cart_items,
            'total': float(ui_payload.get('total') or 0),
            'country_code': str(ui_payload.get('country_code') or ''),
            'blocked_zones': ui_payload.get('blocked_zones') or [],
            'fields': fields,
            'initial_values': initial_values,
            'required_fields': ui_payload.get('required_fields') or [],
            'payment_options': payment_options,
        }

    if ui_payload.get('type') == 'checkout_shipping_form':
        fields = []
        for item in ui_payload.get('fields') or []:
            if not isinstance(item, dict) or not item.get('key') or not item.get('label'):
                continue
            fields.append({
                'key': str(item.get('key')),
                'label': _clean_text_output(item.get('label', '')),
                'required': bool(item.get('required')),
                'placeholder': _clean_text_output(item.get('placeholder', '')),
                'input_type': item.get('input_type', 'text') or 'text',
            })

        if not fields:
            return None

        initial_values = ui_payload.get('initial_values') or {}
        if not isinstance(initial_values, dict):
            initial_values = {}

        return {
            'type': 'checkout_shipping_form',
            'title': _clean_text_output(ui_payload.get('title', 'Completa tus datos de envio')),
            'submit_label': _clean_text_output(ui_payload.get('submit_label', 'Enviar datos')),
            'country_code': str(ui_payload.get('country_code') or ''),
            'blocked_zones': ui_payload.get('blocked_zones') or [],
            'fields': fields,
            'initial_values': initial_values,
            'required_fields': ui_payload.get('required_fields') or [],
        }

    if ui_payload.get('type') == 'cart_update':
        snapshot = _serialize_cart_snapshot(ui_payload)
        return {'type': 'cart_update', **snapshot}

    if ui_payload.get('type') != 'product_list':
        return None

    products = []
    for item in ui_payload.get('products') or []:
        if not isinstance(item, dict) or not item.get('id') or not item.get('title'):
            continue
        products.append({
            'id': str(item.get('id')),
            'title': _clean_text_output(item.get('title', '')),
            'brand': _clean_text_output(item.get('brand', '')),
            'category': _clean_text_output(item.get('category', '')),
            'image_url': item.get('image_url', '') or '',
            'price_min': item.get('price_min'),
            'price_max': item.get('price_max'),
            'price_type': item.get('price_type', '') or '',
            'availability_label': _clean_text_output(item.get('availability_label', '')),
            'is_available': bool(item.get('is_available')),
            'cta_label': _clean_text_output(item.get('cta_label', 'Seleccionar')),
            'selection_message': _clean_text_output(item.get('selection_message', '')),
            'selection_payload': item.get('selection_payload') or {},
        })

    if not products:
        if isinstance(ui_payload.get('cart_snapshot'), dict):
            # Product cards got filtered out but the cart state must still reach
            # the client (e.g. the removed product was the only card candidate).
            return {'type': 'cart_update', **_serialize_cart_snapshot(ui_payload.get('cart_snapshot'))}
        return None

    payload = {
        'type': 'product_list',
        'layout': ui_payload.get('layout') or 'cards',
        'title': _clean_text_output(ui_payload.get('title', 'Productos sugeridos')),
        'products': products,
    }
    if isinstance(ui_payload.get('cart_snapshot'), dict):
        payload['cart_snapshot'] = _serialize_cart_snapshot(ui_payload.get('cart_snapshot'))
    return payload


class MessageSerializer(serializers.ModelSerializer):
    ui_payload = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'role', 'content', 'media_url', 'media_type', 'timestamp', 'ui_payload']
        read_only_fields = ['id', 'timestamp']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['content'] = _clean_text_output(data.get('content', ''))
        return data

    def get_ui_payload(self, obj):
        return serialize_message_ui_payload(getattr(obj, 'metadata', None) or {})


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
    contact_memory = serializers.SerializerMethodField()
    sales_session = serializers.SerializerMethodField()

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
            'escalation_reason', 'unread', 'active_flow', 'qualification', 'sales_stage', 'close_signals', 'contact_memory', 'sales_session', 'messages', 'timeline', 'notes',
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

    def get_sales_session(self, obj):
        """Live state of the v2 sales agent for this conversation."""
        try:
            from apps.ai_engine.models import SalesSession
            from apps.ai_engine.sales.catalog import CatalogService
            from apps.ai_engine.sales.decision import DecisionEngine

            session = SalesSession.objects.filter(conversation=obj).first()
            if not session:
                return None

            checkout_data = session.checkout_data or {}
            products = []
            for product_id in (session.selected_products or [])[:5]:
                product = CatalogService.get_product_by_id(str(product_id), obj.organization)
                if product:
                    products.append({
                        'id': product['id'],
                        'title': product['title'],
                        'price_min': product.get('price_min'),
                        'image_url': product.get('image_url', ''),
                    })

            situation = session.situation or ''
            stage = session.stage or 'discovery'
            strategy = ''
            if situation:
                strategy = str(DecisionEngine.decide(situation, stage).get('response_strategy') or '')

            return {
                'stage': stage,
                'situation': situation,
                'strategy': strategy,
                'checkout_step': session.checkout_step or 0,
                'message_count': session.message_count or 0,
                'objections': session.objections or [],
                'budget_min': float(session.budget_min) if session.budget_min is not None else None,
                'budget_max': float(session.budget_max) if session.budget_max is not None else None,
                'category_interest': session.category_interest or '',
                'selected_products': products,
                'order_number': str(checkout_data.get('order_number') or ''),
                'order_total': checkout_data.get('order_total'),
                'awaiting_confirmation': bool(checkout_data.get('awaiting_order_confirmation')),
                'followup_count': int(((checkout_data.get('followup_state') or {}).get('count')) or 0),
                'updated_at': session.updated_at.isoformat() if session.updated_at else None,
            }
        except Exception:
            return None

    def get_contact_memory(self, obj):
        contact = getattr(obj, 'contact', None)
        if not contact:
            return None
        try:
            from apps.ai_engine.models import ContactMemory
            memory = ContactMemory.objects.filter(contact=contact).first()
            if not memory:
                return None
            return {
                'conversation_count': memory.conversation_count,
                'inferred_budget_min': float(memory.inferred_budget_min) if memory.inferred_budget_min is not None else None,
                'inferred_budget_max': float(memory.inferred_budget_max) if memory.inferred_budget_max is not None else None,
                'style_cues': memory.style_cues or {},
                'occasion_hints': memory.occasion_hints or [],
                'category_preferences': memory.category_preferences or [],
                'last_products_shown': memory.last_products_shown or [],
                'last_intent': memory.last_intent or '',
                'last_objection': memory.last_objection or '',
                'converted': bool(memory.converted),
            }
        except Exception:
            return None
