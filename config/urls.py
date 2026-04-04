"""
Vendly — Root URL configuration.

API structure:
  /api/auth/         → JWT auth, agents, contacts, org settings
  /api/conversations/ → inbox conversations + messages
  /api/channels/     → channel configs + webhook receivers
  /api/kb/           → knowledge base articles + documents
  /api/campaigns/    → templates + campaigns
  /api/flows/        → conversation automation flows
  /api/analytics/    → metrics and reports
  /api/ai/           → AI workspace (copilot, insights, memory, tasks)
  /api/billing/      → plans + subscriptions
  /api/ecommerce/    → products, orders, inventory
  /api/workspace/    → collab notes + agent performance
  /api/schema/       → OpenAPI schema
  /api/docs/         → Swagger UI
  /ws/               → WebSocket consumers (handled by ASGI, not Django URL router)
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)


def health_check(request):
    """Lightweight health check for load balancers / Docker healthcheck."""
    from django.db import connection
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse({
        'status': 'ok' if db_ok else 'degraded',
        'version': '2.0.0',
        'service': 'vendly-api',
        'db': 'connected' if db_ok else 'error',
    }, status=200 if db_ok else 503)


urlpatterns = [
    # ── Django admin ───────────────────────────────────────────────────────────
    path(
        getattr(settings, 'ADMIN_URL', 'admin/'),
        admin.site.urls,
    ),

    # ── Health check ───────────────────────────────────────────────────────────
    path('health', health_check, name='health'),

    # ── OpenAPI / Swagger ──────────────────────────────────────────────────────
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # ── Application APIs ───────────────────────────────────────────────────────
    # Auth: /api/auth/login/, /api/auth/signup/, /api/auth/token/refresh/
    #        /api/auth/agents/, /api/auth/contacts/, /api/auth/organization/
    path('api/auth/', include('apps.accounts.urls')),

    # Conversations + Messages: /api/conversations/
    path('api/conversations/', include('apps.conversations.urls')),

    # Channel configs + Webhooks: /api/channels/
    path('api/channels/', include('apps.channels_config.urls')),

    # Knowledge Base: /api/kb/articles/, /api/kb/documents/
    path('api/kb/', include('apps.knowledge_base.urls')),

    # Campaigns + Templates: /api/campaigns/
    path('api/campaigns/', include('apps.campaigns.urls')),

    # Flows: /api/flows/
    path('api/flows/', include('apps.flows.urls')),

    # Analytics: /api/analytics/overview/, /api/analytics/channels/, /api/analytics/intents/
    path('api/analytics/', include('apps.analytics.urls')),

    # AI Engine / Workspace: /api/ai/copilot/, /api/ai/insights/, /api/ai/memory/, etc.
    path('api/ai/', include('apps.ai_engine.urls')),

    # Billing: /api/billing/plans/, /api/billing/subscriptions/
    path('api/billing/', include('apps.billing.urls')),

    # E-commerce: /api/ecommerce/products/, /api/ecommerce/orders/, /api/ecommerce/inventory/
    path('api/ecommerce/', include('apps.ecommerce.urls')),

    # Workspace: /api/workspace/notes/, /api/workspace/agent-performance/
    path('api/workspace/', include('apps.workspace.urls')),
]

# ── Development extras ──────────────────────────────────────────────────────────
if settings.DEBUG:
    # Serve media files locally in development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Django Debug Toolbar
    try:
        import debug_toolbar
        urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
