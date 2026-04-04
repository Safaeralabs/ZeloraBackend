from __future__ import annotations

from ..schemas import ModelProfile, ProviderName
from .base import BaseAIProvider


class ClaudeProvider(BaseAIProvider):
    provider_name = ProviderName.CLAUDE
    _profile_map = {
        ModelProfile.FAST: 'claude-3-5-haiku-latest',
        ModelProfile.STANDARD: 'claude-3-7-sonnet-latest',
        ModelProfile.PREMIUM: 'claude-3-7-sonnet-latest',
    }

    def supports_profile(self, profile: ModelProfile) -> bool:
        return profile in self._profile_map

    def resolve_model_name(self, profile: ModelProfile) -> str:
        return self._profile_map[profile]
