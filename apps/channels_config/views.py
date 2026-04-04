import hashlib
import hmac
import re
import httpx
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import ChannelConfig
from .serializers import (
    AppChatConnectionSerializer,
    AppChatConversationQuerySerializer,
    PublicAppChatSessionSerializer,
    AppChatPublicSerializer,
    AppChatConnectionUpdateSerializer,
    AppChatInboundSerializer,
    ChannelConfigSerializer,
    DatabaseConnectionSerializer,
    DatabaseConnectionUpdateSerializer,
    DatabaseLookupSerializer,
    WebChatInboundSerializer,
    WhatsAppEmbeddedSignupCompleteSerializer,
    WhatsAppEmbeddedSignupConfigSerializer,
    WhatsAppEmbeddedSignupStartSerializer,
    WebWidgetConnectionSerializer,
    WebWidgetPublicSerializer,
    WebWidgetConnectionUpdateSerializer,
    WhatsAppConnectionSerializer,
    WhatsAppConnectionUpdateSerializer,
    WhatsAppSimulateInboundSerializer,
)
from .services.database_connection import (
    build_database_connection_payload,
    lookup_affiliate_by_document,
    test_database_connection,
    update_database_connection_config,
)
from .services.whatsapp_embedded_signup import (
    build_embedded_signup_config,
    complete_embedded_signup,
    mark_embedded_signup_failure,
    start_embedded_signup,
)
from .public_session import build_public_appchat_session_token, validate_public_appchat_session_token
from core.permissions import IsOrganizationMember
from core.mixins import OrgScopedMixin


PUBLIC_SLUG_SUFFIX_RE = re.compile(r'-(?P<suffix>[a-f0-9]{8})$')


def resolve_public_app_chat_config(org_slug: str | None):
    if not org_slug:
        return None
    return ChannelConfig.objects.select_related('organization').filter(
        organization__is_active=True,
        organization__slug=org_slug,
        channel='app',
        is_active=True,
    ).first()


def resolve_public_web_widget_config(org_slug: str | None):
    if not org_slug:
        return None
    return ChannelConfig.objects.select_related('organization').filter(
        organization__is_active=True,
        organization__slug=org_slug,
        channel='web',
        is_active=True,
    ).first()


def infer_webchat_intent(message_text: str) -> tuple[str, str]:
    normalized = message_text.lower()
    if any(keyword in normalized for keyword in ['subsidio', 'subsidy']):
        return 'check_subsidy', 'Puedo ayudarte con el subsidio. Comparte tu numero de cedula para continuar.'
    if any(keyword in normalized for keyword in ['certificado', 'certificate']):
        return 'request_certificate', 'Puedo ayudarte con el certificado. Necesito tu numero de cedula.'
    if any(keyword in normalized for keyword in ['cita', 'appointment', 'agendar']):
        return 'book_appointment', 'Vamos a agendar tu cita. Dime que servicio necesitas y tu disponibilidad.'
    if any(keyword in normalized for keyword in ['asesor', 'humano', 'agente']):
        return 'human_handoff', 'Voy a escalar tu conversacion a un asesor humano.'
    return 'general_support', 'Recibi tu consulta. Un asesor virtual la esta procesando para darte la mejor respuesta.'


def is_valid_whatsapp_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.META_APP_SECRET:
        return False
    if not signature_header or not signature_header.startswith('sha256='):
        return False
    expected = hmac.new(
        settings.META_APP_SECRET.encode('utf-8'),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    received = signature_header.split('=', 1)[1]
    return hmac.compare_digest(expected, received)


def resolve_whatsapp_org_from_payload(payload: dict):
    entries = payload.get('entry', [])
    for entry in entries:
        for change in entry.get('changes', []):
            value = change.get('value', {})
            metadata = value.get('metadata', {})
            phone_number_id = metadata.get('phone_number_id')
            if not phone_number_id:
                continue
            return ChannelConfig.objects.filter(
                channel='whatsapp',
                is_active=True,
                credentials__phone_number_id=phone_number_id,
            ).select_related('organization').first()
    return None


def build_whatsapp_connection_payload(config: ChannelConfig) -> dict:
    creds = config.credentials or {}
    config_settings = config.settings or {}
    return {
        'id': str(config.id),
        'channel': config.channel,
        'is_active': config.is_active,
        'webhook_url': config.webhook_url,
        'token_configured': bool(creds.get('access_token') or creds.get('api_token')),
        'phone_number_id': creds.get('phone_number_id', ''),
        'whatsapp_business_account_id': creds.get('waba_id', ''),
        'business_portfolio_id': creds.get('business_portfolio_id', ''),
        'display_phone_number': config_settings.get('display_phone_number', ''),
        'verified_name': config_settings.get('verified_name', ''),
        'onboarding_status': config_settings.get('onboarding_status', 'not_started'),
        'webhook_status': config_settings.get('webhook_status', 'pending'),
        'template_sync_status': config_settings.get('template_sync_status', 'never'),
        'quality_status': config_settings.get('quality_status', 'unknown'),
        'messaging_limit_status': config_settings.get('messaging_limit_status', 'unknown'),
        'capabilities': config_settings.get('capabilities', []),
        'last_sync_at': config_settings.get('last_sync_at'),
        'last_webhook_received_at': config_settings.get('last_webhook_received_at'),
        'default_send_behavior': config_settings.get('default_send_behavior', 'assistant_first'),
        'fallback_handling': config_settings.get('fallback_handling', 'router_decides'),
        'auto_sync_templates': config_settings.get('auto_sync_templates', True),
        'alert_on_webhook_failure': config_settings.get('alert_on_webhook_failure', True),
        'internal_label': config_settings.get('internal_label', ''),
        'internal_notes': config_settings.get('internal_notes', ''),
        'created_at': config.created_at,
        'updated_at': config.updated_at,
    }


def build_web_widget_payload(config: ChannelConfig, request) -> dict:
    config_settings = config.settings or {}
    widget_script_url = request.build_absolute_uri('/static/widget.js')
    org_slug = getattr(request.user.organization, 'slug', 'org')
    public_demo_url = request.build_absolute_uri(f'/webapp/demo?org={org_slug}')
    embed_snippet = (
        f'<script src="{widget_script_url}" '
        f'data-vendly-org="{org_slug}" '
        f'data-vendly-channel="web"></script>'
    )
    return {
        'id': str(config.id),
        'channel': config.channel,
        'organization_slug': org_slug,
        'is_active': config.is_active,
        'widget_name': config_settings.get('widget_name', 'Asistente web'),
        'greeting_message': config_settings.get('greeting_message', 'Hola. En que podemos ayudarte hoy?'),
        'brand_color': config_settings.get('brand_color', '#0f766e'),
        'position': config_settings.get('position', 'bottom-right'),
        'allowed_domains': config_settings.get('allowed_domains', []),
        'launcher_label': config_settings.get('launcher_label', 'Hablar con soporte'),
        'require_consent': config_settings.get('require_consent', True),
        'handoff_enabled': config_settings.get('handoff_enabled', True),
        'widget_script_url': widget_script_url,
        'embed_snippet': embed_snippet,
        'public_demo_url': public_demo_url,
        'install_status': config_settings.get('install_status', 'not_installed'),
        'verified_domains': config_settings.get('verified_domains', []),
        'last_install_check_at': config_settings.get('last_install_check_at'),
        'created_at': config.created_at,
        'updated_at': config.updated_at,
    }


def build_public_web_widget_payload(config: ChannelConfig, request) -> dict:
    full_payload = build_web_widget_payload(config, request)
    return {
        'organization_slug': full_payload['organization_slug'],
        'is_active': full_payload['is_active'],
        'widget_name': full_payload['widget_name'],
        'greeting_message': full_payload['greeting_message'],
        'brand_color': full_payload['brand_color'],
        'position': full_payload['position'],
        'launcher_label': full_payload['launcher_label'],
        'require_consent': full_payload['require_consent'],
        'handoff_enabled': full_payload['handoff_enabled'],
        'public_demo_url': full_payload['public_demo_url'],
    }


def build_app_chat_payload(config: ChannelConfig, request) -> dict:
    config_settings = config.settings or {}
    org_slug = getattr(config.organization, 'slug', 'org')
    publishable_key = f'vly_app_{org_slug}_{str(config.id).split("-")[0]}'
    rest_endpoint = request.build_absolute_uri('/api/channels/appchat/messages/')
    public_app_url = request.build_absolute_uri(f'/{org_slug}/')
    android_sdk_snippet = (
        'VendlyAppChat.init(\n'
        f'  baseUrl="{request.build_absolute_uri("/")[:-1]}",\n'
        f'  publishableKey="{publishable_key}",\n'
        f'  organizationSlug="{org_slug}"\n'
        ')'
    )
    ios_sdk_snippet = (
        'VendlyAppChat.configure(\n'
        f'  baseURL: "{request.build_absolute_uri("/")[:-1]}",\n'
        f'  publishableKey: "{publishable_key}",\n'
        f'  organizationSlug: "{org_slug}"\n'
        ')'
    )
    return {
        'id': str(config.id),
        'channel': config.channel,
        'organization_slug': org_slug,
        'is_active': config.is_active,
        'app_name': config_settings.get('app_name', 'App Chat'),
        'welcome_message': config_settings.get('welcome_message', 'Hola. En que podemos ayudarte desde la app?'),
        'primary_color': config_settings.get('primary_color', '#1d4ed8'),
        'accent_color': config_settings.get('accent_color', '#0f172a'),
        'page_background_color': config_settings.get('page_background_color', '#f7f3eb'),
        'background_mode': config_settings.get('background_mode', 'soft'),
        'background_treatment': config_settings.get('background_treatment', 'mesh'),
        'hero_height': config_settings.get('hero_height', 'balanced'),
        'logo_size': config_settings.get('logo_size', 'md'),
        'banner_intensity': config_settings.get('banner_intensity', 'medium'),
        'chat_density': config_settings.get('chat_density', 'comfortable'),
        'hero_curve': config_settings.get('hero_curve', 'soft'),
        'carousel_style': config_settings.get('carousel_style', 'glass'),
        'social_visibility': config_settings.get('social_visibility', 'auto'),
        'component_style': config_settings.get('component_style', 'soft_cards'),
        'layout_template': config_settings.get('layout_template', 'stack'),
        'background_image_url': config_settings.get('background_image_url', ''),
        'background_overlay': config_settings.get('background_overlay', 'soft-dark'),
        'font_family': config_settings.get('font_family', 'Manrope'),
        'font_scale': config_settings.get('font_scale', 'md'),
        'presentation_style': config_settings.get('presentation_style', 'bottom_sheet'),
        'surface_style': config_settings.get('surface_style', 'glass'),
        'bubble_style': config_settings.get('bubble_style', 'rounded'),
        'user_bubble_color': config_settings.get('user_bubble_color', '#1d4ed8'),
        'agent_bubble_color': config_settings.get('agent_bubble_color', '#ffffff'),
        'header_logo_url': config_settings.get('header_logo_url', ''),
        'launcher_label': config_settings.get('launcher_label', 'Abrir soporte'),
        'ticker_enabled': config_settings.get('ticker_enabled', False),
        'ticker_text': config_settings.get('ticker_text', ''),
        'show_featured_products': config_settings.get('show_featured_products', True),
        'instagram_url': config_settings.get('instagram_url', ''),
        'tiktok_url': config_settings.get('tiktok_url', ''),
        'whatsapp_url': config_settings.get('whatsapp_url', ''),
        'website_url': config_settings.get('website_url', ''),
        'location_url': config_settings.get('location_url', ''),
        'ios_bundle_ids': config_settings.get('ios_bundle_ids', []),
        'android_package_names': config_settings.get('android_package_names', []),
        'allowed_origins': config_settings.get('allowed_origins', []),
        'auth_mode': config_settings.get('auth_mode', 'jwt'),
        'require_authentication': config_settings.get('require_authentication', True),
        'push_enabled': config_settings.get('push_enabled', False),
        'handoff_enabled': config_settings.get('handoff_enabled', True),
        'publishable_key': publishable_key,
        'rest_endpoint': rest_endpoint,
        'public_app_url': public_app_url,
        'android_sdk_snippet': android_sdk_snippet,
        'ios_sdk_snippet': ios_sdk_snippet,
        'install_status': config_settings.get('install_status', 'not_installed'),
        'verified_apps': config_settings.get('verified_apps', []),
        'last_install_check_at': config_settings.get('last_install_check_at'),
        'created_at': config.created_at,
        'updated_at': config.updated_at,
    }


def build_public_app_chat_payload(config: ChannelConfig, request) -> dict:
    full_payload = build_app_chat_payload(config, request)
    return {
        'organization_slug': full_payload['organization_slug'],
        'app_name': full_payload['app_name'],
        'welcome_message': full_payload['welcome_message'],
        'primary_color': full_payload['primary_color'],
        'accent_color': full_payload['accent_color'],
        'page_background_color': full_payload['page_background_color'],
        'background_mode': full_payload['background_mode'],
        'background_treatment': full_payload['background_treatment'],
        'hero_height': full_payload['hero_height'],
        'logo_size': full_payload['logo_size'],
        'banner_intensity': full_payload['banner_intensity'],
        'chat_density': full_payload['chat_density'],
        'hero_curve': full_payload['hero_curve'],
        'carousel_style': full_payload['carousel_style'],
        'social_visibility': full_payload['social_visibility'],
        'component_style': full_payload['component_style'],
        'layout_template': full_payload['layout_template'],
        'background_image_url': full_payload['background_image_url'],
        'background_overlay': full_payload['background_overlay'],
        'font_family': full_payload['font_family'],
        'font_scale': full_payload['font_scale'],
        'presentation_style': full_payload['presentation_style'],
        'surface_style': full_payload['surface_style'],
        'bubble_style': full_payload['bubble_style'],
        'user_bubble_color': full_payload['user_bubble_color'],
        'agent_bubble_color': full_payload['agent_bubble_color'],
        'header_logo_url': full_payload['header_logo_url'],
        'launcher_label': full_payload['launcher_label'],
        'ticker_enabled': full_payload['ticker_enabled'],
        'ticker_text': full_payload['ticker_text'],
        'show_featured_products': full_payload['show_featured_products'],
        'instagram_url': full_payload['instagram_url'],
        'tiktok_url': full_payload['tiktok_url'],
        'whatsapp_url': full_payload['whatsapp_url'],
        'website_url': full_payload['website_url'],
        'location_url': full_payload['location_url'],
        'handoff_enabled': full_payload['handoff_enabled'],
        'public_app_url': full_payload['public_app_url'],
    }


def _broadcast_public_appchat_message(conversation, message):
    if conversation.canal != 'app' or not conversation.external_id:
        return
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        from apps.conversations.consumers import build_public_appchat_group
        from apps.conversations.serializers import MessageSerializer

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            build_public_appchat_group(conversation.organization.slug, conversation.external_id),
            {
                'type': 'appchat.message',
                'conversation_id': str(conversation.id),
                'session_id': conversation.external_id,
                'message': MessageSerializer(message).data,
            },
        )
    except Exception:
        pass


def _mark_inbound_unread(conversation, message_timestamp):
    metadata = {**(conversation.metadata or {})}
    inbox_state = {**(metadata.get('inbox_state') or {})}
    inbox_state['last_customer_message_at'] = message_timestamp.isoformat()
    metadata['inbox_state'] = inbox_state
    conversation.metadata = metadata
    conversation.save(update_fields=['metadata', 'updated_at'])


def create_inbound_conversation(*, data: dict, channel: str, source: str):
    from apps.accounts.models import Contact, Organization
    from apps.conversations.models import Conversation, Message, TimelineEvent

    org_slug = data.get('organization_slug', '').strip()
    session_token = (data.get('session_token') or '').strip()
    organization = None

    if org_slug:
        organization = Organization.objects.filter(slug=org_slug, is_active=True).first()
    if organization is None:
        raise ValueError('Organization not found')
    if channel == 'app' and not validate_public_appchat_session_token(org_slug, data['session_id'], session_token):
        raise ValueError('Invalid public app session token')

    contact_lookup = {}
    if data.get('email'):
        contact_lookup['email'] = data['email']
    elif data.get('telefono'):
        contact_lookup['telefono'] = data['telefono']

    contact_defaults = {
        'nombre': data.get('nombre') or ('Usuario app' if channel == 'app' else 'Visitante web'),
        'apellido': data.get('apellido', ''),
        'email': data.get('email', ''),
        'telefono': data.get('telefono', ''),
        'canal': channel,
        'tipo': 'cliente',
    }

    if contact_lookup:
        contact, _ = Contact.objects.get_or_create(
            organization=organization,
            defaults=contact_defaults,
            **contact_lookup,
        )
    else:
        contact = Contact.objects.create(organization=organization, **contact_defaults)

    conversation, created = Conversation.objects.get_or_create(
        organization=organization,
        canal=channel,
        external_id=data['session_id'],
        defaults={
            'contact': contact,
            'estado': 'nuevo',
            'metadata': {'source': source, 'platform': data.get('platform', '')},
            'last_message_at': timezone.now(),
        },
    )

    if conversation.contact_id != contact.id:
        conversation.contact = contact
        conversation.save(update_fields=['contact', 'updated_at'])

    user_message = Message.objects.create(
        conversation=conversation,
        role='user',
        content=data['message'],
        metadata={'source': source, 'platform': data.get('platform', '')},
    )

    _mark_inbound_unread(conversation, user_message.timestamp)
    conversation.last_message_at = user_message.timestamp

    # Auto-reopen resolved conversations when the client writes again
    if conversation.estado == 'resuelto':
        conversation.estado = 'abierto'
        conversation.resolved_at = None
        conversation.save(update_fields=['last_message_at', 'estado', 'resolved_at', 'updated_at'])
        from apps.conversations.models import TimelineEvent as _TE
        _TE.objects.create(
            conversation=conversation,
            tipo='reopened',
            descripcion='Conversacion reabierta automaticamente por nuevo mensaje del cliente',
        )
        # Reset commercial_status so the operator sees it as active again
        try:
            from apps.conversations.views import _update_operator_state
            _update_operator_state(conversation, {'commercial_status': 'en_proceso', 'owner': 'ia'})
        except Exception:
            pass
    else:
        conversation.save(update_fields=['last_message_at', 'updated_at'])

    if created:
        TimelineEvent.objects.create(
            conversation=conversation,
            tipo='bot_start',
            descripcion=f'Conversacion iniciada desde {source}',
            metadata={'source': source},
        )

    # Run AI Router pipeline
    try:
        from apps.ai_router.handler import handle_inbound_message
        bot_reply_text, decision = handle_inbound_message(
            conversation=conversation,
            message=user_message,
            organization=organization,
        )
        intent = decision.intent if decision else 'unknown'
    except Exception:
        intent, bot_reply_text = infer_webchat_intent(data['message'])

    TimelineEvent.objects.create(
        conversation=conversation,
        tipo='intent_detected',
        descripcion=f'Intent detectado: {intent}',
        metadata={'source': source, 'intent': intent},
    )

    bot_message = Message.objects.create(
        conversation=conversation,
        role='bot',
        content=bot_reply_text or 'Recibí tu mensaje. ¿En qué puedo ayudarte?',
        metadata={'source': source, 'intent': intent, 'generated_by': 'ai_router'},
    )

    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from apps.conversations.serializers import MessageSerializer, ConversationListSerializer

        channel_layer = get_channel_layer()
        conversation_payload = ConversationListSerializer(conversation).data
        async_to_sync(channel_layer.group_send)(
            f'org_{conversation.organization_id}',
            {
                'type': 'conversation.updated',
                'conversation_id': str(conversation.id),
                'event': 'conversation_upserted',
                'data': {'conversation': conversation_payload},
            },
        )
        async_to_sync(channel_layer.group_send)(
            f'org_{conversation.organization_id}',
            {
                'type': 'conversation.message',
                'conversation_id': str(conversation.id),
                'message': MessageSerializer(user_message).data,
                'conversation': conversation_payload,
            },
        )
        async_to_sync(channel_layer.group_send)(
            f'org_{conversation.organization_id}',
            {
                'type': 'conversation.message',
                'conversation_id': str(conversation.id),
                'message': MessageSerializer(bot_message).data,
                'conversation': conversation_payload,
            },
        )
    except Exception:
        pass

    _broadcast_public_appchat_message(conversation, user_message)
    _broadcast_public_appchat_message(conversation, bot_message)
    return {
        'conversation_id': str(conversation.id),
        'contact_id': str(contact.id),
        'intent': intent,
        'session_id': data['session_id'],
        'messages': [
            {
                'id': str(user_message.id),
                'role': user_message.role,
                'content': user_message.content,
                'timestamp': user_message.timestamp.isoformat(),
            },
            {
                'id': str(bot_message.id),
                'role': bot_message.role,
                'content': bot_message.content,
                'timestamp': bot_message.timestamp.isoformat(),
            },
        ],
    }


def get_public_conversation_payload(*, org_slug: str | None, session_id: str, channel: str):
    from apps.accounts.models import Organization
    from apps.conversations.models import Conversation

    organization = None
    if org_slug:
        organization = Organization.objects.filter(slug=org_slug, is_active=True).first()

    if organization is None:
        raise ValueError('Organization not found')

    conversation = Conversation.objects.filter(
        organization=organization,
        canal=channel,
        external_id=session_id,
    ).prefetch_related('messages').first()

    if conversation is None:
        return {
            'conversation_id': None,
            'contact_id': None,
            'intent': '',
            'session_id': session_id,
            'messages': [],
        }

    return {
        'conversation_id': str(conversation.id),
        'contact_id': str(conversation.contact_id) if conversation.contact_id else None,
        'intent': conversation.intent or '',
        'session_id': session_id,
        'messages': [
            {
                'id': str(message.id),
                'role': message.role,
                'content': message.content,
                'timestamp': message.timestamp.isoformat(),
            }
            for message in conversation.messages.order_by('timestamp')
        ],
    }


class ChannelConfigViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsOrganizationMember]
    serializer_class = ChannelConfigSerializer

    def get_queryset(self):
        return ChannelConfig.objects.filter(organization=self.request.user.organization)

    def _get_or_create_whatsapp_config(self, request):
        config, _ = ChannelConfig.objects.get_or_create(
            organization=request.user.organization,
            channel='whatsapp',
            defaults={
                'is_active': False,
                'webhook_url': '',
                'settings': {
                    'onboarding_status': 'not_started',
                    'webhook_status': 'pending',
                    'template_sync_status': 'never',
                    'quality_status': 'unknown',
                    'messaging_limit_status': 'unknown',
                    'capabilities': ['inbox'],
                    'default_send_behavior': 'assistant_first',
                    'fallback_handling': 'router_decides',
                    'auto_sync_templates': True,
                    'alert_on_webhook_failure': True,
                },
            },
        )
        return config

    def _get_or_create_web_config(self, request):
        config, _ = ChannelConfig.objects.get_or_create(
            organization=request.user.organization,
            channel='web',
            defaults={
                'is_active': False,
                'settings': {
                    'widget_name': 'Asistente web',
                    'greeting_message': 'Hola. En que podemos ayudarte hoy?',
                    'brand_color': '#0f766e',
                    'position': 'bottom-right',
                    'allowed_domains': [],
                    'launcher_label': 'Hablar con soporte',
                    'require_consent': True,
                    'handoff_enabled': True,
                    'install_status': 'not_installed',
                    'verified_domains': [],
                },
            },
        )
        return config

    def _get_or_create_app_chat_config(self, request):
        config, _ = ChannelConfig.objects.get_or_create(
            organization=request.user.organization,
            channel='app',
            defaults={
                'is_active': False,
                'settings': {
                    'app_name': 'App Chat',
                    'welcome_message': 'Hola. En que podemos ayudarte desde la app?',
                    'primary_color': '#1d4ed8',
                    'accent_color': '#0f172a',
                    'page_background_color': '#f7f3eb',
                    'background_mode': 'soft',
                    'background_treatment': 'mesh',
                    'hero_height': 'balanced',
                    'logo_size': 'md',
                    'banner_intensity': 'medium',
                    'chat_density': 'comfortable',
                    'hero_curve': 'soft',
                    'carousel_style': 'glass',
                    'social_visibility': 'auto',
                    'component_style': 'soft_cards',
                    'layout_template': 'stack',
                    'background_image_url': '',
                    'background_overlay': 'soft-dark',
                    'font_family': 'Manrope',
                    'font_scale': 'md',
                    'presentation_style': 'bottom_sheet',
                    'surface_style': 'glass',
                    'bubble_style': 'rounded',
                    'user_bubble_color': '#1d4ed8',
                    'agent_bubble_color': '#ffffff',
                    'header_logo_url': '',
                    'launcher_label': 'Abrir soporte',
                    'ticker_enabled': False,
                    'ticker_text': '',
                    'show_featured_products': True,
                    'instagram_url': '',
                    'tiktok_url': '',
                    'whatsapp_url': '',
                    'website_url': '',
                    'location_url': '',
                    'ios_bundle_ids': [],
                    'android_package_names': [],
                    'allowed_origins': [],
                    'auth_mode': 'jwt',
                    'require_authentication': True,
                    'push_enabled': False,
                    'handoff_enabled': True,
                    'install_status': 'not_installed',
                    'verified_apps': [],
                },
            },
        )
        return config

    def _get_or_create_database_config(self, request):
        config, _ = ChannelConfig.objects.get_or_create(
            organization=request.user.organization,
            channel='database',
            defaults={
                'is_active': False,
                'settings': {
                    'engine': 'postgresql',
                    'host': '',
                    'port': 5432,
                    'database_name': '',
                    'schema_name': 'public',
                    'ssl_mode': 'prefer',
                    'connection_status': 'not_configured',
                    'last_error': '',
                    'default_lookup_table': '',
                    'document_column': '',
                    'full_name_column': '',
                    'phone_column': '',
                    'email_column': '',
                    'affiliate_type_column': '',
                    'capabilities': ['affiliate_lookup'],
                },
            },
        )
        return config

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        config = self.get_object()
        # Simulate connection test
        return Response({'status': 'connected', 'channel': config.channel})

    @action(
        detail=False,
        methods=['get', 'post'],
        url_path='whatsapp/webhook',
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def whatsapp_webhook(self, request):
        if request.method == 'GET':
            verify_token = request.query_params.get('hub.verify_token')
            challenge = request.query_params.get('hub.challenge')
            if verify_token == settings.WHATSAPP_VERIFY_TOKEN:
                return HttpResponse(challenge or '', content_type='text/plain')
            return Response({'error': 'Invalid token'}, status=status.HTTP_403_FORBIDDEN)

        if len(request.body or b'') > 1024 * 1024:
            return Response({'error': 'Payload too large'}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        signature = request.headers.get('X-Hub-Signature-256')
        if not is_valid_whatsapp_signature(request.body, signature):
            return Response({'error': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data
        if payload.get('object') != 'whatsapp_business_account':
            return Response({'error': 'Unsupported webhook object'}, status=status.HTTP_400_BAD_REQUEST)

        channel_config = resolve_whatsapp_org_from_payload(payload)
        if channel_config is None or channel_config.organization_id is None:
            return Response({'error': 'Unknown phone number binding'}, status=status.HTTP_404_NOT_FOUND)

        try:
            from tasks.channel_tasks import process_incoming_webhook
            process_incoming_webhook.delay(payload, 'whatsapp', str(channel_config.organization_id))
        except Exception:
            return Response({'error': 'Webhook queue unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'status': 'received'})

    @action(detail=False, methods=['get', 'patch'], url_path='whatsapp/connection')
    def whatsapp_connection(self, request):
        config = self._get_or_create_whatsapp_config(request)

        if request.method == 'GET':
            serializer = WhatsAppConnectionSerializer(build_whatsapp_connection_payload(config))
            return Response(serializer.data)

        serializer = WhatsAppConnectionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        credentials = {**(config.credentials or {})}
        config_settings = {**(config.settings or {})}

        if 'access_token' in data and data['access_token']:
            credentials['access_token'] = data['access_token']
        if 'phone_number_id' in data:
            credentials['phone_number_id'] = data['phone_number_id']
        if 'whatsapp_business_account_id' in data:
            credentials['waba_id'] = data['whatsapp_business_account_id']
        if 'business_portfolio_id' in data:
            credentials['business_portfolio_id'] = data['business_portfolio_id']

        for key in [
            'display_phone_number',
            'verified_name',
            'onboarding_status',
            'webhook_status',
            'template_sync_status',
            'quality_status',
            'messaging_limit_status',
            'capabilities',
            'default_send_behavior',
            'fallback_handling',
            'auto_sync_templates',
            'alert_on_webhook_failure',
            'internal_label',
            'internal_notes',
        ]:
            if key in data:
                config_settings[key] = data[key]

        if 'webhook_url' in data:
            config.webhook_url = data['webhook_url']
        if 'is_active' in data:
            config.is_active = data['is_active']

        config.credentials = credentials
        config.settings = config_settings
        config.save()

        response_serializer = WhatsAppConnectionSerializer(build_whatsapp_connection_payload(config))
        return Response(response_serializer.data)

    @action(detail=False, methods=['get'], url_path='whatsapp/embedded-signup/config')
    def whatsapp_embedded_signup_config(self, request):
        config = self._get_or_create_whatsapp_config(request)
        serializer = WhatsAppEmbeddedSignupConfigSerializer(build_embedded_signup_config(config, request))
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='whatsapp/embedded-signup/start')
    def whatsapp_embedded_signup_start(self, request):
        config = self._get_or_create_whatsapp_config(request)
        _, signup_settings = start_embedded_signup(config)
        serializer = WhatsAppEmbeddedSignupStartSerializer({
            'session_state': signup_settings['session_state'],
            'session_started_at': signup_settings['session_started_at'],
            'session_status': signup_settings['session_status'],
        })
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='whatsapp/embedded-signup/complete')
    def whatsapp_embedded_signup_complete(self, request):
        config = self._get_or_create_whatsapp_config(request)
        serializer = WhatsAppEmbeddedSignupCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            config = complete_embedded_signup(config, **serializer.validated_data)
        except ValueError as exc:
            mark_embedded_signup_failure(config, str(exc))
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPError as exc:  # type: ignore[name-defined]
            mark_embedded_signup_failure(config, str(exc))
            return Response({'error': 'Meta token exchange failed'}, status=status.HTTP_502_BAD_GATEWAY)
        response_serializer = WhatsAppConnectionSerializer(build_whatsapp_connection_payload(config))
        return Response(response_serializer.data)

    @action(detail=False, methods=['get', 'patch'], url_path='webapp/connection')
    def webapp_connection(self, request):
        config = self._get_or_create_web_config(request)

        if request.method == 'GET':
            serializer = WebWidgetConnectionSerializer(build_web_widget_payload(config, request))
            return Response(serializer.data)

        serializer = WebWidgetConnectionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        config_settings = {**(config.settings or {})}
        for key in [
            'widget_name',
            'greeting_message',
            'brand_color',
            'position',
            'allowed_domains',
            'launcher_label',
            'require_consent',
            'handoff_enabled',
        ]:
            if key in data:
                config_settings[key] = data[key]
        if 'is_active' in data:
            config.is_active = data['is_active']
            config_settings['install_status'] = 'configured' if data['is_active'] else 'not_installed'

        config.settings = config_settings
        config.save()

        response_serializer = WebWidgetConnectionSerializer(build_web_widget_payload(config, request))
        return Response(response_serializer.data)

    @action(
        detail=False,
        methods=['get'],
        url_path=r'webapp/public/(?P<org_slug>[^/.]+)',
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def webapp_public(self, request, org_slug=None):
        config = resolve_public_web_widget_config(org_slug)
        if config is None:
            return Response({'detail': 'Web Widget no disponible para esta marca.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = WebWidgetPublicSerializer(build_public_web_widget_payload(config, request))
        return Response(serializer.data)

    @action(detail=False, methods=['get', 'patch'], url_path='appchat/connection')
    def appchat_connection(self, request):
        config = self._get_or_create_app_chat_config(request)

        if request.method == 'GET':
            serializer = AppChatConnectionSerializer(build_app_chat_payload(config, request))
            return Response(serializer.data)

        serializer = AppChatConnectionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        config_settings = {**(config.settings or {})}
        for key in [
            'app_name',
            'welcome_message',
            'primary_color',
            'accent_color',
            'page_background_color',
            'background_mode',
            'background_treatment',
            'hero_height',
            'logo_size',
            'banner_intensity',
            'chat_density',
            'hero_curve',
            'carousel_style',
            'social_visibility',
            'component_style',
            'layout_template',
            'background_image_url',
            'background_overlay',
            'font_family',
            'font_scale',
            'presentation_style',
            'surface_style',
            'bubble_style',
            'user_bubble_color',
            'agent_bubble_color',
            'header_logo_url',
            'launcher_label',
            'ticker_enabled',
            'ticker_text',
            'show_featured_products',
            'instagram_url',
            'tiktok_url',
            'whatsapp_url',
            'website_url',
            'location_url',
            'ios_bundle_ids',
            'android_package_names',
            'allowed_origins',
            'auth_mode',
            'require_authentication',
            'push_enabled',
            'handoff_enabled',
        ]:
            if key in data:
                config_settings[key] = data[key]
        if 'is_active' in data:
            config.is_active = data['is_active']
            config_settings['install_status'] = 'configured' if data['is_active'] else 'not_installed'

        config.settings = config_settings
        config.save()

        response_serializer = AppChatConnectionSerializer(build_app_chat_payload(config, request))
        return Response(response_serializer.data)

    @action(
        detail=False,
        methods=['get'],
        url_path=r'appchat/public/(?P<org_slug>[^/.]+)',
        permission_classes=[AllowAny],
    )
    def appchat_public(self, request, org_slug=None):
        config = resolve_public_app_chat_config(org_slug)
        if config is None:
            return Response({'detail': 'App Chat no disponible para esta marca.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AppChatPublicSerializer(build_public_app_chat_payload(config, request))
        return Response(serializer.data)

    @action(
        detail=False,
        methods=['get'],
        url_path=r'appchat/session/(?P<org_slug>[^/.]+)/(?P<session_id>[^/.]+)',
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def appchat_session(self, request, org_slug=None, session_id=None):
        config = resolve_public_app_chat_config(org_slug)
        if config is None:
            return Response({'detail': 'App Chat no disponible para esta marca.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PublicAppChatSessionSerializer(data={'session_id': session_id})
        serializer.is_valid(raise_exception=True)
        return Response({
            'session_token': build_public_appchat_session_token(
                config.organization.slug,
                serializer.validated_data['session_id'],
            ),
            'organization_slug': config.organization.slug,
            'session_id': serializer.validated_data['session_id'],
        })

    @action(
        detail=False,
        methods=['get'],
        url_path=r'appchat/conversations/(?P<org_slug>[^/.]+)/(?P<session_id>[^/.]+)',
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def appchat_conversation(self, request, org_slug=None, session_id=None):
        serializer = AppChatConversationQuerySerializer(data={
            'session_id': session_id,
            'session_token': request.query_params.get('session_token', ''),
        })
        serializer.is_valid(raise_exception=True)
        if not validate_public_appchat_session_token(org_slug or '', serializer.validated_data['session_id'], serializer.validated_data['session_token']):
            return Response({'error': 'Invalid session token'}, status=status.HTTP_403_FORBIDDEN)
        try:
            payload = get_public_conversation_payload(
                org_slug=org_slug,
                session_id=serializer.validated_data['session_id'],
                channel='app',
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)

    @action(detail=False, methods=['get', 'patch'], url_path='database/connection')
    def database_connection(self, request):
        config = self._get_or_create_database_config(request)

        if request.method == 'GET':
            serializer = DatabaseConnectionSerializer(build_database_connection_payload(config))
            return Response(serializer.data)

        serializer = DatabaseConnectionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        config = update_database_connection_config(config, serializer.validated_data)
        response_serializer = DatabaseConnectionSerializer(build_database_connection_payload(config))
        return Response(response_serializer.data)

    @action(detail=False, methods=['post'], url_path='database/test-connection')
    def test_database_connection_action(self, request):
        config = self._get_or_create_database_config(request)
        return Response(test_database_connection(config))

    @action(detail=False, methods=['post'], url_path='database/lookup-affiliate')
    def lookup_database_affiliate(self, request):
        config = self._get_or_create_database_config(request)
        serializer = DatabaseLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = lookup_affiliate_by_document(config, serializer.validated_data['document_number'])
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result)

    @action(detail=False, methods=['post'], url_path='webapp/verify-install')
    def verify_webapp_install(self, request):
        config = self._get_or_create_web_config(request)
        config_settings = {**(config.settings or {})}
        config_settings['install_status'] = 'pending_manual_verification'
        config_settings['last_install_check_at'] = timezone.now().isoformat()
        config_settings['verified_domains'] = []
        config.settings = config_settings
        config.save(update_fields=['settings', 'updated_at'])
        return Response({
            'status': 'pending_manual_verification',
            'install_status': config_settings['install_status'],
            'verified_domains': config_settings['verified_domains'],
            'last_install_check_at': config_settings['last_install_check_at'],
        })

    @action(detail=False, methods=['post'], url_path='appchat/verify-install')
    def verify_appchat_install(self, request):
        config = self._get_or_create_app_chat_config(request)
        config_settings = {**(config.settings or {})}
        config_settings['install_status'] = 'pending_manual_verification'
        config_settings['verified_apps'] = []
        config_settings['last_install_check_at'] = timezone.now().isoformat()
        config.settings = config_settings
        config.save(update_fields=['settings', 'updated_at'])
        return Response({
            'status': 'pending_manual_verification',
            'install_status': config_settings['install_status'],
            'verified_apps': config_settings['verified_apps'],
            'last_install_check_at': config_settings['last_install_check_at'],
        })

    @action(detail=False, methods=['post'], url_path='whatsapp/verify-webhook')
    def verify_whatsapp_webhook(self, request):
        config = self._get_or_create_whatsapp_config(request)
        config_settings = {**(config.settings or {})}
        config_settings['webhook_status'] = 'verified'
        config_settings['last_webhook_received_at'] = timezone.now().isoformat()
        if not config.webhook_url:
            config.webhook_url = request.build_absolute_uri('/api/channels/whatsapp/webhook/')
        config.settings = config_settings
        config.save(update_fields=['webhook_url', 'settings', 'updated_at'])
        return Response({
            'status': 'verified',
            'webhook_url': config.webhook_url,
            'last_webhook_received_at': config_settings['last_webhook_received_at'],
        })

    @action(detail=False, methods=['post'], url_path='whatsapp/sync-templates')
    def sync_whatsapp_templates_action(self, request):
        config = self._get_or_create_whatsapp_config(request)
        config_settings = {**(config.settings or {})}
        config_settings['template_sync_status'] = 'pending'
        config_settings['last_sync_at'] = timezone.now().isoformat()
        config.settings = config_settings
        config.save(update_fields=['settings', 'updated_at'])
        try:
            from tasks.channel_tasks import sync_whatsapp_templates
            sync_whatsapp_templates.delay(str(request.user.organization_id))
        except Exception:
            pass
        return Response({'status': 'pending', 'last_sync_at': config_settings['last_sync_at']})

    @action(detail=False, methods=['post'], url_path='whatsapp/simulate-inbound')
    def simulate_whatsapp_inbound(self, request):
        serializer = WhatsAppSimulateInboundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = self._get_or_create_whatsapp_config(request)
        creds = config.credentials or {}
        phone_number_id = creds.get('phone_number_id')
        if not phone_number_id:
            return Response({'error': 'WhatsApp connection is not configured'}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            'object': 'whatsapp_business_account',
            'entry': [
                {
                    'changes': [
                        {
                            'value': {
                                'metadata': {
                                    'phone_number_id': phone_number_id,
                                },
                                'messages': [
                                    {
                                        'from': serializer.validated_data['phone'],
                                        'id': f'sim-{timezone.now().timestamp()}',
                                        'type': serializer.validated_data.get('message_type', 'text') or 'text',
                                        'text': {'body': serializer.validated_data['message']},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ],
        }

        from tasks.channel_tasks import process_incoming_webhook

        result = process_incoming_webhook(payload, 'whatsapp', str(request.user.organization_id))
        return Response({'status': 'processed', 'result': result})

    @action(
        detail=False,
        methods=['post'],
        url_path='webchat/messages',
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def webchat_messages(self, request):
        serializer = WebChatInboundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = create_inbound_conversation(
                data=serializer.validated_data,
                channel='web',
                source='web_widget',
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=['post'],
        url_path='appchat/messages',
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def appchat_messages(self, request):
        serializer = AppChatInboundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = create_inbound_conversation(
                data=serializer.validated_data,
                channel='app',
                source='app_chat',
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)
