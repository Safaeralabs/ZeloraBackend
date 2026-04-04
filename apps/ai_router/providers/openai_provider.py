from __future__ import annotations

from django.conf import settings

from ..schemas import ModelProfile, ProviderName
from .base import BaseAIProvider


class OpenAIProvider(BaseAIProvider):
    provider_name = ProviderName.OPENAI

    def supports_profile(self, profile: ModelProfile) -> bool:
        return profile in (ModelProfile.FAST, ModelProfile.STANDARD, ModelProfile.PREMIUM)

    def resolve_model_name(self, profile: ModelProfile) -> str:
        if profile == ModelProfile.FAST:
            return getattr(settings, 'OPENAI_ROUTER_MODEL', 'gpt-4.1-nano')
        if profile == ModelProfile.PREMIUM:
            return 'gpt-4.1'
        return getattr(settings, 'OPENAI_SALES_MODEL', getattr(settings, 'OPENAI_MODEL', 'gpt-4o'))
