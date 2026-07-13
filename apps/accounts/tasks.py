"""
Accounts Celery tasks.

Email sending (verification, password reset) is dispatched here instead of
inline in the request/response cycle. SMTP against a misconfigured or
unreachable host can block for tens of seconds — long enough that the
gateway kills the HTTP request before Django ever responds, which the
browser then reports as a bare CORS failure (no response == no CORS
headers). Running it via Celery means a slow/broken mail provider can never
stall signup, resend-verification, or password-reset requests.
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

try:
    from tasks.celery_app import app as celery_app

    @celery_app.task(
        name='accounts.tasks.send_verification_email',
        ignore_result=True,
        queue='default',
    )
    def send_verification_email_task(user_id: str) -> None:
        from django.contrib.auth import get_user_model
        from .email_utils import send_verification_email

        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return
        try:
            send_verification_email(user)
        except Exception as exc:
            logger.warning('verification_email_task_failed', user_id=user_id, error=str(exc))

    @celery_app.task(
        name='accounts.tasks.send_password_reset_email',
        ignore_result=True,
        queue='default',
    )
    def send_password_reset_email_task(user_id: str) -> None:
        from django.contrib.auth import get_user_model
        from .email_utils import send_password_reset_email

        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return
        try:
            send_password_reset_email(user)
        except Exception as exc:
            logger.warning('password_reset_email_task_failed', user_id=user_id, error=str(exc))

except ImportError:
    send_verification_email_task = None  # type: ignore[assignment]
    send_password_reset_email_task = None  # type: ignore[assignment]
