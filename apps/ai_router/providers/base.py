from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import ModelProfile, ProviderName


class BaseAIProvider(ABC):
    provider_name: ProviderName

    @abstractmethod
    def supports_profile(self, profile: ModelProfile) -> bool:
        ...

    @abstractmethod
    def resolve_model_name(self, profile: ModelProfile) -> str:
        ...
