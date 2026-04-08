from __future__ import annotations

from .providers import ClaudeProvider, OpenAIProvider
from .schemas import ModelProfile, ModelSelection, ProviderName


class ModelSelector:
    def __init__(self) -> None:
        self._providers = {
            ProviderName.OPENAI: OpenAIProvider(),
            ProviderName.CLAUDE: ClaudeProvider(),
        }

    def select_for_route(
        self,
        *,
        tenant_id: str,
        intent_name: str,
        route_name: str,
    ) -> ModelSelection:
        if route_name == 'block_action':
            return ModelSelection(
                profile=ModelProfile.FAST,
                provider=None,
                model_name=None,
                reason='Deterministic security block; no provider call required.',
            )

        if route_name == 'route_to_sales_agent':
            provider = self._providers[ProviderName.OPENAI]
            profile = ModelProfile.STANDARD
            return ModelSelection(
                profile=profile,
                provider=provider.provider_name,
                model_name=provider.resolve_model_name(profile),
                reason=f'Standard profile selected for agent handoff in tenant {tenant_id}.',
            )

        if route_name == 'route_to_general_agent':
            provider = self._providers[ProviderName.OPENAI]
            profile = ModelProfile.FAST
            return ModelSelection(
                profile=profile,
                provider=provider.provider_name,
                model_name='gpt-4.1-nano',
                reason=f'Fast profile selected for general agent in tenant {tenant_id}.',
            )

        if route_name == 'trigger_flow':
            provider = self._providers[ProviderName.OPENAI]
            profile = ModelProfile.FAST
            return ModelSelection(
                profile=profile,
                provider=provider.provider_name,
                model_name=provider.resolve_model_name(profile),
                reason=f'Fast profile selected for flow-oriented intent "{intent_name}".',
            )

        provider = self._providers[ProviderName.OPENAI]
        profile = ModelProfile.STANDARD
        return ModelSelection(
            profile=profile,
            provider=provider.provider_name,
            model_name=provider.resolve_model_name(profile),
            reason=f'Default standard profile selected for route "{route_name}".',
        )
