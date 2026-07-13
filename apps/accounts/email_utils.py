from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

VERIFICATION_EXPIRY_HOURS = 24
PASSWORD_RESET_EXPIRY_HOURS = 1


def send_verification_email(user) -> 'EmailVerificationToken':  # noqa: F821
    from .models import EmailVerificationToken

    token_obj = EmailVerificationToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(hours=VERIFICATION_EXPIRY_HOURS),
    )

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')
    verify_url = f"{frontend_url}/verify-email?token={token_obj.token}"

    html_body = render_to_string('emails/verify_email.html', {
        'user': user,
        'verify_url': verify_url,
        'expiry_hours': VERIFICATION_EXPIRY_HOURS,
        'logo_url': f'{frontend_url}/email-logo-mark.png',
    })

    send_mail(
        subject='Verifica tu correo electrónico — Zelora',
        message=f'Visita este enlace para verificar tu email: {verify_url}',
        from_email=None,
        recipient_list=[user.email],
        html_message=html_body,
        fail_silently=False,
    )

    return token_obj


def send_password_reset_email(user) -> 'PasswordResetToken':  # noqa: F821
    from .models import PasswordResetToken

    token_obj = PasswordResetToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(hours=PASSWORD_RESET_EXPIRY_HOURS),
    )

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')
    reset_url = f"{frontend_url}/reset-password?token={token_obj.token}"

    html_body = render_to_string('emails/password_reset.html', {
        'user': user,
        'reset_url': reset_url,
        'expiry_hours': PASSWORD_RESET_EXPIRY_HOURS,
        'logo_url': f'{frontend_url}/email-logo-mark.png',
    })

    send_mail(
        subject='Restablece tu contraseña — Zelora',
        message=f'Visita este enlace para crear una nueva contraseña: {reset_url}',
        from_email=None,
        recipient_list=[user.email],
        html_message=html_body,
        fail_silently=False,
    )

    return token_obj
