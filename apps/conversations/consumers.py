"""
Vendly — InboxConsumer (Django Channels WebSocket)

Handles real-time inbox updates for agents:
  - Authenticates via JWT token in WebSocket subprotocol
  - Joins org-specific group: "org_{org_id}"
  - Joins user-specific group: "user_{user_id}"
  - Broadcasts: new_message, status_changed, agent_typing events
  - Handles ping/pong heartbeats
  - Auto-closes unauthenticated connections
"""
import json
import structlog
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from apps.channels_config.public_session import validate_public_appchat_session_token

logger = structlog.get_logger(__name__)


def build_public_appchat_group(org_slug: str, session_id: str) -> str:
    normalized_org = ''.join(char if char.isalnum() else '-' for char in (org_slug or '').lower())
    normalized_session = ''.join(char if char.isalnum() else '-' for char in (session_id or '').lower())
    return f'appchat-{normalized_org}-{normalized_session}'[:100]


class InboxConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for the Vendly Inbox module.

    Groups:
      - org_{org_id}    — all agents in the same organization
      - user_{user_id}  — private messages to a specific agent

    Client → Server events:
      { "type": "ping" }
      { "type": "agent_typing", "conversation_id": "<uuid>" }

    Server → Client events:
      { "type": "pong" }
      { "type": "new_message",      "conversation_id": "...", "message": {...} }
      { "type": "status_changed",   "conversation_id": "...", "estado": "..." }
      { "type": "conversation_assigned", "conversation_id": "...", "agent": "..." }
      { "type": "agent_typing",     "conversation_id": "...", "agent_id": "..." }
      { "type": "notification",     "message": "...", "level": "info|warning|error" }
    """

    async def connect(self):
        # ── 1. Extract JWT from query params ──────────────────────────────────
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            logger.warning('ws_auth_missing_token', path=self.scope.get('path'))
            await self.close(code=4001)
            return

        org_id = str(user.organization_id) if user.organization_id else None
        if not org_id:
            await self.close(code=4002)
            return

        self.user = user
        self.org_id = org_id

        # ── 2. Set up channel groups ───────────────────────────────────────────
        self.org_group = f'org_{self.org_id}'
        self.user_group = f'user_{self.user.id}'

        await self.channel_layer.group_add(self.org_group, self.channel_name)
        await self.channel_layer.group_add(self.user_group, self.channel_name)

        await self.accept(subprotocol='vendly-ws')

        # ── 3. Send welcome event with agent info ──────────────────────────────
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'agent_id': str(self.user.id),
            'org_id': self.org_id,
            'nombre': self.user.nombre,
            'rol': self.user.rol,
        }))

        logger.info(
            'ws_connected',
            user_id=str(self.user.id),
            org_id=self.org_id,
            channel=self.channel_name,
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'org_group'):
            await self.channel_layer.group_discard(self.org_group, self.channel_name)
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

        user = getattr(self, 'user', None)
        user_id = getattr(user, 'id', 'unknown')
        logger.info('ws_disconnected', user_id=str(user_id or 'unknown'), close_code=close_code)

    async def receive(self, text_data):
        """Handle messages from the WebSocket client."""
        try:
            data = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'detail': 'Invalid JSON payload',
            }))
            return

        event_type = data.get('type')

        if event_type == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

        elif event_type == 'agent_typing':
            # Broadcast typing indicator to all agents in org
            conversation_id = data.get('conversation_id')
            if conversation_id and hasattr(self, 'org_group'):
                await self.channel_layer.group_send(
                    self.org_group,
                    {
                        'type': 'agent.typing',
                        'conversation_id': conversation_id,
                        'agent_id': str(self.user.id),
                        'agent_nombre': self.user.nombre,
                    }
                )

        elif event_type == 'mark_read':
            # Client acknowledges reading a conversation — update unread count in future
            pass

        else:
            logger.debug('ws_unknown_event', event_type=event_type)

    # ── Group message handlers (called by channel_layer.group_send) ────────────

    async def conversation_updated(self, event):
        """Generic conversation update event — forwards to WebSocket client."""
        await self.send(text_data=json.dumps({
            'type': event.get('event', 'conversation_updated'),
            'conversation_id': event.get('conversation_id'),
            'data': event.get('data', {}),
        }))

    async def conversation_message(self, event):
        """New message arrived in a conversation."""
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'conversation_id': event.get('conversation_id'),
            'message': event.get('message', {}),
        }))

    async def status_changed(self, event):
        """Conversation status changed (escalated, resolved, etc.)."""
        await self.send(text_data=json.dumps({
            'type': 'status_changed',
            'conversation_id': event.get('conversation_id'),
            'estado': event.get('estado'),
            'previous_estado': event.get('previous_estado'),
        }))

    async def conversation_assigned(self, event):
        """Conversation assigned to an agent."""
        await self.send(text_data=json.dumps({
            'type': 'conversation_assigned',
            'conversation_id': event.get('conversation_id'),
            'agent': event.get('agent'),
        }))

    async def agent_typing(self, event):
        """Typing indicator from another agent."""
        # Don't send back to the agent who triggered it
        if str(getattr(self, 'user', {}).id or '') != str(event.get('agent_id', '')):
            await self.send(text_data=json.dumps({
                'type': 'agent_typing',
                'conversation_id': event.get('conversation_id'),
                'agent_id': event.get('agent_id'),
                'agent_nombre': event.get('agent_nombre'),
            }))

    async def new_notification(self, event):
        """Platform notification (campaign sent, SLA breach, etc.)."""
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'message': event.get('message'),
            'level': event.get('level', 'info'),
            'data': event.get('data', {}),
        }))


@database_sync_to_async
def _resolve_public_appchat_scope(org_slug: str):
    from apps.channels_config.models import ChannelConfig

    config = ChannelConfig.objects.select_related('organization').filter(
        organization__slug=org_slug,
        organization__is_active=True,
        channel='app',
        is_active=True,
    ).first()
    if config is None:
        return None
    return {
        'organization_id': str(config.organization_id),
        'organization_slug': config.organization.slug,
    }


class PublicAppChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        route_kwargs = self.scope.get('url_route', {}).get('kwargs', {})
        query_string = self.scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        requested_org_slug = route_kwargs.get('org_slug', '')
        session_id = route_kwargs.get('session_id', '')
        session_token = (params.get('session_token', ['']) or [''])[0]

        if not requested_org_slug or not session_id:
            await self.close(code=4004)
            return
        if not validate_public_appchat_session_token(requested_org_slug, session_id, session_token):
            await self.close(code=4003)
            return

        resolved_scope = await _resolve_public_appchat_scope(requested_org_slug)
        if resolved_scope is None:
            await self.close(code=4004)
            return

        self.organization_id = resolved_scope['organization_id']
        self.organization_slug = resolved_scope['organization_slug']
        self.session_id = session_id
        self.public_group = build_public_appchat_group(self.organization_slug, self.session_id)

        await self.channel_layer.group_add(self.public_group, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'session_id': self.session_id,
            'organization_slug': self.organization_slug,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'public_group'):
            await self.channel_layer.group_discard(self.public_group, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            return
        if data.get('type') == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

    async def appchat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'conversation_id': event.get('conversation_id'),
            'session_id': event.get('session_id'),
            'message': event.get('message', {}),
        }))
