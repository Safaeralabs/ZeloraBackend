"""
JWT WebSocket Authentication Middleware.

Authenticates WebSocket connections by reading a JWT token from:
  1. WebSocket subprotocol: "vendly-jwt.<access_token>"

Usage in asgi.py:
    JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
"""
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_user_from_token(token_key: str):
    """Validate JWT access token and return the corresponding User or AnonymousUser."""
    try:
        from rest_framework_simplejwt.tokens import UntypedToken
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
        from rest_framework_simplejwt.settings import api_settings
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Validate the token (raises on failure)
        UntypedToken(token_key)

        # Decode payload to get user_id
        import jwt as pyjwt
        from django.conf import settings

        decoded = pyjwt.decode(
            token_key,
            settings.SECRET_KEY,
            algorithms=[api_settings.ALGORITHM],
        )
        user_id = decoded.get(api_settings.USER_ID_CLAIM)
        if not user_id:
            return AnonymousUser()

        user = User.objects.select_related('organization').get(pk=user_id)
        return user if user.is_active else AnonymousUser()

    except Exception:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Channels middleware that authenticates WebSocket connections via JWT.
    Sets scope['user'] before the consumer handles the connection.
    """

    async def __call__(self, scope, receive, send):
        token = None

        subprotocols = scope.get('subprotocols') or []
        for protocol in subprotocols:
            if isinstance(protocol, str) and protocol.startswith('vendly-jwt.'):
                token = protocol.removeprefix('vendly-jwt.')
                break

        if token:
            scope['user'] = await _get_user_from_token(token)
        else:
            scope['user'] = AnonymousUser()

        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    """Convenience wrapper — mirrors AuthMiddlewareStack but uses JWT."""
    return JWTAuthMiddleware(inner)
