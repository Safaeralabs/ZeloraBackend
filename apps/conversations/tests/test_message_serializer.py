from django.test import TestCase

from apps.accounts.models import Organization
from apps.conversations.models import Conversation, Message
from apps.conversations.serializers import MessageSerializer


class MessageSerializerTests(TestCase):
    def test_exposes_safe_product_ui_payload(self):
        organization = Organization.objects.create(name='Test Org', slug='test-org-serializer')
        conversation = Conversation.objects.create(
            organization=organization,
            canal='web',
            estado='nuevo',
        )
        message = Message.objects.create(
            conversation=conversation,
            role='bot',
            content='Te comparto estas opciones.',
            metadata={
                'ui_payload': {
                    'type': 'product_list',
                    'layout': 'cards',
                    'title': 'Productos sugeridos',
                    'products': [
                        {
                            'id': 'prod-1',
                            'title': 'Top Motion Support Arena',
                            'brand': 'Vendly',
                            'category': 'Tops',
                            'image_url': 'https://example.com/top.jpg',
                            'price_min': 149900,
                            'price_max': 149900,
                            'price_type': 'fixed',
                            'availability_label': 'Disponible',
                            'is_available': True,
                            'cta_label': 'Seleccionar',
                            'selection_message': 'Me interesa Top Motion Support Arena',
                            'selection_payload': {
                                'interactive': {
                                    'action': 'select_product',
                                    'product_id': 'prod-1',
                                }
                            },
                        }
                    ],
                },
                'generated_by': 'ai_router',
            },
        )

        payload = MessageSerializer(message).data

        self.assertEqual(payload['ui_payload']['type'], 'product_list')
        self.assertEqual(len(payload['ui_payload']['products']), 1)
        self.assertEqual(
            payload['ui_payload']['products'][0]['selection_message'],
            'Me interesa Top Motion Support Arena',
        )
        self.assertEqual(
            payload['ui_payload']['products'][0]['selection_payload']['interactive']['product_id'],
            'prod-1',
        )

    def test_exposes_safe_checkout_compact_ui_payload(self):
        organization = Organization.objects.create(name='Test Org 2', slug='test-org-checkout')
        conversation = Conversation.objects.create(
            organization=organization,
            canal='app',
            estado='nuevo',
        )
        message = Message.objects.create(
            conversation=conversation,
            role='bot',
            content='Confirma tu pedido aqui.',
            metadata={
                'ui_payload': {
                    'type': 'checkout_compact',
                    'title': 'Confirma tu pedido',
                    'submit_label': 'Confirmar pedido',
                    'currency': 'COP',
                    'total': 159900,
                    'cart_items': [
                        {
                            'product_id': 'prod-1',
                            'title': 'Top Motion',
                            'qty': 1,
                            'unit_price': 159900,
                            'subtotal': 159900,
                            'currency': 'COP',
                        }
                    ],
                    'fields': [
                        {
                            'key': 'full_name',
                            'label': 'Nombre completo',
                            'required': True,
                            'placeholder': 'Nombre y apellido',
                            'input_type': 'text',
                        }
                    ],
                    'required_fields': ['full_name'],
                    'payment_options': [
                        {
                            'id': 'nequi',
                            'label': 'Nequi',
                            'description': 'Pago inmediato',
                            'instructions': 'Numero: 3001234567',
                        }
                    ],
                },
            },
        )

        payload = MessageSerializer(message).data
        self.assertEqual(payload['ui_payload']['type'], 'checkout_compact')
        self.assertEqual(payload['ui_payload']['cart_items'][0]['title'], 'Top Motion')
        self.assertEqual(payload['ui_payload']['required_fields'], ['full_name'])
        self.assertEqual(payload['ui_payload']['payment_options'][0]['id'], 'nequi')
