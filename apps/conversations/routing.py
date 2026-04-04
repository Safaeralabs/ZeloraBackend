"""
WebSocket URL patterns for Vendly Inbox.
Registered in config/asgi.py via ProtocolTypeRouter.
"""
from django.urls import re_path

from .consumers import InboxConsumer, PublicAppChatConsumer


websocket_urlpatterns = [
    re_path(r'^ws/inbox/$', InboxConsumer.as_asgi()),
    re_path(r'^ws/inbox$', InboxConsumer.as_asgi()),
    re_path(r'^ws/notifications/$', InboxConsumer.as_asgi()),
    re_path(r'^ws/notifications$', InboxConsumer.as_asgi()),
    re_path(r'^ws/appchat/(?P<org_slug>[^/]+)/(?P<session_id>[^/]+)/$', PublicAppChatConsumer.as_asgi()),
    re_path(r'^ws/appchat/(?P<org_slug>[^/]+)/(?P<session_id>[^/]+)$', PublicAppChatConsumer.as_asgi()),
]
