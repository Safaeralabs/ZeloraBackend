from django.test import SimpleTestCase

from apps.ai_engine.sales.policy import SalesPolicyEngine


class SalesPolicyEngineTests(SimpleTestCase):
    def test_blocks_checkout_step_without_selected_products(self):
        policy = SalesPolicyEngine.enforce(
            action={'checkout_step': 1, 'response_strategy': 'close', 'fetch_products': False},
            session_stage='discovery',
            situation='ready_to_buy_customer',
            has_selected_products=False,
        )
        action = policy['action']
        self.assertNotIn('checkout_step', action)
        self.assertTrue(action.get('fetch_products'))
        self.assertEqual(action.get('response_strategy'), 'clarify')

    def test_reopens_checkout_to_considering_on_exploration(self):
        policy = SalesPolicyEngine.enforce(
            action={'response_strategy': 'clarify', 'fetch_products': False},
            session_stage='checkout',
            situation='discovery',
            has_selected_products=True,
            has_shipping_submission=False,
            has_checkout_submission=False,
        )
        self.assertEqual(policy.get('force_stage'), 'considering')
        self.assertTrue(policy['action'].get('fetch_products'))
        self.assertEqual(policy['action'].get('response_strategy'), 'recommend')

    def test_does_not_reopen_checkout_while_submitting_checkout_data(self):
        policy = SalesPolicyEngine.enforce(
            action={'checkout_step': 2, 'response_strategy': 'close'},
            session_stage='checkout',
            situation='discovery',
            has_selected_products=True,
            has_shipping_submission=True,
            has_checkout_submission=False,
        )
        self.assertNotIn('force_stage', policy)
        self.assertEqual(policy['action'].get('checkout_step'), 2)
