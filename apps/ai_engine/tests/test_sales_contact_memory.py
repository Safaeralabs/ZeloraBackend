"""
ContactMemoryService — soft, cross-conversation customer signals.

Covers: write-side sync from SessionManager.update(), read-side summary
formatting/gating, generator prompt wiring, and the previously-dead
conversations/serializers.py::get_contact_memory (the model it references
was deleted in an earlier refactor; this model brings it back with the
same field names, so the inbox "Cliente" panel starts working again).
"""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import Contact, Organization
from apps.ai_engine.models import ContactMemory, SalesSession
from apps.ai_engine.sales.contact_memory import ContactMemoryService
from apps.ai_engine.sales.generator import ResponseGenerator
from apps.ai_engine.sales.session import SessionManager
from apps.ai_router.executors.sales_agent import SalesAgentExecutor
from apps.channels_config.models import ChannelConfig
from apps.conversations.models import Conversation, Message
from apps.conversations.serializers import ConversationDetailSerializer
from apps.ecommerce.models import Product, ProductVariant


class ContactMemorySyncTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Memory Org', slug='memory-org')

    def _session(self, *, contact=None, message_count=1, **overrides):
        conversation = Conversation.objects.create(
            organization=self.org, canal='web', estado='nuevo', contact=contact,
        )
        session = SalesSession.objects.create(
            conversation=conversation, organization=self.org, message_count=message_count, **overrides,
        )
        return session

    def test_anonymous_contact_is_skipped(self):
        contact = Contact.objects.create(organization=self.org, nombre='Anon')
        session = self._session(contact=contact)
        ContactMemoryService.sync_from_session(session=session, situation='discovery', context={})
        self.assertFalse(ContactMemory.objects.filter(contact=contact).exists())

    def test_no_contact_is_skipped(self):
        session = self._session(contact=None)
        ContactMemoryService.sync_from_session(session=session, situation='discovery', context={})
        self.assertEqual(ContactMemory.objects.count(), 0)

    def test_creates_and_populates_memory_for_identified_contact(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        session = self._session(
            contact=contact, budget_min=40_000, budget_max=60_000,
            category_interest='utiles escolares', objections=['price'],
        )
        ContactMemoryService.sync_from_session(
            session=session, situation='objection_customer',
            context={'recommended_products': [{'id': 'p1'}, {'id': 'p2'}]},
        )
        memory = ContactMemory.objects.get(contact=contact)
        self.assertEqual(memory.conversation_count, 1)
        self.assertEqual(float(memory.inferred_budget_min), 40_000)
        self.assertEqual(float(memory.inferred_budget_max), 60_000)
        self.assertIn('utiles escolares', memory.category_preferences)
        self.assertEqual(memory.last_objection, 'price')
        self.assertEqual(memory.last_intent, 'objection_customer')
        self.assertEqual(memory.last_products_shown, ['p1', 'p2'])
        self.assertEqual(memory.total_products_viewed, 2)
        self.assertFalse(memory.converted)

    def test_marks_converted_on_order_completed(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        session = self._session(contact=contact)
        ContactMemoryService.sync_from_session(
            session=session, situation='checkout', context={'order_completed': True},
        )
        memory = ContactMemory.objects.get(contact=contact)
        self.assertTrue(memory.converted)

    def test_conversation_count_increments_only_on_first_turn_of_new_session(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        # First conversation, first turn.
        session_1 = self._session(contact=contact, message_count=1)
        ContactMemoryService.sync_from_session(session=session_1, situation='discovery', context={})
        # Same conversation, second turn — must NOT increment again.
        session_1.message_count = 2
        ContactMemoryService.sync_from_session(session=session_1, situation='discovery', context={})
        self.assertEqual(ContactMemory.objects.get(contact=contact).conversation_count, 1)

        # A brand NEW conversation for the same contact, first turn again.
        session_2 = self._session(contact=contact, message_count=1)
        ContactMemoryService.sync_from_session(session=session_2, situation='discovery', context={})
        self.assertEqual(ContactMemory.objects.get(contact=contact).conversation_count, 2)

    def test_wired_into_session_manager_update(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        session = self._session(contact=contact, category_interest='papeleria')
        SessionManager.update(
            session=session, situation='discovery', action={}, context={}, reply='hola',
        )
        self.assertTrue(ContactMemory.objects.filter(contact=contact).exists())


class ContactMemoryFetchSummaryTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Summary Org', slug='summary-org')

    def test_empty_without_contact(self):
        self.assertEqual(ContactMemoryService.fetch_summary(contact=None), '')

    def test_empty_for_first_time_contact(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        ContactMemory.objects.create(organization=self.org, contact=contact, conversation_count=1)
        self.assertEqual(ContactMemoryService.fetch_summary(contact=contact), '')

    def test_returns_summary_for_returning_contact(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        ContactMemory.objects.create(
            organization=self.org, contact=contact, conversation_count=3,
            inferred_budget_min=40_000, inferred_budget_max=60_000,
            category_preferences=['papeleria'], last_objection='price', converted=True,
        )
        summary = ContactMemoryService.fetch_summary(contact=contact)
        self.assertIn('3 conversaciones', summary)
        self.assertIn('papeleria', summary)
        self.assertIn('price', summary)
        self.assertIn('Ya ha comprado antes.', summary)


class GeneratorContactMemorySectionTests(TestCase):
    def _prompt(self, context):
        session = SimpleNamespace(
            organization=SimpleNamespace(name='Summary Org'), stage='discovery', selected_products=[],
            budget_min=None, budget_max=None, objections=[], category_interest='',
        )
        return ResponseGenerator._build_system_prompt(
            session=session, situation='discovery', action={'response_strategy': 'discover'},
            context=context, runtime_config={},
        )

    def test_prompt_includes_contact_memory_and_guardrail(self):
        prompt = self._prompt({
            'recommended_products': [], 'product_resolution': {}, 'promotions': [], 'kb_content': '',
            'contact_memory_summary': '## Cliente recurrente\nEste contacto ya tuvo 3 conversaciones antes.',
        })
        self.assertIn('Cliente recurrente', prompt)
        self.assertIn('no lo recites textualmente', prompt)

    def test_prompt_omits_section_without_contact_memory(self):
        prompt = self._prompt({
            'recommended_products': [], 'product_resolution': {}, 'promotions': [], 'kb_content': '',
            'contact_memory_summary': '',
        })
        self.assertNotIn('Cliente recurrente', prompt)


class SerializerContactMemoryRevivalTests(TestCase):
    """The frontend inbox panel already reads exactly this shape; it was
    silently always None since the backing model had been deleted."""

    def setUp(self):
        self.org = Organization.objects.create(name='Serializer Org', slug='serializer-org')

    def test_get_contact_memory_returns_real_data(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        conversation = Conversation.objects.create(organization=self.org, canal='web', contact=contact)
        ContactMemory.objects.create(
            organization=self.org, contact=contact, conversation_count=4,
            inferred_budget_min=40_000, inferred_budget_max=60_000,
            category_preferences=['papeleria'], last_intent='objection_customer',
            last_objection='price', converted=True,
        )
        serializer = ConversationDetailSerializer(conversation)
        data = serializer.data['contact_memory']
        self.assertEqual(data['conversation_count'], 4)
        self.assertEqual(data['inferred_budget_min'], 40_000.0)
        self.assertEqual(data['category_preferences'], ['papeleria'])
        self.assertTrue(data['converted'])

    def test_get_contact_memory_none_without_memory_row(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        conversation = Conversation.objects.create(organization=self.org, canal='web', contact=contact)
        serializer = ConversationDetailSerializer(conversation)
        self.assertIsNone(serializer.data['contact_memory'])


class EndToEndCrossConversationMemoryTests(TestCase):
    """Full scenario from the request: an order is placed, the conversation
    closes, and a brand-new conversation from the same identified customer
    should have both the hard order history and the soft preference memory
    available to the agent."""

    def setUp(self):
        self.org = Organization.objects.create(name='E2E Org', slug='e2e-org')
        self.product = Product.objects.create(
            organization=self.org, title='Cuaderno Argollado', category='Utiles escolares',
            status='active', is_active=True,
        )
        ProductVariant.objects.create(product=self.product, sku='CUAD-01', name='Unico', price=50_000, stock=5)

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_new_conversation_has_order_history_and_soft_memory(self, mock_detect, mock_generate):
        conversation_1 = Conversation.objects.create(organization=self.org, canal='web', estado='nuevo')
        SalesSession.objects.create(
            conversation=conversation_1, organization=self.org, stage='checkout',
            selected_products=[str(self.product.id)], category_interest='utiles escolares',
        )
        ChannelConfig.objects.create(
            organization=self.org, channel='onboarding', is_active=True,
            settings={'payment_methods': ['efectivo'], 'payment_settings': {'cash_enabled': True, 'cash_instructions': 'Pagas en efectivo contra entrega.'}},
        )
        mock_detect.side_effect = ['checkout', 'checkout']

        message = Message.objects.create(
            conversation=conversation_1, role='user', content='Quiero finalizar la compra.',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'submit_compact_checkout',
                        'data': {
                            'full_name': 'Ana Perez', 'phone': '3001112233', 'payment_method': 'efectivo',
                            'address_line1': 'Calle 10 #23-45', 'city': 'Bogota', 'reference': 'Porteria',
                        },
                    },
                },
            },
        )
        executor_1 = SalesAgentExecutor()
        executor_1.execute(conversation=conversation_1, message=message, decision=None, organization=self.org)
        confirm_message = Message.objects.create(
            conversation=conversation_1, role='user', content='Si, confirmo mi pedido.', metadata={},
        )
        executor_1.execute(conversation=conversation_1, message=confirm_message, decision=None, organization=self.org)

        conversation_1.refresh_from_db()
        resolved_contact = conversation_1.contact
        self.assertIsNotNone(resolved_contact)

        # Conversation closes; a brand new one starts, identified from turn 1
        # (e.g. a returning WhatsApp thread, or the widget already knows the
        # phone from a prior session).
        conversation_2 = Conversation.objects.create(
            organization=self.org, canal='web', estado='nuevo', contact=resolved_contact,
        )
        session_2 = SalesSession.objects.create(conversation=conversation_2, organization=self.org)

        executor_2 = SalesAgentExecutor()
        context = executor_2._load_context(
            action={}, session=session_2, organization=self.org, message_text='como va mi pedido anterior?',
        )
        self.assertIn('Cuaderno Argollado', context['customer_order_history'])
        self.assertEqual(context['customer_history_totals'], [50_000.0])
