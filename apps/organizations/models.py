"""
Organizations app models.

NOTE: The Organization model lives in apps.accounts.models (alongside User)
to avoid circular imports (User has a FK to Organization).
This module re-exports it for convenience and adds any org-only helpers.
"""
from apps.accounts.models import Organization  # noqa: F401

__all__ = ['Organization']
