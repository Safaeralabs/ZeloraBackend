"""Organization-level URL — /api/auth/organization/ is the primary endpoint."""
from django.urls import path
from apps.accounts.views import OrganizationView

urlpatterns = [
    path('', OrganizationView.as_view(), name='organization-detail'),
]
