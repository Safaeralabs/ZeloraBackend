from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Organization
from apps.ai_engine.models import SalesSession
from apps.ai_engine.sales.followup import FollowUpEngine
from apps.conversations.models import Conversation, Message
from apps.ecommerce.models import Product, ProductVariant


RUNTIME_CONFIG = {
    'sales_agent': {
        'enabled': True,
        'name': 'Lia',
        'followup_mode': 'suave',
        'max_followups': 2,
    },
    'org_profile': {'brand': {'avoid_phrases': []}},
}


class FollowUpEngineTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Followup Org', slug='followup-org')
        self.now = timezone.now()

    def _make_session(self, *, stage='considering', hours_quiet=6, last_role='bot',
                      checkout_data=None, estado='en_proceso', canal='app', metadata=None):
        conversation = Conversation.objects.create(
            organization=self.org,
            canal=canal,
            estado=estado,
            metadata=metadata or {},
        )
        Message.objects.create(conversation=conversation, role='user', content='hola, quiero un top')
        Message.objects.create(conversation=conversation, role=last_role, content='te muestro opciones')
        last_activity = self.now - timedelta(hours=hours_quiet)
        Conversation.objects.filter(id=conversation.id).update(last_message_at=last_activity)
        conversation.refresh_from_db()

        session = SalesSession.objects.create(
            conversation=conversation,
            organization=self.org,
            stage=stage,
            checkout_data=checkout_data or {},
        )
        SalesSession.objects.filter(id=session.id).update(updated_at=last_activity)
        session.refresh_from_db()
        return session

    def _create_product(self, title='Top Motion Arena'):
        product = Product.objects.create(
            organization=self.org,
            title=title,
            category='Tops',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(product=product, sku='top-sku', name='V', price=90000, stock=4)
        return product

    # ── Eligibility ───────────────────────────────────────────────────────────

    def test_considering_session_quiet_for_hours_gets_followup(self):
        session = self._make_session(stage='considering', hours_quiet=6)
        sent = FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now)

        self.assertTrue(sent)
        followup = session.conversation.messages.order_by('-timestamp').first()
        self.assertEqual(followup.role, 'bot')
        self.assertEqual(followup.metadata['followup']['number'], 1)
        self.assertIn('Lia', followup.content)
        session.refresh_from_db()
        self.assertEqual(session.checkout_data['followup_state']['count'], 1)

    def test_checkout_followup_mentions_pending_order(self):
        product = self._create_product()
        session = self._make_session(stage='checkout', hours_quiet=6)
        session.selected_products = [str(product.id)]
        session.save(update_fields=['selected_products'])

        FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now)
        followup = session.conversation.messages.order_by('-timestamp').first()
        self.assertIn('pedido', followup.content.lower())
        self.assertIn('Top Motion Arena', followup.content)

    def test_recent_activity_is_not_nudged(self):
        session = self._make_session(hours_quiet=1)
        self.assertFalse(FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now))

    def test_cold_lead_is_left_alone(self):
        session = self._make_session(hours_quiet=100)
        self.assertFalse(FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now))

    def test_order_already_placed_is_not_nudged(self):
        session = self._make_session(stage='checkout', hours_quiet=6,
                                     checkout_data={'order_id': 'abc-123'})
        self.assertFalse(FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now))

    def test_human_owned_conversation_is_not_nudged(self):
        session = self._make_session(
            hours_quiet=6,
            metadata={'operator_state': {'owner': 'humano'}},
        )
        self.assertFalse(FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now))

    def test_pending_user_message_blocks_followup(self):
        session = self._make_session(hours_quiet=6, last_role='user')
        self.assertFalse(FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now))

    def test_max_followups_is_respected(self):
        session = self._make_session(
            hours_quiet=30,
            checkout_data={'followup_state': {
                'count': 2,
                'last_at': (self.now - timedelta(hours=25)).isoformat(),
            }},
        )
        self.assertFalse(FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now))

    def test_spacing_between_followups_is_respected(self):
        session = self._make_session(
            hours_quiet=10,
            checkout_data={'followup_state': {
                'count': 1,
                'last_at': (self.now - timedelta(hours=5)).isoformat(),
            }},
        )
        self.assertFalse(FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now))

    def test_followup_mode_off_disables_engine(self):
        config = {'sales_agent': {'enabled': True, 'followup_mode': 'desactivado'}}
        session = self._make_session(hours_quiet=6)
        self.assertFalse(FollowUpEngine.process_session(session, config, now=self.now))

    def test_disabled_sales_agent_disables_followups(self):
        config = {'sales_agent': {'enabled': False, 'followup_mode': 'suave'}}
        session = self._make_session(hours_quiet=6)
        self.assertFalse(FollowUpEngine.process_session(session, config, now=self.now))

    def test_second_followup_is_softer_and_final(self):
        session = self._make_session(
            hours_quiet=30,
            checkout_data={'followup_state': {
                'count': 1,
                'last_at': (self.now - timedelta(hours=25)).isoformat(),
            }},
        )
        sent = FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now)
        self.assertTrue(sent)
        followup = session.conversation.messages.order_by('-timestamp').first()
        self.assertEqual(followup.metadata['followup']['number'], 2)
        session.refresh_from_db()
        self.assertEqual(session.checkout_data['followup_state']['count'], 2)
        # Third attempt blocked by max_followups=2
        future = self.now + timedelta(hours=25)
        self.assertFalse(FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=future))

    def test_brand_guard_strips_forbidden_phrases_from_followup(self):
        config = {
            'sales_agent': {'enabled': True, 'name': 'Lia', 'followup_mode': 'suave', 'max_followups': 3},
            'org_profile': {'brand': {'avoid_phrases': ['quede pendiente de ti']}},
        }
        session = self._make_session(stage='considering', hours_quiet=6)
        sent = FollowUpEngine.process_session(session, config, now=self.now)
        self.assertTrue(sent)
        followup = session.conversation.messages.order_by('-timestamp').first()
        self.assertNotIn('quede pendiente de ti', followup.content.lower())

    # ── Sweep ─────────────────────────────────────────────────────────────────

    @patch('apps.ai_engine.sales.brand.BrandVoice.load_runtime_config', return_value=RUNTIME_CONFIG)
    def test_sweep_sends_to_eligible_and_skips_rest(self, _mock_config):
        self._make_session(stage='considering', hours_quiet=6)        # eligible
        self._make_session(stage='checkout', hours_quiet=6)           # eligible
        self._make_session(stage='considering', hours_quiet=6, last_role='user')  # skipped

        result = FollowUpEngine.sweep(now=self.now)
        self.assertEqual(result['sent'], 2)
        self.assertEqual(result['skipped'], 1)

    @patch('apps.ai_engine.sales.brand.BrandVoice.load_runtime_config', return_value=RUNTIME_CONFIG)
    def test_sweep_is_idempotent_within_spacing_window(self, _mock_config):
        self._make_session(stage='considering', hours_quiet=6)
        first = FollowUpEngine.sweep(now=self.now)
        second = FollowUpEngine.sweep(now=self.now + timedelta(minutes=30))
        self.assertEqual(first['sent'], 1)
        self.assertEqual(second['sent'], 0)

    def test_whatsapp_followup_queues_outbound_send(self):
        from apps.accounts.models import Contact
        contact = Contact.objects.create(
            organization=self.org, nombre='Ana', telefono='573001112233', canal='whatsapp',
        )
        session = self._make_session(hours_quiet=6, canal='whatsapp')
        session.conversation.contact = contact
        session.conversation.save(update_fields=['contact'])

        with patch('tasks.channel_tasks.send_whatsapp_message') as mock_task:
            sent = FollowUpEngine.process_session(session, RUNTIME_CONFIG, now=self.now)
        self.assertTrue(sent)
        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        self.assertEqual(kwargs['phone'], '573001112233')
        self.assertEqual(kwargs['org_id'], str(self.org.id))
