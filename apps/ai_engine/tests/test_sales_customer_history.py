"""
CustomerHistoryService — cross-conversation order memory.

Covers: fetch formatting/filtering, the contact re-linking fix that makes
cross-conversation lookup possible at all, prompt wiring, and the price
validator's historical-total exemption.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.accounts.models import Contact, Organization
from apps.ai_engine.models import SalesSession
from apps.ai_engine.sales.customer_history import CustomerHistoryService
from apps.ai_engine.sales.generator import ResponseGenerator
from apps.ai_engine.sales.validator import ResponseValidator
from apps.ai_router.executors.sales_agent import SalesAgentExecutor
from apps.channels_config.models import ChannelConfig
from apps.conversations.models import Conversation, Message
from apps.ecommerce.models import Order, Product, ProductVariant


class CustomerHistoryFetchTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='History Org', slug='history-org')
        self.conversation = Conversation.objects.create(organization=self.org, canal='web', estado='nuevo')

    def _order(self, *, contact, conversation=None, total=50_000, items=None, status='new'):
        return Order.objects.create(
            organization=self.org,
            contact=contact,
            conversation=conversation,
            items=items or [{'title': 'Cuaderno Argollado', 'qty': 1}],
            total=total,
            status=status,
            payment_method='efectivo',
        )

    def test_returns_empty_without_contact(self):
        result = CustomerHistoryService.fetch(organization=self.org, contact=None)
        self.assertEqual(result, {'text': '', 'totals': []})

    def test_returns_empty_for_anonymous_contact_without_identity(self):
        contact = Contact.objects.create(organization=self.org, nombre='Anon')
        result = CustomerHistoryService.fetch(organization=self.org, contact=contact)
        self.assertEqual(result, {'text': '', 'totals': []})

    def test_formats_orders_with_real_numbers(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        order = self._order(contact=contact, total=50_000)
        result = CustomerHistoryService.fetch(organization=self.org, contact=contact)
        expected_ref = CustomerHistoryService.display_order_number(order)
        self.assertIn(f'#{expected_ref}', result['text'])
        self.assertIn('Cuaderno Argollado x1', result['text'])
        self.assertIn('$50,000', result['text'])
        self.assertIn('pendiente', result['text'])
        self.assertEqual(result['totals'], [50_000.0])

    def test_excludes_the_current_conversation_own_order(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        self._order(contact=contact, conversation=self.conversation)
        result = CustomerHistoryService.fetch(
            organization=self.org, contact=contact, exclude_conversation_id=self.conversation.id,
        )
        self.assertEqual(result, {'text': '', 'totals': []})

    def test_caps_at_max_orders(self):
        contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        for i in range(5):
            self._order(contact=contact, total=10_000 + i)
        result = CustomerHistoryService.fetch(organization=self.org, contact=contact, max_orders=2)
        self.assertEqual(len(result['totals']), 2)

    def test_different_contacts_are_isolated(self):
        contact_a = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        contact_b = Contact.objects.create(organization=self.org, nombre='Luis', telefono='3009998877')
        self._order(contact=contact_a, total=50_000)
        result = CustomerHistoryService.fetch(organization=self.org, contact=contact_b)
        self.assertEqual(result, {'text': '', 'totals': []})


class GeneratorCustomerHistorySectionTests(TestCase):
    def _prompt(self, context):
        session = SimpleNamespace(
            organization=SimpleNamespace(name='History Org'),
            stage='discovery', selected_products=[], budget_min=None, budget_max=None,
            objections=[], category_interest='',
        )
        return ResponseGenerator._build_system_prompt(
            session=session, situation='discovery', action={'response_strategy': 'discover'},
            context=context, runtime_config={},
        )

    def test_prompt_includes_history_and_guardrail(self):
        prompt = self._prompt({
            'recommended_products': [], 'product_resolution': {}, 'promotions': [], 'kb_content': '',
            'customer_order_history': '## Historial de pedidos de este cliente (datos reales, no inventes otros numeros)\n- Pedido #ABC123 (2026-06-01): Cuaderno x1 - $50,000 COP - pendiente - pago: efectivo',
        })
        self.assertIn('Historial de pedidos', prompt)
        self.assertIn('ABC123', prompt)
        self.assertIn('No puedes modificar pedidos ya confirmados', prompt)

    def test_prompt_omits_section_without_history(self):
        prompt = self._prompt({
            'recommended_products': [], 'product_resolution': {}, 'promotions': [], 'kb_content': '',
            'customer_order_history': '',
        })
        self.assertNotIn('Historial de pedidos', prompt)


class ValidatorHistoricalPriceExemptionTests(TestCase):
    def test_historical_total_is_not_flagged_as_hallucination(self):
        context = {
            'recommended_products': [{'title': 'Lapiz', 'price_min': 3_000, 'price_max': 3_000}],
            'customer_history_totals': [50_000.0],
        }
        reply = 'Tu pedido anterior fue por $50,000 en total. ¿Te ayudo con algo mas?'
        result = ResponseValidator.validate(reply, context)
        self.assertEqual(result, reply)

    def test_unrelated_price_still_blocked_even_with_history_present(self):
        context = {
            'recommended_products': [{'title': 'Lapiz', 'price_min': 3_000, 'price_max': 3_000}],
            'customer_history_totals': [50_000.0],
        }
        # Not a plausible quantity-multiple of either known price (ratio > 30
        # units either way), so it can't be mistaken for a legit subtotal.
        reply = 'El precio de este producto es $2,345,678.'
        result = ResponseValidator.validate(reply, context)
        self.assertEqual(result, ResponseValidator._fallback_reply(context))

    def test_history_totals_alone_activate_the_check(self):
        # No recommended_products at all — history totals must still gate.
        context = {'customer_history_totals': [50_000.0]}
        reply = 'Ese pedido especifico no existe, pero aqui tienes uno por $9,999,999.'
        result = ResponseValidator.validate(reply, context)
        self.assertEqual(result, ResponseValidator._fallback_reply(context))


class ConversationContactRelinkingTests(TestCase):
    """The bug this feature depends on: without re-pointing conversation.contact
    to the checkout-resolved identity, a brand new conversation from the same
    phone/email could never be matched back to this order."""

    def setUp(self):
        self.org = Organization.objects.create(name='Relink Org', slug='relink-org')
        # Anonymous placeholder, exactly like an app-chat widget session start.
        self.anon_contact = Contact.objects.create(organization=self.org, nombre='Usuario app')
        self.conversation = Conversation.objects.create(
            organization=self.org, canal='app', estado='nuevo', contact=self.anon_contact,
        )
        self.product = Product.objects.create(
            organization=self.org, title='Cuaderno Argollado', category='Utiles escolares',
            status='active', is_active=True,
        )
        ProductVariant.objects.create(product=self.product, sku='CUAD-01', name='Unico', price=50_000, stock=5)

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_checkout_repoints_conversation_contact_to_resolved_identity(self, mock_detect, mock_generate):
        SalesSession.objects.create(
            conversation=self.conversation, organization=self.org, stage='checkout',
            selected_products=[str(self.product.id)],
        )
        ChannelConfig.objects.create(
            organization=self.org, channel='onboarding', is_active=True,
            settings={'payment_methods': ['efectivo'], 'payment_settings': {'cash_enabled': True, 'cash_instructions': 'Pagas en efectivo contra entrega.'}},
        )
        mock_detect.side_effect = ['checkout', 'checkout']

        message = Message.objects.create(
            conversation=self.conversation, role='user', content='Quiero finalizar la compra.',
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
        executor = SalesAgentExecutor()
        executor.execute(conversation=self.conversation, message=message, decision=None, organization=self.org)

        confirm_message = Message.objects.create(
            conversation=self.conversation, role='user', content='Si, confirmo mi pedido.', metadata={},
        )
        executor.execute(conversation=self.conversation, message=confirm_message, decision=None, organization=self.org)

        self.conversation.refresh_from_db()
        self.assertNotEqual(self.conversation.contact_id, self.anon_contact.id)
        self.assertEqual(self.conversation.contact.telefono, '3001112233')

        order = Order.objects.filter(organization=self.org).latest('created_at')
        self.assertEqual(order.contact_id, self.conversation.contact_id)
        self.assertEqual(order.payment_method, 'efectivo')

    def test_new_conversation_from_same_phone_sees_order_history(self):
        # Simulates: first conversation placed an order and resolved the
        # contact by phone; a brand new conversation later starts anonymous
        # but the SAME phone gets provided again mid-chat, which should
        # match the same Contact and surface the prior order.
        real_contact = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        Order.objects.create(
            organization=self.org, contact=real_contact, conversation=self.conversation,
            items=[{'title': 'Cuaderno Argollado', 'qty': 1}], total=50_000, status='new',
            payment_method='efectivo',
        )

        new_conversation = Conversation.objects.create(
            organization=self.org, canal='web', estado='nuevo', contact=real_contact,
        )
        session = SalesSession.objects.create(conversation=new_conversation, organization=self.org)

        executor = SalesAgentExecutor()
        context = executor._load_context(
            action={}, session=session, organization=self.org, message_text='como va mi pedido anterior?',
        )
        self.assertIn('Cuaderno Argollado', context['customer_order_history'])
        self.assertEqual(context['customer_history_totals'], [50_000.0])
