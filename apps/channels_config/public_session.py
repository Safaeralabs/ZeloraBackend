from __future__ import annotations

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

PUBLIC_APPCHAT_SESSION_SALT = 'vendly.appchat.public-session'
PUBLIC_APPCHAT_SESSION_MAX_AGE_SECONDS = 60 * 60 * 12


def build_public_appchat_session_token(org_slug: str, session_id: str) -> str:
    signer = TimestampSigner(salt=PUBLIC_APPCHAT_SESSION_SALT)
    return signer.sign(f'{org_slug}:{session_id}')


def validate_public_appchat_session_token(org_slug: str, session_id: str, token: str | None) -> bool:
    if not token:
        return False
    signer = TimestampSigner(salt=PUBLIC_APPCHAT_SESSION_SALT)
    try:
        value = signer.unsign(
            token,
            max_age=getattr(settings, 'PUBLIC_APPCHAT_SESSION_MAX_AGE_SECONDS', PUBLIC_APPCHAT_SESSION_MAX_AGE_SECONDS),
        )
    except (BadSignature, SignatureExpired):
        return False
    return value == f'{org_slug}:{session_id}'
