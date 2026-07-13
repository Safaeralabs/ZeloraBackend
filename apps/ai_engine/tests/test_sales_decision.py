"""
Tests for DecisionEngine — decision table coverage and handoff rules.
"""
from django.test import SimpleTestCase

from apps.ai_engine.sales.decision import ACTIVE_STAGES, SITUATIONS, DecisionEngine


VALID_STAGES = ('discovery', 'considering', 'checkout', 'handoff', 'closed')


class DecisionEngineTableTests(SimpleTestCase):
    """Systematic coverage of every entry in the decision table."""

    def _assert_valid_action(self, situation: str, stage: str):
        action = DecisionEngine.decide(situation, stage)
        self.assertIsInstance(action, dict, f'Action must be dict for ({situation}, {stage})')
        self.assertIn('response_strategy', action, f'Missing response_strategy for ({situation}, {stage})')
        self.assertIn(
            action['response_strategy'],
            ('discover', 'recommend', 'close', 'inform', 'clarify', 'redirect', 'ignore'),
            f'Unknown response_strategy for ({situation}, {stage})',
        )

    def test_all_table_entries_return_valid_action(self):
        for key in DecisionEngine.DECISION_TABLE:
            situation, stage = key
            with self.subTest(situation=situation, stage=stage):
                self._assert_valid_action(situation, stage)

    def test_unknown_combination_returns_safe_fallback(self):
        action = DecisionEngine.decide('unknown_situation', 'discovery')
        self.assertIsInstance(action, dict)
        self.assertEqual(action['response_strategy'], 'clarify')
        self.assertFalse(action.get('fetch_products', False))
        self.assertFalse(action.get('requires_handoff', False))

    def test_unknown_stage_returns_safe_fallback(self):
        action = DecisionEngine.decide('discovery', 'unknown_stage')
        self.assertIsInstance(action, dict)
        self.assertEqual(action['response_strategy'], 'clarify')


class DecisionEngineHandoffTests(SimpleTestCase):
    """Handoff escalation rules."""

    def test_administrative_customer_in_checkout_requires_handoff(self):
        action = DecisionEngine.decide('administrative_customer', 'checkout')
        self.assertTrue(action.get('requires_handoff'))
        self.assertEqual(action.get('handoff_reason'), 'payment')

    def test_post_sale_in_checkout_requires_handoff(self):
        action = DecisionEngine.decide('post_sale', 'checkout')
        self.assertTrue(action.get('requires_handoff'))
        self.assertEqual(action.get('handoff_reason'), 'complexity')

    def test_post_sale_in_considering_requires_handoff(self):
        action = DecisionEngine.decide('post_sale', 'considering')
        self.assertTrue(action.get('requires_handoff'))

    def test_prompt_injection_does_not_require_handoff(self):
        action = DecisionEngine.decide('prompt_injection', 'discovery')
        self.assertFalse(action.get('requires_handoff', False))
        self.assertEqual(action.get('response_strategy'), 'ignore')

    def test_off_topic_does_not_require_handoff(self):
        action = DecisionEngine.decide('off_topic', 'discovery')
        self.assertFalse(action.get('requires_handoff', False))
        self.assertEqual(action.get('response_strategy'), 'redirect')


class DecisionEngineProductFetchTests(SimpleTestCase):
    """Verify fetch_products flag for key scenarios."""

    def test_discovery_stage_fetches_products(self):
        action = DecisionEngine.decide('discovery', 'discovery')
        self.assertTrue(action.get('fetch_products'))

    def test_specific_product_customer_fetches_products(self):
        action = DecisionEngine.decide('specific_product_customer', 'discovery')
        self.assertTrue(action.get('fetch_products'))

    def test_price_sensitive_customer_in_discovery_does_not_fetch_products(self):
        # Intentional: show promos first, not products
        action = DecisionEngine.decide('price_sensitive_customer', 'discovery')
        self.assertFalse(action.get('fetch_products'))
        self.assertTrue(action.get('fetch_promotions'))

    def test_price_sensitive_customer_in_considering_fetches_products(self):
        action = DecisionEngine.decide('price_sensitive_customer', 'considering')
        self.assertTrue(action.get('fetch_products'))

    def test_intent_is_passed_through_to_action(self):
        action = DecisionEngine.decide('discovery', 'discovery', conversation_intent='buy_intent')
        self.assertEqual(action.get('intent'), 'buy_intent')


class DecisionEngineMatrixCoverageTests(SimpleTestCase):
    """The full 20 situations x 3 active stages matrix must be explicit."""

    def test_every_situation_stage_combination_is_in_the_table(self):
        for situation in SITUATIONS:
            for stage in ACTIVE_STAGES:
                with self.subTest(situation=situation, stage=stage):
                    self.assertIn(
                        (situation, stage),
                        DecisionEngine.DECISION_TABLE,
                        f'Missing decision table cell for ({situation}, {stage})',
                    )

    def test_table_has_no_entries_outside_the_canonical_matrix(self):
        for situation, stage in DecisionEngine.DECISION_TABLE:
            with self.subTest(situation=situation, stage=stage):
                self.assertIn(situation, SITUATIONS)
                self.assertIn(stage, ACTIVE_STAGES)


class DecisionEngineClosingTests(SimpleTestCase):
    """Close-oriented strategy for high-intent combinations."""

    def test_ready_to_buy_in_checkout_advances_the_close(self):
        action = DecisionEngine.decide('ready_to_buy_customer', 'checkout')
        self.assertEqual(action['response_strategy'], 'close')
        self.assertEqual(action.get('checkout_step'), 2)

    def test_urgent_customer_in_considering_pushes_to_checkout(self):
        action = DecisionEngine.decide('urgent_customer', 'considering')
        self.assertEqual(action['response_strategy'], 'close')
        self.assertEqual(action.get('checkout_step'), 1)

    def test_objection_in_considering_closes_with_value_not_clarify(self):
        action = DecisionEngine.decide('objection_customer', 'considering')
        self.assertEqual(action['response_strategy'], 'close')
        self.assertTrue(action.get('fetch_products'))
        self.assertTrue(action.get('fetch_promotions'))
        self.assertIn('sales_scripts', action.get('fetch_kb', []))

    def test_changing_mind_in_checkout_rescues_the_sale(self):
        action = DecisionEngine.decide('changing_mind_customer', 'checkout')
        self.assertEqual(action['response_strategy'], 'close')
        self.assertTrue(action.get('fetch_promotions'))

    def test_unknown_situation_in_checkout_defaults_to_close(self):
        action = DecisionEngine.decide('unknown_situation', 'checkout')
        self.assertEqual(action['response_strategy'], 'close')

    def test_unknown_situation_outside_checkout_still_defaults_to_clarify(self):
        action = DecisionEngine.decide('unknown_situation', 'considering')
        self.assertEqual(action['response_strategy'], 'clarify')

    def test_checkout_language_before_cart_clarifies_without_checkout_step(self):
        # No cart yet: nothing to close, and checkout_step must be absent so
        # ResponseContractEnforcer does not treat the turn as an active checkout.
        action = DecisionEngine.decide('checkout', 'discovery')
        self.assertEqual(action['response_strategy'], 'clarify')
        self.assertNotIn('checkout_step', action)
        self.assertTrue(action.get('fetch_products'))

    def test_checkout_language_with_cart_in_considering_starts_checkout(self):
        action = DecisionEngine.decide('checkout', 'considering')
        self.assertEqual(action['response_strategy'], 'close')
        self.assertEqual(action.get('checkout_step'), 1)
