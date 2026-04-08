"""
WebSocket URL patterns for Vendly Inbox.
Registered in config/asgi.py via ProtocolTypeRouter.
"""
from django.urls import re_path

from .consumers import InboxConsumer, PublicAppChatConsumer, PublicWebChatConsumer

# Private patterns — go through AllowedHostsOriginValidator
private_websocket_urlpatterns = [
    re_path(r'^ws/inbox/$', InboxConsumer.as_asgi()),
    re_path(r'^ws/inbox$', InboxConsumer.as_asgi()),
    re_path(r'^ws/notifications/$', InboxConsumer.as_asgi()),
    re_path(r'^ws/notifications$', InboxConsumer.as_asgi()),
]

# Public patterns — bypass AllowedHostsOriginValidator (cross-origin from customer sites)
public_websocket_urlpatterns = [
    re_path(r'^ws/appchat/(?P<org_slug>[^/]+)/(?P<session_id>[^/]+)/$', PublicAppChatConsumer.as_asgi()),
    re_path(r'^ws/appchat/(?P<org_slug>[^/]+)/(?P<session_id>[^/]+)$', PublicAppChatConsumer.as_asgi()),
    re_path(r'^ws/webchat/(?P<org_slug>[^/]+)/(?P<session_id>[^/]+)/$', PublicWebChatConsumer.as_asgi()),
    re_path(r'^ws/webchat/(?P<org_slug>[^/]+)/(?P<session_id>[^/]+)$', PublicWebChatConsumer.as_asgi()),
]

# Combined for backwards compatibility
websocket_urlpatterns = private_websocket_urlpatterns + public_websocket_urlpatterns
