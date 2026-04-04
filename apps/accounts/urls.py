"""
Accounts URL configuration.

/api/auth/login/                → POST — JWT login
/api/auth/signup/               → POST — Create org + admin user
/api/auth/token/refresh/        → POST — Refresh JWT
/api/auth/agents/               → GET (admin), POST (admin) — agent list/create
/api/auth/agents/{id}/          → GET/PUT/PATCH/DELETE — agent detail
/api/auth/agents/me/            → GET/PUT/PATCH — current agent profile
/api/auth/agents/change_password/ → POST — change password
/api/auth/contacts/             → CRUD contacts
/api/auth/organization/         → GET/PUT — organization settings
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView

from .views import (
    LoginView,
    SignupView,
    SignupAvailabilityView,
    AgentViewSet,
    ContactViewSet,
    OrganizationView,
    OnboardingProfileView,
    OnboardingQuickKnowledgeUploadView,
)

router = DefaultRouter()
router.register('agents', AgentViewSet, basename='agents')
router.register('contacts', ContactViewSet, basename='contacts')

urlpatterns = [
    # Auth endpoints
    path('login/', LoginView.as_view(), name='token_obtain_pair'),
    path('signup/', SignupView.as_view(), name='signup'),
    path('signup-availability/', SignupAvailabilityView.as_view(), name='signup-availability'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),

    # Organization
    path('organization/', OrganizationView.as_view(), name='organization-detail'),
    path('onboarding-profile/', OnboardingProfileView.as_view(), name='onboarding-profile'),
    path('onboarding-quick-knowledge/', OnboardingQuickKnowledgeUploadView.as_view(), name='onboarding-quick-knowledge'),

    # Agents + Contacts (router)
    path('', include(router.urls)),
]
