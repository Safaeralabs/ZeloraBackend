"""
OrderLookupService — lets the Sales Agent answer order-status questions when
a customer types their order number.

Security invariants under test: read-only always; full detail only when the
requester's resolved contact matches the order's contact; otherwise generic
status only, never address/items/phone/total.
"""
from django.test import TestCase

from apps.accounts.models import Contact, Organization
from apps.ai_engine.sales.order_lookup import OrderLookupService
from apps.ecommerce.models import Order


class OrderLookupExtractCodeTests(TestCase):
    def test_extracts_hex_code_from_message(self):
        self.assertEqual(OrderLookupService.extract_code('mi pedido es 3F2A1B0C gracias'), '3F2A1B0C')

    def test_no_code_returns_none(self):
        self.assertIsNone(OrderLookupService.extract_code('hola, como estas?'))

    def test_lowercase_code_is_uppercased(self):
        self.assertEqual(OrderLookupService.extract_code('el numero es ab12cd'), 'AB12CD')


class OrderLookupBuildContextTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Lookup Org', slug='lookup-org')
        self.owner = Contact.objects.create(organization=self.org, nombre='Ana', telefono='3001112233')
        self.stranger = Contact.objects.create(organization=self.org, nombre='Luis', telefono='3009998877')
        self.order = Order.objects.create(
            organization=self.org,
            contact=self.owner,
            items=[{'title': 'Leggings Negro', 'qty': 2}],
            total=90_000,
            status='shipped',
            payment_method='nequi',
        )
        self.code = str(self.order.id).split('-')[0].upper()

    def test_no_code_in_message_is_a_noop(self):
        result = OrderLookupService.build_context(
            organization=self.org, message_text='hola, tienen envios a Medellin?', requester_contact=self.owner,
        )
        self.assertEqual(result, {'text': '', 'matched': False})

    def test_unknown_code_tells_agent_not_to_invent_a_status(self):
        result = OrderLookupService.build_context(
            organization=self.org, message_text='mi pedido es ABCDEF12', requester_contact=self.owner,
        )
        self.assertFalse(result['matched'])
        self.assertIn('no inventes', result['text'].lower())

    def test_owner_asking_gets_full_detail(self):
        result = OrderLookupService.build_context(
            organization=self.org,
            message_text=f'como va mi pedido {self.code}?',
            requester_contact=self.owner,
        )
        self.assertTrue(result['matched'])
        self.assertIn('identidad verificada', result['text'])
        self.assertIn('Leggings Negro', result['text'])
        self.assertIn('$90,000', result['text'])
        self.assertIn('enviado', result['text'])

    def test_stranger_asking_gets_generic_status_only(self):
        result = OrderLookupService.build_context(
            organization=self.org,
            message_text=f'que tal el pedido {self.code}?',
            requester_contact=self.stranger,
        )
        self.assertTrue(result['matched'])
        self.assertIn('NO verificada', result['text'])
        self.assertIn('enviado', result['text'])
        self.assertNotIn('Leggings Negro', result['text'])
        self.assertNotIn('90,000', result['text'])

    def test_no_requester_contact_gets_generic_status_only(self):
        result = OrderLookupService.build_context(
            organization=self.org,
            message_text=f'estado del pedido {self.code}',
            requester_contact=None,
        )
        self.assertTrue(result['matched'])
        self.assertIn('NO verificada', result['text'])
        self.assertNotIn('Leggings Negro', result['text'])

    def test_lookup_is_scoped_to_organization(self):
        other_org = Organization.objects.create(name='Other Org', slug='other-org')
        result = OrderLookupService.find(organization=other_org, code=self.code)
        self.assertIsNone(result)

    def test_never_matches_a_cancel_or_modify_intent_with_side_effects(self):
        # The service has no write path at all — this just documents the
        # invariant: build_context never touches Order.save()/.delete().
        result = OrderLookupService.build_context(
            organization=self.org,
            message_text=f'cancela mi pedido {self.code}',
            requester_contact=self.owner,
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'shipped')
        self.assertTrue(result['matched'])
