"""
Organizations views — delegates to apps.accounts.views.OrganizationView.
Kept separate to allow independent URL namespacing.
"""
from apps.accounts.views import OrganizationView  # noqa: F401

__all__ = ['OrganizationView']
