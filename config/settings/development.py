"""
Development settings — DEBUG on, relaxed security, console logging.
"""
from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ['*']

# ─── Email (console backend for dev) ───────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ─── Database can use SQLite for quick local runs (override in .env) ───────────
# Leave PostgreSQL as default — devs should run docker-compose up postgres redis

# ─── Django Debug Toolbar (optional) ───────────────────────────────────────────
try:
    import debug_toolbar  # noqa: F401
    INSTALLED_APPS += ['debug_toolbar']  # noqa: F405
    MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE  # noqa: F405
    INTERNAL_IPS = ['127.0.0.1', '::1']
    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': lambda _: DEBUG,
    }
except ImportError:
    pass

# ─── Logging: verbose console only ─────────────────────────────────────────────
LOGGING['root']['handlers'] = ['console']  # noqa: F405
LOGGING['loggers']['apps']['level'] = 'DEBUG'  # noqa: F405

# ─── JWT: shorter tokens for faster dev iteration ──────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {  # noqa: F405
    **SIMPLE_JWT,  # noqa: F405
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=12),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}

# ─── CORS: allow all in dev ─────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True

# ─── Feature flags: enable AI copilot in dev ────────────────────────────────────
ENABLE_REAL_AI = False
DEMO_MODE = True
