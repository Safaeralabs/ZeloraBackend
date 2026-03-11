"""
Production settings — hardened security, JSON logging, S3 media.
Never commit actual secrets here; all values must come from env vars.
"""
from .base import *  # noqa: F401, F403

DEBUG = False

# ─── Security headers ──────────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
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

# ─── Email: production SMTP ─────────────────────────────────────────────────────
import os
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

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
