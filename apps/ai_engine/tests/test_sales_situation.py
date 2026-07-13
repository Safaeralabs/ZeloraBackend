from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.ai_engine.sales.situation import SituationDetector


class SituationDetectorHybridTests(SimpleTestCase):
    def _session(self, stage: str = 'discovery'):
        return SimpleNamespace(
            stage=stage,
            situation='discovery',
            selected_products=[],
            objections=[],
            budget_min=None,
            budget_max=None,
        )

    def test_checkout_payment_message_forces_checkout(self):
        result = SituationDetector.detect(
            user_message='prefiero transferencia',
            conversation_history=[],
            session=self._session(stage='checkout'),
        )
        self.assertEqual(result, 'checkout')

    def test_checkout_exploration_message_reopens_to_discovery(self):
        result = SituationDetector.detect(
            user_message='quiero ver otros productos similares',
            conversation_history=[],
            session=self._session(stage='checkout'),
        )
        self.assertEqual(result, 'discovery')

    def test_buy_intent_forces_ready_to_buy(self):
        result = SituationDetector.detect(
            user_message='ok, me lo llevo',
            conversation_history=[],
            session=self._session(stage='considering'),
        )
        self.assertEqual(result, 'ready_to_buy_customer')

    def test_variant_question_forces_specific_product(self):
        result = SituationDetector.detect(
            user_message='la tienes en talla S?',
            conversation_history=[],
            session=self._session(stage='discovery'),
        )
        self.assertEqual(result, 'specific_product_customer')

    def test_off_topic_forces_off_topic(self):
        result = SituationDetector.detect(
            user_message='como esta el clima hoy?',
            conversation_history=[],
            session=self._session(stage='discovery'),
        )
        self.assertEqual(result, 'off_topic')
