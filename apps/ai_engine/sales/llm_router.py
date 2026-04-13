"""
LLM Router — Selects the right model for each task.

Strategy:
- gpt-5.4-nano: extraction, classification, summaries (fast, cheap)
- gpt-5.4-mini: main sales conversation (default, good balance)
- gpt-5.4: complex reasoning, delicate cases (premium)
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Routes LLM calls to appropriate model based on task.

    Settings (from Django config):
    - OPENAI_SITUATION_MODEL: gpt-5.4-nano (default)
    - OPENAI_SALES_MODEL: gpt-5.4-mini (default)
    - OPENAI_PREMIUM_MODEL: gpt-5.4 (default)
    - OPENAI_API_KEY: required
    """

    @staticmethod
    def model_for_task(task: str) -> str:
        """
        Get the appropriate model for a task.

        Args:
            task: Task name (situation | main_response | complex_reasoning |
                            summary | fallback_extraction | etc.)

        Returns:
            Model name string (e.g., "gpt-5.4-mini")
        """
        task_to_model = {
            # Extraction and classification — nano (fast, cheap)
            'situation_detection': settings.OPENAI_SITUATION_MODEL or 'gpt-5.4-nano',
            'intent_extraction': settings.OPENAI_SITUATION_MODEL or 'gpt-5.4-nano',
            'entity_extraction': settings.OPENAI_SITUATION_MODEL or 'gpt-5.4-nano',
            'objection_detection': settings.OPENAI_SITUATION_MODEL or 'gpt-5.4-nano',

            # Main sales conversation — mini (default)
            'main_response': settings.OPENAI_SALES_MODEL or 'gpt-5.4-mini',
            'discovery': settings.OPENAI_SALES_MODEL or 'gpt-5.4-mini',
            'recommendation': settings.OPENAI_SALES_MODEL or 'gpt-5.4-mini',
            'objection_handling': settings.OPENAI_SALES_MODEL or 'gpt-5.4-mini',
            'closing': settings.OPENAI_SALES_MODEL or 'gpt-5.4-mini',
            'redirect': settings.OPENAI_SALES_MODEL or 'gpt-5.4-mini',

            # Summaries — nano
            'summary': settings.OPENAI_SITUATION_MODEL or 'gpt-5.4-nano',
            'session_summary': settings.OPENAI_SITUATION_MODEL or 'gpt-5.4-nano',

            # Complex reasoning / delicate cases — premium
            'complex_comparison': settings.OPENAI_PREMIUM_MODEL or 'gpt-5.4',
            'advanced_recommendation': settings.OPENAI_PREMIUM_MODEL or 'gpt-5.4',
            'delicate_post_sale': settings.OPENAI_PREMIUM_MODEL or 'gpt-5.4',
            'high_risk_objection': settings.OPENAI_PREMIUM_MODEL or 'gpt-5.4',
            'ambiguous_language': settings.OPENAI_SALES_MODEL or 'gpt-5.4-mini',  # try mini first
            'fallback_extraction': settings.OPENAI_PREMIUM_MODEL or 'gpt-5.4',  # escalate if mini failed
        }

        model = task_to_model.get(task)
        if not model:
            # Safe default
            logger.warning(f'Unknown task {task}, using OPENAI_SALES_MODEL')
            model = settings.OPENAI_SALES_MODEL or 'gpt-5.4-mini'

        return model

    @staticmethod
    def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Rough estimate of API cost (for monitoring).

        Args:
            model: Model name
            input_tokens: Tokens in
            output_tokens: Tokens out

        Returns:
            Estimated USD cost
        """
        # Rough pricing as of late 2024
        # These are estimates — check OpenAI pricing
        pricing = {
            'gpt-5.4-nano': {'input': 0.3e-6, 'output': 1.2e-6},  # cheapest
            'gpt-5.4-mini': {'input': 0.15e-5, 'output': 0.6e-5},  # mid-tier
            'gpt-5.4': {'input': 2.5e-5, 'output': 10e-5},  # premium
        }

        rates = pricing.get(model, pricing['gpt-5.4-mini'])
        return (input_tokens * rates['input']) + (output_tokens * rates['output'])

    @staticmethod
    def get_all_models() -> dict:
        """
        Return all configured models for monitoring/debugging.

        Returns:
            Dict with model assignments
        """
        return {
            'situation_model': settings.OPENAI_SITUATION_MODEL or 'gpt-5.4-nano',
            'sales_model': settings.OPENAI_SALES_MODEL or 'gpt-5.4-mini',
            'premium_model': settings.OPENAI_PREMIUM_MODEL or 'gpt-5.4',
        }
