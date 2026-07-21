"""
Production settings — hardened security, JSON logging, S3 media.
Never commit actual secrets here; all values must come from env vars.
"""
from .base import *  # noqa: F401, F403

DEBUG = False

# ─── Static files: WhiteNoise ──────────────────────────────────────────────────
# Railway runs the container directly behind its edge proxy — there's no
# separate web server (nginx) or CDN serving /static/, so without WhiteNoise
# collectstatic writes files that nothing ever serves (this is why Django
# admin loaded with no CSS).
# Django 5's STORAGES dict and the legacy STATICFILES_STORAGE setting are
# mutually exclusive — base.py already defines STORAGES (media → S3/R2 when
# USE_S3 is set), so only the 'staticfiles' entry is overridden here rather
# than reassigning STATICFILES_STORAGE.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
] + MIDDLEWARE[1:]  # noqa: F405
STORAGES = globals().get('STORAGES', {  # noqa: F405
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
})
STORAGES['staticfiles'] = {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}

# ─── Security headers ──────────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# Railway's internal healthcheck probes hit the container over plain HTTP
# (no X-Forwarded-Proto) — exempt /health so it isn't 301-redirected.
SECURE_REDIRECT_EXEMPT = [r'^health$']
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# ─── Logging: JSON to file + console ────────────────────────────────────────────
LOGGING['root']['handlers'] = ['console', 'json_file']  # noqa: F405

# ─── Cache: longer TTL in prod ──────────────────────────────────────────────────
CACHES['default']['TIMEOUT'] = 600  # noqa: F405

# ─── Email: SendGrid over HTTPS (not raw SMTP) ─────────────────────────────────
# Railway blocks outbound SMTP (ports 25/465/587) at the network level — every
# raw-SMTP attempt (SendGrid, Gmail) either hangs until timeout or fails
# immediately with "Network is unreachable". SendGrid's Web API runs over
# HTTPS/443, which isn't blocked.
import os
EMAIL_BACKEND = 'sendgrid_backend.SendgridBackend'
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')
SENDGRID_SANDBOX_MODE_IN_DEBUG = False

# ─── Admin URL: obscure it from brute-force bots ───────────────────────────────
ADMIN_URL = os.environ.get('ADMIN_URL', 'vendly-admin-2026/')

# ─── Use S3 if configured ──────────────────────────────────────────────────────
# USE_S3=True in env will activate S3 storage configured in base.py

# ─── DRF rate limits: stricter in prod ─────────────────────────────────────────
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {  # noqa: F405
    'anon': '20/min',
    'user': '300/min',
}

# ─── Celery: larger concurrency in prod ────────────────────────────────────────
CELERY_WORKER_CONCURRENCY = int(os.environ.get('CELERY_CONCURRENCY', '8'))
