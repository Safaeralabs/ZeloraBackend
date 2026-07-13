"""
Tests for SessionManager — state persistence and signal extraction.
"""
from django.test import TestCase

from apps.accounts.models import Organization
from apps.ai_engine.models import SalesSession
from apps.ai_engine.sales.session import SessionManager
from apps.conversations.models import Conversation


class SessionManagerSignalExtractionTests(TestCase):
    """extract_session_signals — pure parsing logic."""

    def test_price_objection_detected(self):
        signals = SessionManager.extract_session_signals(
            user_message='Me gusta, pero está muy caro',
            action={},
            context={},
        )
        self.assertIn('price', signals['detected_objections'])

    def test_shipping_city_extracted(self):
        signals = SessionManager.extract_session_signals(
            user_message='¿Hacen envío a Lima?',
            action={},
            context={},
        )
        self.assertEqual(signals['shipping_city'], 'Lima')

    def test_quality_objection_detected(self):
        signals = SessionManager.extract_session_signals(
            user_message='No me convence la calidad',
            action={},
            context={},
        )
        self.assertIn('quality', signals['detected_objections'])

    def test_no_objection_in_positive_message(self):
        signals = SessionManager.extract_session_signals(
            user_message='Me encanta, lo quiero',
            action={},
            context={},
        )
        self.assertEqual(signals['detected_objections'], [])

    def test_no_city_extracted_without_shipping_keyword(self):
        signals = SessionManager.extract_session_signals(
            user_message='Vivo en Bogotá',
            action={},
            context={},
        )
        self.assertEqual(signals['shipping_city'], '')

    def test_checkout_data_populated_when_checkout_step_active(self):
        signals = SessionManager.extract_session_signals(
            user_message='Confirmo el pedido',
            action={'checkout_step': 2},
            context={},
        )
        self.assertEqual(signals['checkout_data']['step'], 2)
        self.assertIn('Confirmo', signals['checkout_data']['last_user_message'])


class SessionManagerUpdateTests(TestCase):
    """SessionManager.update — state persistence to DB."""

    def setUp(self):
        self.org = Organization.objects.create(name='Session Org', slug='session-org')
        self.conversation = Conversation.objects.create(
            organization=self.org,
            canal='web',
            estado='nuevo',
        )
        self.session = SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            situation='discovery',
        )

    def _update(self, *, situation='discovery', action=None, context=None, reply='OK'):
        action = action or {'response_strategy': 'discover'}
        context = context or {}
        SessionManager.update(
            session=self.session,
            situation=situation,
            action=action,
            context=context,
            reply=reply,
        )
        self.session.refresh_from_db()

    def test_category_interest_persisted_from_resolution(self):
        self._update(context={
            'product_resolution': {'category': 'leggings'},
        })
        self.assertEqual(self.session.category_interest, 'leggings')

    def test_shipping_city_persisted(self):
        self._update(context={'shipping_city': 'Medellín'})
        self.assertEqual(self.session.shipping_city, 'Medellín')

    def test_objections_accumulated(self):
        self._update(context={'detected_objections': ['price']})
        self.assertIn('price', self.session.objections)

    def test_stage_transitions_discovery_to_considering_on_selection(self):
        self._update(context={'selected_product_ids': ['abc-123']})
        self.assertEqual(self.session.stage, 'considering')
        self.assertIn('abc-123', self.session.selected_products)

    def test_shown_products_accumulated_and_capped_at_20(self):
        # Seed with 18 already-shown products
        existing = [f'prod-{i}' for i in range(18)]
        self.session.shown_products = existing
        self.session.save(update_fields=['shown_products'])

        products = [
            {'id': 'prod-new-1', 'title': 'A'},
            {'id': 'prod-new-2', 'title': 'B'},
            {'id': 'prod-new-3', 'title': 'C'},
        ]
        self._update(context={'recommended_products': products})

        self.assertLessEqual(len(self.session.shown_products), 20)
        self.assertIn('prod-new-1', self.session.shown_products)
        self.assertIn('prod-new-2', self.session.shown_products)

    def test_message_count_incremented(self):
        initial_count = self.session.message_count
        self._update()
        self.assertEqual(self.session.message_count, initial_count + 1)

    def test_situation_change_recorded(self):
        self.session.situation = 'discovery'
        self.session.save(update_fields=['situation'])
        self._update(situation='specific_product_customer')
        self.assertEqual(self.session.situation, 'specific_product_customer')
        self.assertEqual(self.session.last_situation, 'discovery')

    def test_checkout_step_advances_stage_with_selected_products(self):
        self.session.selected_products = ['prod-1']
        self.session.save(update_fields=['selected_products'])
        self._update(action={'checkout_step': 1, 'response_strategy': 'close'})
        self.assertEqual(self.session.stage, 'checkout')
        self.assertEqual(self.session.checkout_step, 1)

    def test_checkout_step_does_not_advance_without_selected_products(self):
        self._update(action={'checkout_step': 1, 'response_strategy': 'close'})
        self.assertEqual(self.session.stage, 'discovery')
        self.assertEqual(self.session.checkout_step, 0)

    def test_order_completed_resets_checkout_state(self):
        self.session.stage = 'checkout'
        self.session.checkout_step = 2
        self.session.selected_products = ['prod-1']
        self.session.category_interest = 'llaveros'
        self.session.save(update_fields=['stage', 'checkout_step', 'selected_products', 'category_interest'])

        self._update(
            action={'response_strategy': 'close'},
            context={'order_completed': True},
        )

        self.assertEqual(self.session.stage, 'discovery')
        self.assertEqual(self.session.checkout_step, 0)
        self.assertEqual(self.session.selected_products, [])
        self.assertEqual(self.session.category_interest, '')

    def test_force_stage_considering_reopens_checkout_without_losing_cart(self):
        self.session.stage = 'checkout'
        self.session.checkout_step = 2
        self.session.selected_products = ['prod-1']
        self.session.checkout_data = {'shipping_form': {'city': 'Bogota'}}
        self.session.save(update_fields=['stage', 'checkout_step', 'selected_products', 'checkout_data'])

        self._update(
            situation='discovery',
            action={'fetch_products': True, 'response_strategy': 'recommend'},
            context={'force_stage': 'considering'},
        )

        self.assertEqual(self.session.stage, 'considering')
        self.assertEqual(self.session.checkout_step, 0)
        self.assertEqual(self.session.selected_products, ['prod-1'])
        self.assertEqual(self.session.checkout_data.get('shipping_form', {}).get('city'), 'Bogota')


class SessionManagerGetOrCreateTests(TestCase):
    """get_or_create — idempotent session creation."""

    def setUp(self):
        self.org = Organization.objects.create(name='GC Org', slug='gc-org')
        self.conversation = Conversation.objects.create(
            organization=self.org,
            canal='web',
            estado='nuevo',
        )

    def test_creates_session_if_not_exists(self):
        self.assertFalse(SalesSession.objects.filter(conversation=self.conversation).exists())
        session = SessionManager.get_or_create(self.conversation)
        self.assertEqual(session.stage, 'discovery')
        self.assertEqual(SalesSession.objects.filter(conversation=self.conversation).count(), 1)

    def test_returns_existing_session_without_creating_duplicate(self):
        existing = SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='considering',
        )
        session = SessionManager.get_or_create(self.conversation)
        self.assertEqual(session.id, existing.id)
        self.assertEqual(session.stage, 'considering')
        self.assertEqual(SalesSession.objects.filter(conversation=self.conversation).count(), 1)
