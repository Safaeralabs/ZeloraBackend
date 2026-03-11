"""
ASGI config for Vendly.
Handles both HTTP (Django) and WebSocket (Django Channels) traffic.
WebSocket connections are authenticated via JWT token in query params.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.core.asgi import get_asgi_application  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.conversations.routing import websocket_urlpatterns  # noqa: E402
from core.ws_auth import JWTAuthMiddlewareStack  # noqa: E402

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    # Standard HTTP — served by Django
    'http': django_asgi_app,

    # WebSocket — authenticated via JWT, scoped to org channel groups
    'websocket': AllowedHostsOriginValidator(
        JWTAuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
