"""
WebSocket URL patterns for Vendly Inbox.
Registered in config/asgi.py via ProtocolTypeRouter.
"""
from django.urls import re_path
from .consumers import InboxConsumer

websocket_urlpatterns = [
    # Main inbox — real-time conversation + message updates
    re_path(r'^ws/inbox/$', InboxConsumer.as_asgi()),

    # Notification stream — platform-level alerts
    re_path(r'^ws/notifications/$', InboxConsumer.as_asgi()),
]
