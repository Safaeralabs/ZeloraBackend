"""
Sales policy layer for deterministic stage/action guards.
"""
from __future__ import annotations


class SalesPolicyEngine:
    EXPLORATION_SITUATIONS = {
        'discovery',
        'comparing_customer',
        'indecisive_customer',
        'specific_product_customer',
    }

    @staticmethod
    def enforce(
        *,
        action: dict,
        session_stage: str,
        situation: str,
        has_selected_products: bool,
        has_shipping_submission: bool = False,
        has_checkout_submission: bool = False,
    ) -> dict:
        normalized = dict(action or {})
        force_stage = None

        # Never enter or advance checkout without cart items.
        if normalized.get('checkout_step') and not has_selected_products:
            normalized.pop('checkout_step', None)
            normalized['fetch_products'] = True
            normalized['response_strategy'] = 'clarify'

        # If user re-enters exploration while in checkout, move to considering
        # without losing cart state.
        if (
            session_stage == 'checkout'
            and has_selected_products
            and not has_shipping_submission
            and not has_checkout_submission
            and situation in SalesPolicyEngine.EXPLORATION_SITUATIONS
        ):
            normalized.pop('checkout_step', None)
            normalized['fetch_products'] = True
            normalized['response_strategy'] = 'recommend'
            force_stage = 'considering'

        result = {'action': normalized}
        if force_stage:
            result['force_stage'] = force_stage
        return result
