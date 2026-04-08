"""
ASGI config for Vendly.
Handles both HTTP (Django) and WebSocket (Django Channels) traffic.

Private WebSocket paths (inbox, notifications) are protected by AllowedHostsOriginValidator.
Public WebSocket paths (appchat, webchat) bypass origin validation so customer sites
can connect from their own domains (widget.js embeds).
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.core.asgi import get_asgi_application  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.conversations.routing import (  # noqa: E402
    private_websocket_urlpatterns,
    public_websocket_urlpatterns,
)
from core.ws_auth import JWTAuthMiddlewareStack  # noqa: E402

django_asgi_app = get_asgi_application()

# Private: origin-validated, JWT-authenticated (inbox/notifications)
_private_ws = AllowedHostsOriginValidator(
    JWTAuthMiddlewareStack(URLRouter(private_websocket_urlpatterns))
)

# Public: no origin check, session-token-authenticated (appchat/webchat from customer domains)
_public_ws = JWTAuthMiddlewareStack(URLRouter(public_websocket_urlpatterns))

_PUBLIC_WS_PREFIXES = ('/ws/webchat/', '/ws/appchat/')


class _PublicWebSocketMiddleware:
    """Route public WebSocket paths to the origin-unrestricted handler."""

    def __init__(self, private_app, public_app):
        self._private = private_app
        self._public = public_app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            path = scope.get('path', '')
            for prefix in _PUBLIC_WS_PREFIXES:
                if path.startswith(prefix):
                    return await self._public(scope, receive, send)
        return await self._private(scope, receive, send)


application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': _PublicWebSocketMiddleware(_private_ws, _public_ws),
})
