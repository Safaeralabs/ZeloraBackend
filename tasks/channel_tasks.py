"""
Channel-specific Celery tasks:
  - send_whatsapp_message       — Send a message via Meta WhatsApp Cloud API
  - process_incoming_webhook    — Process incoming webhook payload from any channel
  - sync_whatsapp_templates     — Sync approved templates from Meta to DB
"""
import structlog
import httpx
from celery import shared_task
from django.utils import timezone

logger = structlog.get_logger(__name__)

WHATSAPP_API_VERSION = 'v19.0'
WHATSAPP_BASE_URL = 'https://graph.facebook.com'


@shared_task(
    bind=True,
    name='tasks.channel_tasks.send_whatsapp_message',
    max_retries=3,
    default_retry_delay=30,
    queue='channels',
)
def send_whatsapp_message(
    self,
    phone: str,
    message: str,
    org_id: str,
    conv_id: str | None = None,
    message_type: str = 'text',
) -> dict:
    """
    Send a WhatsApp message via Meta Cloud API.

    Requires the organization to have a ChannelConfig(canal='whatsapp') with:
      credentials.api_token        — Meta access token
      credentials.phone_number_id  — WhatsApp phone number ID

    Args:
        phone:        Recipient phone number (E.164, no +)
        message:      Text content to send
        org_id:       Organization UUID
        conv_id:      Optional conversation UUID (for tracking)
        message_type: 'text' (other types: 'template' — extend as needed)
    """
    try:
        from apps.channels_config.models import ChannelConfig

        cfg = ChannelConfig.objects.get(
            organization_id=org_id,
            channel='whatsapp',
            is_active=True,
        )

        creds = cfg.credentials
        api_token = creds.get('api_token') or creds.get('access_token', '')
        phone_number_id = creds.get('phone_number_id', '')

        if not api_token or not phone_number_id:
            raise ValueError(f'WhatsApp credentials incomplete for org {org_id}')

        url = f'{WHATSAPP_BASE_URL}/{WHATSAPP_API_VERSION}/{phone_number_id}/messages'
        headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json',
        }
        payload = {
            'messaging_product': 'whatsapp',
            'to': phone,
            'type': 'text',
            'text': {'body': message, 'preview_url': False},
        }

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        wa_msg_id = data.get('messages', [{}])[0].get('id', '')

        logger.info(
            'whatsapp_sent',
            phone=phone[-4:],  # Log only last 4 digits for PII safety
            org_id=org_id,
            wa_msg_id=wa_msg_id,
            conv_id=conv_id,
        )
        return {'status': 'ok', 'wa_message_id': wa_msg_id}

    except httpx.HTTPStatusError as exc:
        logger.error(
            'whatsapp_send_http_error',
            status=exc.response.status_code,
            body=exc.response.text[:500],
            phone=phone[-4:],
        )
        raise self.retry(exc=exc)

    except httpx.RequestError as exc:
        logger.error('whatsapp_send_network_error', error=str(exc))
        raise self.retry(exc=exc)

    except Exception as exc:
        logger.error('whatsapp_send_fatal', error=str(exc), exc_info=True)
        raise


@shared_task(
    bind=True,
    name='tasks.channel_tasks.process_incoming_webhook',
    max_retries=2,
    default_retry_delay=5,
    queue='channels',
)
def process_incoming_webhook(self, payload: dict, canal: str, org_id: str) -> dict:
    """
    Process an incoming webhook from any channel.

    For WhatsApp, parses the Meta webhook payload:
      - Extracts sender phone + message text
      - Gets or creates Contact
      - Gets or creates open Conversation
      - Creates Message record (deduplication via wa_id)
      - Triggers AI bot response (ai_tasks.generate_bot_response)
      - Broadcasts WebSocket event to org group

    Args:
        payload: Raw webhook JSON body (already deserialized)
        canal:   Channel name ('whatsapp', 'instagram', etc.)
        org_id:  Organization UUID string
    """
    try:
        from apps.conversations.models import Conversation, Message
        from apps.accounts.models import Contact
        from apps.accounts.models import Organization

        org = Organization.objects.get(id=org_id)

        if canal == 'whatsapp':
            return _process_whatsapp_webhook(payload, org)
        elif canal == 'instagram':
            return _process_instagram_webhook(payload, org)
        else:
            logger.warning('webhook_unsupported_canal', canal=canal)
            return {'status': 'skipped', 'reason': f'canal {canal} not implemented'}

    except Exception as exc:
        logger.error('webhook_process_error', canal=canal, error=str(exc), exc_info=True)
        raise self.retry(exc=exc)


def _process_whatsapp_webhook(payload: dict, org) -> dict:
    """Handle WhatsApp Business Cloud API webhook payload."""
    from apps.conversations.models import Conversation, Message
    from apps.accounts.models import Contact

    processed = 0

    try:
        entries = payload.get('entry', [])
        for entry in entries:
            for change in entry.get('changes', []):
                value = change.get('value', {})
                messages = value.get('messages', [])

                for msg_data in messages:
                    phone = msg_data.get('from', '')
                    msg_type = msg_data.get('type', 'text')
                    wa_msg_id = msg_data.get('id', '')

                    # Extract text content
                    if msg_type == 'text':
                        text = msg_data.get('text', {}).get('body', '')
                    elif msg_type == 'image':
                        text = '[Imagen recibida]'
                    elif msg_type == 'audio':
                        text = '[Audio recibido]'
                    elif msg_type == 'document':
                        text = '[Documento recibido]'
                    elif msg_type == 'location':
                        loc = msg_data.get('location', {})
                        text = f'[Ubicación: {loc.get("latitude", 0)}, {loc.get("longitude", 0)}]'
                    else:
                        text = f'[Mensaje tipo: {msg_type}]'

                    if not phone:
                        continue

                    # Deduplication
                    if wa_msg_id and Message.objects.filter(metadata__wa_id=wa_msg_id).exists():
                        logger.debug('webhook_duplicate_msg', wa_msg_id=wa_msg_id)
                        continue

                    # Get or create Contact
                    contact, _ = Contact.objects.get_or_create(
                        organization=org,
                        telefono=phone,
                        defaults={
                            'nombre': phone,
                            'apellido': '',
                        },
                    )

                    # Get or create open Conversation
                    conv = _get_or_create_open_conversation(org, contact, 'whatsapp')

                    # Save incoming message
                    Message.objects.create(
                        conversation=conv,
                        role='user',
                        content=text,
                        metadata={'wa_id': wa_msg_id, 'channel': 'whatsapp', 'msg_type': msg_type},
                    )

                    conv.updated_at = timezone.now()
                    conv.save(update_fields=['updated_at'])

                    # Trigger AI bot response
                    try:
                        from tasks.ai_tasks import generate_bot_response
                        generate_bot_response.delay(str(conv.id), text)
                    except Exception as e:
                        logger.warning('bot_response_trigger_error', error=str(e))

                    # Broadcast to agents
                    _broadcast_new_message_event(org.id, conv.id)
                    processed += 1

    except Exception as exc:
        logger.error('whatsapp_webhook_parse_error', error=str(exc), exc_info=True)
        raise

    logger.info('whatsapp_webhook_processed', org_id=str(org.id), messages=processed)
    return {'status': 'ok', 'messages_processed': processed}


def _process_instagram_webhook(payload: dict, org) -> dict:
    """Placeholder for Instagram DM webhook — extend as needed."""
    logger.info('instagram_webhook_received', org_id=str(org.id))
    return {'status': 'ok', 'note': 'instagram handler placeholder'}


def _get_or_create_open_conversation(org, contact, canal: str):
    """Find an open conversation for this contact/channel or create a new one."""
    from apps.conversations.models import Conversation

    conv = Conversation.objects.filter(
        organization=org,
        contact=contact,
        canal=canal,
        estado__in=['nuevo', 'en_proceso'],
    ).first()

    if not conv:
        conv = Conversation.objects.create(
            organization=org,
            contact=contact,
            canal=canal,
            estado='nuevo',
            intent='Consulta entrante',
            sentimiento='neutro',
        )

    return conv


def _broadcast_new_message_event(org_id, conv_id):
    """Broadcast a WebSocket event to all agents in the org."""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        async_to_sync(channel_layer.group_send)(
            f'org_{org_id}',
            {
                'type': 'conversation.updated',
                'event': 'new_message',
                'conversation_id': str(conv_id),
            }
        )
    except Exception as e:
        logger.warning('ws_broadcast_error', error=str(e))


@shared_task(
    name='tasks.channel_tasks.sync_whatsapp_templates',
    queue='channels',
)
def sync_whatsapp_templates(org_id: str) -> dict:
    """
    Sync approved WhatsApp templates from Meta to local Template records.
    Call this after updating templates in Meta Business Manager.
    """
    try:
        from apps.channels_config.models import ChannelConfig
        from apps.campaigns.models import Template

        cfg = ChannelConfig.objects.get(
            organization_id=org_id,
            channel='whatsapp',
            is_active=True,
        )
        creds = cfg.credentials
        api_token = creds.get('api_token', '')
        waba_id = creds.get('waba_id', '')

        if not api_token or not waba_id:
            return {'status': 'skipped', 'reason': 'missing credentials'}

        url = f'{WHATSAPP_BASE_URL}/{WHATSAPP_API_VERSION}/{waba_id}/message_templates'
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers={'Authorization': f'Bearer {api_token}'})
            resp.raise_for_status()
            data = resp.json()

        synced = 0
        for tpl in data.get('data', []):
            status = tpl.get('status', '').lower()
            Template.objects.update_or_create(
                organization_id=org_id,
                external_id=tpl['id'],
                defaults={
                    'name': tpl.get('name', ''),
                    'content': str(tpl.get('components', [])),
                    'channel': 'whatsapp',
                    'status': 'approved' if status == 'approved' else 'draft',
                },
            )
            synced += 1

        logger.info('whatsapp_templates_synced', org_id=org_id, count=synced)
        return {'status': 'ok', 'templates_synced': synced}

    except Exception as exc:
        logger.error('sync_templates_error', org_id=org_id, error=str(exc))
        raise
