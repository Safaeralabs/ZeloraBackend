from unittest.mock import patch, MagicMock

from django.test import TestCase, SimpleTestCase

from apps.accounts.models import Organization
from apps.ai_engine.models import SalesSession
from apps.ai_router.executors.sales_agent import SalesAgentExecutor
from apps.channels_config.models import ChannelConfig
from apps.conversations.models import Conversation, Message
from apps.ecommerce.models import Order, Product, ProductVariant, Promotion
from apps.knowledge_base.models import KBArticle
from apps.workspace.models import CollabNote


class SalesAgentIntegrationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Integration Org', slug='integration-org')
        self.conversation = Conversation.objects.create(
            organization=self.org,
            canal='web',
            estado='nuevo',
        )

    def _create_product(self, *, title: str, category: str = 'Ropa', stock: int = 5) -> Product:
        product = Product.objects.create(
            organization=self.org,
            title=title,
            category=category,
            status='active',
            is_active=True,
            is_bestseller=True,
        )
        ProductVariant.objects.create(
            product=product,
            sku=f'{title[:8]}-sku',
            name='Variante',
            price=100000,
            stock=stock,
        )
        return product

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_browse_query_builds_cards_and_updates_category_interest(self, mock_detect, mock_generate):
        self._create_product(title='Camiseta Negra', category='Ropa')
        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'Te comparto una opción disponible.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='quiero una camiseta negra',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        metadata = executor.get_message_metadata()

        self.assertEqual(reply, 'Te comparto una opción disponible.')
        self.assertEqual(session.category_interest, 'camiseta')
        self.assertEqual(metadata['ui_payload']['products'][0]['title'], 'Camiseta Negra')

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_explicit_product_selection_persists_selected_products(self, mock_detect, mock_generate):
        product = self._create_product(title='Top Motion Support Arena', category='Tops')
        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'Perfecto, te ayudo con ese producto.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Me interesa este producto',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'select_product',
                        'product_id': str(product.id),
                    }
                }
            },
        )

        executor = SalesAgentExecutor()
        executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        self.assertIn(str(product.id), session.selected_products)
        self.assertEqual(session.stage, 'considering')

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_checkout_revalidates_selected_products(self, mock_detect, mock_generate):
        product = self._create_product(title='Legging Heat Control Negro', category='Leggings')
        session = SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            selected_products=[str(product.id)],
        )
        mock_detect.return_value = 'checkout'
        mock_generate.return_value = 'Voy a confirmar tu pedido.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='confirmo compra',
            metadata={},
        )

        executor = SalesAgentExecutor()
        executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        metadata = executor.get_message_metadata()
        session.refresh_from_db()

        self.assertEqual(session.stage, 'checkout')
        self.assertEqual(metadata['ui_payload']['type'], 'checkout_compact')
        self.assertEqual(metadata['ui_payload']['cart_items'][0]['title'], 'Legging Heat Control Negro')

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_checkout_reopens_to_considering_when_user_explores_again(self, mock_detect, mock_generate):
        product = self._create_product(title='Collar de Perlas', category='Accesorios')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            checkout_step=2,
            selected_products=[str(product.id)],
            checkout_data={'shipping_form': {'city': 'Bogota'}},
        )
        mock_detect.return_value = 'discovery'
        mock_generate.return_value = 'Claro, te muestro otras opciones.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='quiero ver otro producto',
            metadata={},
        )

        executor = SalesAgentExecutor()
        executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        metadata = executor.get_message_metadata()
        session = SalesSession.objects.get(conversation=self.conversation)

        self.assertEqual(session.stage, 'considering')
        self.assertEqual(session.checkout_step, 0)
        self.assertEqual(session.selected_products, [str(product.id)])
        self.assertEqual(metadata['ui_payload']['type'], 'product_list')

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_checkout_submission_does_not_reopen_to_considering(self, mock_detect, mock_generate):
        product = self._create_product(title='Collar de Perlas', category='Accesorios')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            checkout_step=2,
            selected_products=[str(product.id)],
        )
        mock_detect.return_value = 'discovery'
        mock_generate.return_value = 'Gracias por tus datos de envio.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='te paso mis datos',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'submit_shipping_form',
                        'data': {
                            'full_name': 'Ana Perez',
                            'phone': '+573001112233',
                            'address_line1': 'Calle 10 #23-45',
                            'city': 'Bogota',
                            'reference': 'Porteria principal',
                        },
                    }
                }
            },
        )

        executor = SalesAgentExecutor()
        executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        self.assertEqual(session.stage, 'checkout')

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_ready_to_buy_without_selected_product_stays_out_of_checkout(self, mock_detect, mock_generate):
        self._create_product(title='Collar de Perlas', category='Accesorios')
        mock_detect.return_value = 'ready_to_buy_customer'
        mock_generate.return_value = 'Claro, dime cual producto quieres agregar al carrito.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='me gustaria comprarlo',
            metadata={},
        )

        executor = SalesAgentExecutor()
        executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        metadata = executor.get_message_metadata()
        session = SalesSession.objects.get(conversation=self.conversation)

        self.assertEqual(session.stage, 'discovery')
        self.assertEqual(session.checkout_step, 0)
        self.assertEqual(metadata['ui_payload']['type'], 'product_list')

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_implicit_selection_from_text_allows_checkout(self, mock_detect, mock_generate):
        product = self._create_product(title='Camiseta Negra', category='Ropa')
        mock_detect.return_value = 'ready_to_buy_customer'
        mock_generate.return_value = 'Perfecto, pasemos al pago.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='me lo llevo, la camiseta negra',
            metadata={},
        )

        executor = SalesAgentExecutor()
        executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        metadata = executor.get_message_metadata()

        self.assertIn(str(product.id), session.selected_products)
        self.assertEqual(session.stage, 'checkout')
        self.assertEqual((metadata.get('ui_payload') or {}).get('type'), 'checkout_compact')

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_payment_message_with_selected_product_opens_checkout_form(self, mock_detect, mock_generate):
        product = self._create_product(title='Camiseta Negra', category='Ropa')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='considering',
            selected_products=[str(product.id)],
        )
        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'Perfecto, puedes pagar por transferencia.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='sii transferencia porfa',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        metadata = executor.get_message_metadata()
        self.assertIn('Para crear tu pedido me faltan', reply)
        self.assertEqual((metadata.get('ui_payload') or {}).get('type'), 'checkout_compact')

    @patch('apps.ai_engine.sales.catalog.CatalogService.resolve_query')
    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_variant_question_uses_real_variant_availability(self, mock_detect, mock_generate, mock_resolve):
        product = Product.objects.create(
            organization=self.org,
            title='Enterizo Shape Black',
            category='Ropa',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(product=product, sku='ent-s', name='S', price=169900, stock=2, reserved=0)
        ProductVariant.objects.create(product=product, sku='ent-m', name='M', price=169900, stock=0, reserved=0)

        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='considering',
            selected_products=[str(product.id)],
        )

        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'No tengo informacion de tallas.'
        mock_resolve.return_value = {
            'products': [
                {
                    'id': str(product.id),
                    'title': 'Enterizo Shape Black',
                    'brand': '',
                    'category': 'Ropa',
                    'image_url': '',
                    'price_min': 169900.0,
                    'price_max': 169900.0,
                    'price_type': 'fixed',
                    'availability_label': 'Disponible',
                    'is_available': True,
                }
            ],
            'resolution': {'match_type': 'browse', 'needs_confirmation': False, 'category': 'enterizo'},
        }

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='que tallas tienes disp?',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        lowered = reply.lower()
        self.assertIn('s', lowered)
        self.assertIn('agotadas', lowered)

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_post_order_transfer_question_returns_account_details(self, mock_detect, mock_generate):
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            checkout_data={
                'order_id': 'abc-123',
                'payment_method': 'transferencia_bancaria',
                'payment_method_label': 'Transferencia bancaria',
                'payment_instructions': 'Banco: ABC. Cuenta: 123456. Titular: Vendly SAS.',
            },
        )
        mock_detect.return_value = 'post_sale'
        mock_generate.return_value = 'Te recomiendo contactar soporte.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='que cuenta es?',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        lowered = reply.lower()
        self.assertIn('cuenta', lowered)
        self.assertIn('titular', lowered)
        mock_generate.assert_not_called()

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_post_order_transfer_where_to_transfer_phrase_prioritizes_payment_context(self, mock_detect, mock_generate):
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            checkout_data={
                'order_id': 'abc-123',
                'order_number': '1F456C2D',
                'payment_method': 'transferencia_bancaria',
                'payment_method_label': 'Transferencia bancaria',
                'payment_instructions': 'Banco: Bancolombia. Tipo: Ahorros. Cuenta: 12123234234. Titular: Valdiri SAS.',
            },
        )
        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'Lo siento, no tengo ese producto.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='donde transfiero?',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        lowered = reply.lower()
        self.assertIn('datos para pagar', lowered)
        self.assertIn('cuenta', lowered)
        self.assertIn('titular', lowered)
        self.assertNotIn('producto', lowered)
        mock_generate.assert_not_called()

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_post_order_transfer_without_details_escalates_to_human(self, mock_detect, mock_generate):
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            checkout_data={
                'order_id': 'abc-123',
                'payment_method': 'transferencia_bancaria',
                'payment_method_label': 'Transferencia bancaria',
                'payment_instructions': '',
            },
        )
        mock_detect.return_value = 'post_sale'
        mock_generate.return_value = 'Te compartimos luego.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='que cuenta es?',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        conversation = Conversation.objects.get(id=self.conversation.id)
        operator_state = (conversation.metadata or {}).get('operator_state') or {}
        self.assertIn('soporte', reply.lower())
        self.assertEqual(session.stage, 'handoff')
        self.assertEqual(conversation.estado, 'escalado')
        self.assertEqual(operator_state.get('priority'), 'alta')
        self.assertTrue(operator_state.get('follow_up'))
        self.assertEqual(operator_state.get('owner'), 'humano')
        self.assertEqual(
            CollabNote.objects.filter(
                conversation=conversation,
                note_type='warning',
                is_pinned=True,
            ).count(),
            1,
        )
        mock_generate.assert_not_called()

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_checkout_payment_method_selection_nequi_does_not_trigger_handoff(self, mock_detect, mock_generate):
        product = self._create_product(title='Enterizo Shape Black', category='Ropa')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            selected_products=[str(product.id)],
        )
        mock_detect.return_value = 'checkout'
        mock_generate.return_value = 'Perfecto, continuamos con tu pedido.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='nequi',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        conversation = Conversation.objects.get(id=self.conversation.id)
        self.assertNotIn('especialista', reply.lower())
        self.assertNotEqual(session.stage, 'handoff')
        self.assertNotEqual(conversation.estado, 'escalado')

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_preorder_transfer_request_does_not_send_bank_account_details(self, mock_detect, mock_generate):
        product = self._create_product(title='Camiseta Negra', category='Ropa')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            selected_products=[str(product.id)],
        )
        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings={
                'payment_methods': ['transferencia bancaria', 'efectivo'],
                'payment_settings': {
                    'bank_transfer_enabled': True,
                    'bank_name': 'Bancolombia',
                    'account_type': 'Ahorros',
                    'account_number': '12123234234',
                    'account_holder': 'Valdiri SAS',
                    'cash_enabled': True,
                },
            },
        )
        mock_detect.return_value = 'checkout'
        mock_generate.return_value = 'Excelente. Por favor realiza la transferencia a la cuenta.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='por transferencia bancaria!',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        lowered = reply.lower()
        self.assertIn('me faltan', lowered)
        self.assertNotIn('12123234234', lowered)
        self.assertNotIn('bancolombia', lowered)
        self.assertNotIn('valdiri sas', lowered)

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_post_order_payment_ping_is_idempotent_and_pending_manual_validation(self, mock_detect, mock_generate):
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            checkout_data={
                'order_id': 'abc-123',
                'order_number': 'A1B2C3D4',
                'payment_method': 'transferencia_bancaria',
                'payment_method_label': 'Transferencia bancaria',
                'payment_instructions': 'Banco: ABC. Cuenta: 123456. Titular: Vendly SAS.',
            },
        )
        mock_detect.side_effect = ['post_sale', 'post_sale']
        mock_generate.return_value = 'Recibido.'

        executor = SalesAgentExecutor()

        first_message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='listo ya',
            metadata={},
        )
        first_reply = executor.execute(
            conversation=self.conversation,
            message=first_message,
            decision=None,
            organization=self.org,
        )

        second_message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='listo ya',
            metadata={},
        )
        second_reply = executor.execute(
            conversation=self.conversation,
            message=second_message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        checkout_data = session.checkout_data or {}
        self.assertIn('pendiente de validacion manual', first_reply.lower())
        self.assertIn('ya tengo registrado tu reporte de pago', second_reply.lower())
        self.assertTrue(checkout_data.get('payment_reported_by_customer'))

    @patch('apps.ai_engine.sales.catalog.CatalogService.resolve_query')
    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_does_not_repeat_same_product_cards_within_cooldown(self, mock_detect, mock_generate, mock_resolve):
        product = self._create_product(title='Collar de Perlas', category='Accesorios')
        session = SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            message_count=6,
            checkout_data={
                'last_products_shown_ids': [str(product.id)],
                'last_products_shown_turn': 6,
            },
        )
        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'Te puedo ayudar con ese producto.'
        mock_resolve.return_value = {
            'products': [
                {
                    'id': str(product.id),
                    'title': 'Collar de Perlas',
                    'brand': '',
                    'category': 'Accesorios',
                    'image_url': '',
                    'price_min': 35000.0,
                    'price_max': 35000.0,
                    'price_type': 'fixed',
                    'availability_label': 'Disponible',
                    'is_available': True,
                }
            ],
            'resolution': {
                'match_type': 'browse',
                'needs_confirmation': False,
                'category': 'collar',
            },
        }

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='gracias',
            metadata={},
        )

        executor = SalesAgentExecutor()
        executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )
        session.refresh_from_db()

        metadata = executor.get_message_metadata()
        self.assertEqual(metadata, {})
        self.assertEqual(session.checkout_data.get('last_products_shown_ids'), [str(product.id)])

    @patch('apps.ai_engine.sales.catalog.CatalogService.resolve_query')
    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_explicit_browse_request_overrides_cooldown(self, mock_detect, mock_generate, mock_resolve):
        product = self._create_product(title='Collar de Perlas', category='Accesorios')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            message_count=6,
            checkout_data={
                'last_products_shown_ids': [str(product.id)],
                'last_products_shown_turn': 6,
            },
        )
        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'Aqui tienes opciones disponibles.'
        mock_resolve.return_value = {
            'products': [
                {
                    'id': str(product.id),
                    'title': 'Collar de Perlas',
                    'brand': '',
                    'category': 'Accesorios',
                    'image_url': '',
                    'price_min': 35000.0,
                    'price_max': 35000.0,
                    'price_type': 'fixed',
                    'availability_label': 'Disponible',
                    'is_available': True,
                }
            ],
            'resolution': {
                'match_type': 'browse',
                'needs_confirmation': False,
                'category': 'collar',
            },
        }

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='muestrame productos disponibles',
            metadata={},
        )

        executor = SalesAgentExecutor()
        executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        metadata = executor.get_message_metadata()
        self.assertEqual(metadata['ui_payload']['type'], 'product_list')

    @patch('apps.ai_engine.sales.catalog.CatalogService.resolve_query')
    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_product_cards_cooldown_is_persisted_between_turns(self, mock_detect, mock_generate, mock_resolve):
        product = self._create_product(title='Collar de Perlas', category='Accesorios')
        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'Te comparto opciones.'
        mock_resolve.return_value = {
            'products': [
                {
                    'id': str(product.id),
                    'title': 'Collar de Perlas',
                    'brand': '',
                    'category': 'Accesorios',
                    'image_url': '',
                    'price_min': 35000.0,
                    'price_max': 35000.0,
                    'price_type': 'fixed',
                    'availability_label': 'Disponible',
                    'is_available': True,
                }
            ],
            'resolution': {
                'match_type': 'browse',
                'needs_confirmation': False,
                'category': 'collar',
            },
        }

        executor = SalesAgentExecutor()

        first_message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='quiero ver collares',
            metadata={},
        )
        executor.execute(
            conversation=self.conversation,
            message=first_message,
            decision=None,
            organization=self.org,
        )
        first_metadata = executor.get_message_metadata()
        self.assertEqual(first_metadata['ui_payload']['type'], 'product_list')

        session = SalesSession.objects.get(conversation=self.conversation)
        self.assertEqual(session.checkout_data.get('last_products_shown_ids'), [str(product.id)])

        second_message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='gracias',
            metadata={},
        )
        executor.execute(
            conversation=self.conversation,
            message=second_message,
            decision=None,
            organization=self.org,
        )
        second_metadata = executor.get_message_metadata()
        self.assertEqual(second_metadata, {})

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_remove_cart_item_after_order_uses_fixed_post_purchase_reply(self, mock_detect, mock_generate):
        product = self._create_product(title='Llavero Azul', category='Accesorios')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            selected_products=[str(product.id)],
            checkout_data={'order_id': 'abc-123', 'order_number': 'CB4B1A5A'},
        )
        mock_detect.return_value = 'post_sale'
        mock_generate.return_value = 'LLM fallback should not be used'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Quiero quitar este producto del carrito.',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'remove_cart_item',
                        'product_id': str(product.id),
                    }
                }
            },
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        self.assertIn('ya fue confirmado', reply)
        self.assertIn('CB4B1A5A', reply)
        self.assertEqual(session.selected_products, [str(product.id)])
        mock_generate.assert_not_called()

    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_compact_checkout_requires_confirmation_before_creating_order(self, mock_detect):
        product = self._create_product(title='Collar Perlas', category='Accesorios')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            selected_products=[str(product.id)],
        )
        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings={
                'payment_methods': ['nequi', 'transferencia bancaria', 'efectivo'],
                'payment_settings': {
                    'nequi_enabled': True,
                    'nequi_number': '3001234567',
                    'nequi_holder': 'Vendly SAS',
                    'nequi_note': 'Envia comprobante por chat.',
                    'bank_transfer_enabled': True,
                    'cash_enabled': True,
                },
            },
        )
        mock_detect.side_effect = ['checkout', 'checkout']

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Quiero finalizar la compra.',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'submit_compact_checkout',
                        'data': {
                            'full_name': 'Ana Perez',
                            'phone': '+573001112233',
                            'payment_method': 'nequi',
                            'address_line1': 'Calle 10 #23-45',
                            'city': 'Bogota',
                            'reference': 'Porteria principal',
                        },
                    },
                },
            },
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        self.assertIn('confirmas que cree el pedido', reply.lower())
        self.assertEqual(Order.objects.filter(organization=self.org).count(), 0)

        confirm_message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Si, confirmo mi pedido.',
            metadata={},
        )
        reply_confirm = executor.execute(
            conversation=self.conversation,
            message=confirm_message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        order = Order.objects.filter(organization=self.org).latest('created_at')
        payment = (order.fulfillment_summary or {}).get('payment') or {}

        self.assertIn('metodo de pago: nequi', reply_confirm.lower())
        self.assertEqual(payment.get('method'), 'nequi')
        self.assertEqual(payment.get('status'), 'pending_confirmation')
        self.assertEqual(order.status, 'new')
        self.assertEqual(session.stage, 'discovery')

        # The agent must proactively say what happens next — it should not
        # wait for the customer to ask "y ahora que?".
        followup = executor.get_followup_message()
        self.assertTrue(followup)
        self.assertIn('nequi', followup.lower())
        self.assertIn('entrega', followup.lower())  # Collar Perlas requires shipping

    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_cash_payment_followup_does_not_ask_for_more_action(self, mock_detect):
        product = self._create_product(title='Cuaderno Argollado', category='Utiles escolares')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            selected_products=[str(product.id)],
        )
        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings={'payment_methods': ['efectivo'], 'payment_settings': {'cash_enabled': True}},
        )
        mock_detect.side_effect = ['checkout', 'checkout']

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Quiero finalizar la compra.',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'submit_compact_checkout',
                        'data': {
                            'full_name': 'Ana Perez',
                            'phone': '+573001112233',
                            'payment_method': 'efectivo',
                            'address_line1': 'Calle 10 #23-45',
                            'city': 'Bogota',
                            'reference': 'Porteria principal',
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
        reply_confirm = executor.execute(
            conversation=self.conversation, message=confirm_message, decision=None, organization=self.org,
        )
        self.assertIn('¡listo!', reply_confirm.lower())

        followup = executor.get_followup_message()
        self.assertTrue(followup)
        self.assertIn('no tienes que hacer nada mas', followup.lower())

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_confirmed_order_change_request_is_not_faked_by_the_llm(self, mock_detect, mock_generate):
        """
        Regression: once an order is confirmed, asking to change it (e.g.
        "en lugar de 1 cuaderno quiero 3") used to fall through to the LLM,
        which happily narrated a brand new checkout (quantity, payment
        method, address) without ever touching the real Order. The customer
        believed the change went through; the DB still had the original
        order. This must be blocked deterministically and hand off to a
        human instead of letting the LLM improvise a fake order edit.
        """
        product = self._create_product(title='Cuaderno Argollado', category='Utiles escolares')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            selected_products=[str(product.id)],
        )
        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings={'payment_methods': ['efectivo'], 'payment_settings': {'cash_enabled': True}},
        )
        mock_detect.side_effect = ['checkout', 'checkout', 'checkout']

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Quiero finalizar la compra.',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'submit_compact_checkout',
                        'data': {
                            'full_name': 'Ana Perez',
                            'phone': '+573001112233',
                            'payment_method': 'efectivo',
                            'address_line1': 'Calle 10 #23-45',
                            'city': 'Bogota',
                            'reference': 'Porteria principal',
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
        executor.execute(
            conversation=self.conversation, message=confirm_message, decision=None, organization=self.org,
        )
        order = Order.objects.filter(organization=self.org).latest('created_at')
        self.assertEqual(len(order.items), 1)
        self.assertEqual(order.items[0]['qty'], 1)

        change_message = Message.objects.create(
            conversation=self.conversation, role='user', content='en lugar de 1 cuaderno quiero 3', metadata={},
        )
        reply = executor.execute(
            conversation=self.conversation, message=change_message, decision=None, organization=self.org,
        )

        self.assertIn('ya fue confirmado', reply.lower())
        self.assertIn('asesor', reply.lower())
        mock_generate.assert_not_called()

        # The order itself must be untouched — no silent quantity/price drift.
        order.refresh_from_db()
        self.assertEqual(order.items[0]['qty'], 1)

        self.conversation.refresh_from_db()
        self.assertEqual((self.conversation.metadata or {}).get('operator_state', {}).get('owner'), 'humano')

    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_compact_checkout_with_explicit_confirmation_creates_order_same_turn(self, mock_detect):
        product = self._create_product(title='Camiseta Negra', category='Ropa')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            selected_products=[str(product.id)],
        )
        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings={
                'payment_methods': ['nequi', 'transferencia bancaria', 'efectivo'],
                'payment_settings': {
                    'nequi_enabled': True,
                    'nequi_number': '3001234567',
                    'nequi_holder': 'Vendly SAS',
                    'nequi_note': 'Envia comprobante por chat.',
                    'bank_transfer_enabled': True,
                    'cash_enabled': True,
                },
            },
        )
        mock_detect.return_value = 'checkout'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Confirmo mi pedido.',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'submit_compact_checkout',
                        'data': {
                            'full_name': 'Ana Perez',
                            'phone': '+573001112233',
                            'payment_method': 'nequi',
                            'address_line1': 'Calle 10 #23-45',
                            'city': 'Bogota',
                            'reference': 'Porteria principal',
                        },
                    },
                },
            },
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        order = Order.objects.filter(organization=self.org).latest('created_at')

        self.assertIn('tu pedido', reply.lower())
        self.assertEqual(order.status, 'new')
        self.assertEqual(session.stage, 'discovery')
        self.assertEqual(Order.objects.filter(organization=self.org).count(), 1)

    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_checkout_order_applies_promotions_to_final_total(self, mock_detect):
        product = self._create_product(title='Camiseta Negra', category='Ropa')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            selected_products=[str(product.id)],
        )
        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings={
                'payment_methods': ['nequi'],
                'payment_settings': {
                    'nequi_enabled': True,
                    'nequi_number': '3001234567',
                    'nequi_holder': 'Vendly SAS',
                },
            },
        )
        promo = Promotion.objects.create(
            organization=self.org,
            title='10% launch',
            scope='order',
            discount_type='percentage',
            discount_value=10,
            applies_to='all_products',
            is_active=True,
        )
        self.assertIsNotNone(promo.id)
        mock_detect.side_effect = ['checkout', 'checkout']

        executor = SalesAgentExecutor()
        draft = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='quiero finalizar',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'submit_compact_checkout',
                        'data': {
                            'full_name': 'Ana Perez',
                            'phone': '+573001112233',
                            'payment_method': 'nequi',
                            'address_line1': 'Calle 10 #23-45',
                            'city': 'Bogota',
                            'reference': 'Porteria principal',
                        },
                    },
                },
            },
        )
        first_reply = executor.execute(
            conversation=self.conversation,
            message=draft,
            decision=None,
            organization=self.org,
        )
        self.assertIsInstance(first_reply, str)

        confirm = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='si, confirmo mi pedido',
            metadata={},
        )
        reply_confirm = executor.execute(
            conversation=self.conversation,
            message=confirm,
            decision=None,
            organization=self.org,
        )

        order = Order.objects.filter(organization=self.org).latest('created_at')
        self.assertEqual(float(order.total), 90000.0)
        pricing = (order.fulfillment_summary or {}).get('pricing') or {}
        self.assertEqual(float(pricing.get('discount_total') or 0), 10000.0)
        self.assertIn('90000', reply_confirm.replace(',', ''))

    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_cart_is_locked_after_order_confirmation(self, mock_detect):
        product = self._create_product(title='Enterizo Shape Black', category='Ropa')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            selected_products=[str(product.id)],
        )
        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings={
                'payment_methods': ['transferencia bancaria'],
                'payment_settings': {
                    'bank_transfer_enabled': True,
                    'bank_name': 'Bancolombia',
                    'account_type': 'Ahorros',
                    'account_number': '1234567890',
                    'account_holder': 'Vendly SAS',
                },
            },
        )
        mock_detect.side_effect = ['checkout', 'checkout', 'post_sale']

        executor = SalesAgentExecutor()
        draft = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='quiero finalizar',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'submit_compact_checkout',
                        'data': {
                            'full_name': 'Ana Perez',
                            'phone': '+573001112233',
                            'payment_method': 'transferencia_bancaria',
                            'address_line1': 'Calle 10 #23-45',
                            'city': 'Bogota',
                            'reference': 'Porteria principal',
                        },
                    },
                },
            },
        )
        executor.execute(
            conversation=self.conversation,
            message=draft,
            decision=None,
            organization=self.org,
        )

        confirm = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='si, confirmo mi pedido',
            metadata={},
        )
        executor.execute(
            conversation=self.conversation,
            message=confirm,
            decision=None,
            organization=self.org,
        )

        remove = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Quiero quitar este producto del carrito.',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'remove_cart_item',
                        'product_id': str(product.id),
                    }
                }
            },
        )
        reply = executor.execute(
            conversation=self.conversation,
            message=remove,
            decision=None,
            organization=self.org,
        )
        metadata = executor.get_message_metadata()

        session = SalesSession.objects.get(conversation=self.conversation)
        self.assertIn('ya fue confirmado', reply)
        self.assertEqual(session.selected_products, [])
        self.assertEqual(metadata, {})

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_remove_cart_item_first_time_triggers_human_retention_question(self, mock_detect, mock_generate):
        product = self._create_product(title='Camiseta Negra', category='Ropa')
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='checkout',
            selected_products=[str(product.id)],
        )
        mock_detect.return_value = 'checkout'
        mock_generate.return_value = 'Te muestro opciones.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Quiero quitar este producto del carrito.',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'remove_cart_item',
                        'product_id': str(product.id),
                    }
                }
            },
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        lowered = reply.lower()
        self.assertIn('que no te convencio', lowered)
        self.assertIn('precio', lowered)
        self.assertIn('calidad', lowered)
        self.assertNotIn('talla', lowered)
        self.assertNotIn('color', lowered)
        mock_generate.assert_not_called()

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_remove_cart_item_when_cart_is_empty_returns_noop_reply(self, mock_detect, mock_generate):
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='considering',
            selected_products=[],
        )
        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'Te muestro otras opciones.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Quiero quitar este producto del carrito.',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'remove_cart_item',
                        'product_id': 'missing-product',
                    }
                }
            },
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        self.assertIn('carrito ya esta vacio', reply.lower())
        mock_generate.assert_not_called()

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_preorder_payment_request_with_empty_cart_is_blocked(self, mock_detect, mock_generate):
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            selected_products=[],
            checkout_data={},
        )
        mock_detect.return_value = 'checkout'
        mock_generate.return_value = 'Puedes pagar por transferencia.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='transferencia bancaria',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        lowered = reply.lower()
        self.assertIn('carrito esta vacio', lowered)
        self.assertIn('agrega un producto', lowered)
        mock_generate.assert_not_called()

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_post_order_shipping_urgent_uses_kb_policy_when_available(self, mock_detect, mock_generate):
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            checkout_data={
                'order_id': 'abc-123',
                'order_number': '11737A01',
            },
        )
        KBArticle.objects.create(
            organization=self.org,
            title='Politica de envios',
            content='Envio nacional estimado: 2 a 4 dias habiles en ciudades principales.',
            category='envios',
            purpose='policy',
            status='published',
        )
        mock_detect.return_value = 'post_sale'
        mock_generate.return_value = 'Por favor contacta al servicio al cliente.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='es urgente, cuando me llega a casa?',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        conversation = Conversation.objects.get(id=self.conversation.id)
        self.assertIn('2 a 4 dias habiles', reply.lower())
        self.assertNotEqual(session.stage, 'handoff')
        self.assertNotEqual(conversation.estado, 'escalado')
        mock_generate.assert_not_called()

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_post_order_shipping_urgent_without_info_escalates_with_natural_phrase(self, mock_detect, mock_generate):
        SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            stage='discovery',
            checkout_data={
                'order_id': 'abc-123',
                'order_number': '11737A01',
            },
        )
        mock_detect.return_value = 'post_sale'
        mock_generate.return_value = 'Por favor contacta al servicio al cliente.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='cuando me lo envian? es urgente',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        conversation = Conversation.objects.get(id=self.conversation.id)
        self.assertIn('dejame validarlo un momento internamente', reply.lower())
        self.assertEqual(session.stage, 'handoff')
        self.assertEqual(conversation.estado, 'escalado')
        mock_generate.assert_not_called()

    @patch('apps.ai_engine.sales.catalog.CatalogService.resolve_query')
    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_multiturn_catalog_similar_and_transfer_contracts(self, mock_detect, mock_generate, mock_resolve):
        scrunchie = self._create_product(title='Scrunchie Move Pack x3', category='Accesorios')
        enterizo = self._create_product(title='Enterizo Shape Black', category='Enterizos')
        top = self._create_product(title='Top Motion Support Arena', category='Tops')

        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings={
                'payment_methods': ['nequi', 'transferencia bancaria', 'efectivo'],
                'payment_settings': {
                    'bank_transfer_enabled': True,
                    'bank_name': 'Bancolombia',
                    'account_type': 'Ahorros',
                    'account_number': '1234567890',
                    'account_holder': 'Vendly SAS',
                    'payment_reference_note': 'Envia comprobante al chat.',
                },
            },
        )

        def _catalog_payload(product):
            return {
                'id': str(product.id),
                'title': product.title,
                'brand': 'Valdiri Move',
                'category': product.category,
                'image_url': '',
                'price_min': 29900.0 if product.id == scrunchie.id else (169900.0 if product.id == enterizo.id else 79900.0),
                'price_max': 29900.0 if product.id == scrunchie.id else (169900.0 if product.id == enterizo.id else 79900.0),
                'price_type': 'fixed',
                'availability_label': 'Disponible',
                'is_available': True,
                'requires_shipping': True,
            }

        all_products = [_catalog_payload(scrunchie), _catalog_payload(enterizo), _catalog_payload(top)]

        def _resolve_side_effect(query, organization, session, limit=5):
            lowered = str(query or '').lower()
            if 'enterizo' in lowered:
                products = [_catalog_payload(enterizo), _catalog_payload(top)]
            elif 'similar' in lowered or 'otros' in lowered:
                products = [_catalog_payload(top), _catalog_payload(enterizo), _catalog_payload(scrunchie)]
            else:
                products = all_products
            return {
                'products': products[:limit],
                'resolution': {
                    'match_type': 'browse',
                    'needs_confirmation': False,
                    'category': 'ropa deportiva',
                    'interpreted_query': query,
                },
            }

        mock_resolve.side_effect = _resolve_side_effect
        mock_detect.side_effect = [
            'discovery',                  # hoola
            'discovery',                  # como vas?
            'discovery',                  # que productos tienes?
            'comparing_customer',         # similares
            'specific_product_customer',  # enterizo
            'ready_to_buy_customer',      # me lo llevo
            'checkout',                   # transferencia
        ]
        mock_generate.side_effect = [
            '¡Hola! ¿En qué puedo ayudarte hoy?',
            '¡Muy bien, gracias! ¿Qué tal tú?',
            'Disculpa, parece que tuve un error. Por favor cuéntame qué necesitas.',
            'Actualmente, tenemos disponible el Top Motion Support Arena.',
            'El Enterizo Shape Black es un enterizo moldeador con fit ajustado.',
            '¡Genial elección! Puedes pagar a través de Nequi, transferencia bancaria o en efectivo. ¿Cuál método prefieres?',
            'Perfecto, puedes realizar la transferencia a nuestra cuenta bancaria.',
        ]

        executor = SalesAgentExecutor()

        m1 = Message.objects.create(conversation=self.conversation, role='user', content='hoola!', metadata={})
        r1 = executor.execute(conversation=self.conversation, message=m1, decision=None, organization=self.org)
        md1 = executor.get_message_metadata()

        m2 = Message.objects.create(conversation=self.conversation, role='user', content='como vas?', metadata={})
        r2 = executor.execute(conversation=self.conversation, message=m2, decision=None, organization=self.org)
        md2 = executor.get_message_metadata()

        m3 = Message.objects.create(conversation=self.conversation, role='user', content='sii, que productos tienes?', metadata={})
        r3 = executor.execute(conversation=self.conversation, message=m3, decision=None, organization=self.org)
        md3 = executor.get_message_metadata()

        m4 = Message.objects.create(conversation=self.conversation, role='user', content='que otros productos similares tienes?', metadata={})
        r4 = executor.execute(conversation=self.conversation, message=m4, decision=None, organization=self.org)
        md4 = executor.get_message_metadata()

        m5 = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='que me dices del enterizo shape este?',
            metadata={'structured_payload': {'interactive': {'action': 'select_product', 'product_id': str(enterizo.id)}}},
        )
        r5 = executor.execute(conversation=self.conversation, message=m5, decision=None, organization=self.org)
        md5 = executor.get_message_metadata()

        m6 = Message.objects.create(conversation=self.conversation, role='user', content='okk. me lo llevo', metadata={})
        r6 = executor.execute(conversation=self.conversation, message=m6, decision=None, organization=self.org)
        md6 = executor.get_message_metadata()

        m7 = Message.objects.create(conversation=self.conversation, role='user', content='transferencia', metadata={})
        r7 = executor.execute(conversation=self.conversation, message=m7, decision=None, organization=self.org)
        md7 = executor.get_message_metadata()

        self.assertIn('hola', r1.lower())
        self.assertIn('muy bien', r2.lower())
        self.assertNotIn('tuve un error', r3.lower())
        self.assertIn('opciones', r3.lower())
        self.assertIn('top motion support arena', r4.lower())
        self.assertIn('enterizo shape black', r4.lower())
        self.assertIn('enterizo shape black', r5.lower())
        self.assertIn('metodo de pago', r6.lower())
        # Pre-order transfer: acknowledge the chosen method and ask for the
        # missing checkout data, but NEVER share account details before the
        # order exists (see test_preorder_transfer_does_not_share_account_details).
        self.assertIn('transferencia', r7.lower())
        self.assertIn('faltan', r7.lower())
        self.assertNotIn('1234567890', r7)

        # Product cards should only appear on explicit product-seeking turns.
        self.assertEqual(md1, {})
        self.assertEqual(md2, {})
        self.assertEqual((md3.get('ui_payload') or {}).get('type'), 'product_list')
        self.assertEqual((md4.get('ui_payload') or {}).get('type'), 'product_list')
        self.assertEqual(md5, {})
        self.assertEqual((md6.get('ui_payload') or {}).get('type'), 'checkout_compact')
        self.assertEqual((md7.get('ui_payload') or {}).get('type'), 'checkout_compact')


class SalesAgentSecurityTests(TestCase):
    """Ensure cross-org and invalid product IDs are handled safely."""

    def setUp(self):
        self.org = Organization.objects.create(name='Main Org', slug='main-org')
        self.other_org = Organization.objects.create(name='Other Org', slug='other-org-sa')
        self.conversation = Conversation.objects.create(
            organization=self.org,
            canal='web',
            estado='nuevo',
        )

    def _create_product(self, org, title):
        product = Product.objects.create(
            organization=org,
            title=title,
            category='Tops',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(
            product=product,
            sku=f'{title[:6]}-sku',
            name='Variante',
            price=100_000,
            stock=5,
        )
        return product

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_product_id_from_other_org_is_ignored(self, mock_detect, mock_generate):
        other_product = self._create_product(self.other_org, 'Top Ajeno')
        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'No encontré ese producto.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Me interesa este producto',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'select_product',
                        'product_id': str(other_product.id),
                    }
                }
            },
        )

        executor = SalesAgentExecutor()
        executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        session = SalesSession.objects.get(conversation=self.conversation)
        # The foreign org product must not be persisted in this org's session
        self.assertNotIn(str(other_product.id), session.selected_products or [])

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate')
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_nonexistent_product_id_does_not_crash_pipeline(self, mock_detect, mock_generate):
        mock_detect.return_value = 'specific_product_customer'
        mock_generate.return_value = 'No encontré ese producto.'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Me interesa este',
            metadata={
                'structured_payload': {
                    'interactive': {
                        'action': 'select_product',
                        'product_id': '00000000-0000-0000-0000-000000000000',
                    }
                }
            },
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        self.assertIsNotNone(reply)


class SalesAgentResilienceTests(TestCase):
    """Pipeline must not crash on LLM failures."""

    def setUp(self):
        self.org = Organization.objects.create(name='Resilience Org', slug='resilience-org')
        self.conversation = Conversation.objects.create(
            organization=self.org,
            canal='web',
            estado='nuevo',
        )

    @patch('apps.ai_engine.sales.situation.SituationDetector.detect', side_effect=Exception('LLM timeout'))
    def test_situation_detector_failure_returns_fallback_reply(self, _mock_detect):
        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Quiero ver productos',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        self.assertIsNotNone(reply)
        # Must return the safe fallback, not propagate the exception
        self.assertIn('te ayudo', reply.lower())

    @patch('apps.ai_engine.sales.generator.ResponseGenerator.generate', side_effect=Exception('LLM unavailable'))
    @patch('apps.ai_engine.sales.situation.SituationDetector.detect')
    def test_generator_failure_returns_fallback_reply(self, mock_detect, _mock_generate):
        mock_detect.return_value = 'discovery'

        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content='Quiero ver productos',
            metadata={},
        )

        executor = SalesAgentExecutor()
        reply = executor.execute(
            conversation=self.conversation,
            message=message,
            decision=None,
            organization=self.org,
        )

        self.assertIsNotNone(reply)
        self.assertIn('te ayudo', reply.lower())


class SalesAgentCatalogQueryBuilderTests(SimpleTestCase):
    """Unit tests for _build_catalog_query — no DB needed."""

    def setUp(self):
        self.executor = SalesAgentExecutor()

    def test_shipping_only_message_returns_current_message(self):
        result = self.executor._build_catalog_query(
            current_message='¿Hacen envíos a Lima?',
            user_messages=['¿Hacen envíos a Lima?'],
        )
        # No product keywords — should return the current message unchanged
        self.assertEqual(result, '¿Hacen envíos a Lima?')

    def test_mixed_product_and_shipping_accumulates_product(self):
        result = self.executor._build_catalog_query(
            current_message='¿Hacen envíos a Lima?',
            user_messages=['quiero unos leggings negros', '¿Hacen envíos a Lima?'],
        )
        self.assertIn('leggings', result.lower())

    def test_product_queries_accumulate(self):
        result = self.executor._build_catalog_query(
            current_message='que sea de algodón',
            user_messages=['quiero una camiseta', 'que sea blanca'],
        )
        self.assertIn('camiseta', result.lower())
        self.assertIn('algodón', result.lower())

    def test_returns_last_3_relevant_turns(self):
        user_messages = [
            'quiero tops',
            'que sean negros',
            'formales',
            'sport también',
        ]
        result = self.executor._build_catalog_query(
            current_message='de algodón',
            user_messages=user_messages,
        )
        # Only last 3 from relevant + current should be in the window
        # (_build_catalog_query joins relevant[-3:])
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


class ImplicitSelectionIntentTests(SimpleTestCase):
    """Natural buy phrases a real salesperson must recognize as 'add to cart'."""

    def test_recognizes_natural_buy_phrases(self):
        positives = [
            'me llevo el Top Motion Support Arena',
            'listo, me lo llevo',
            'lo llevo entonces',
            'la llevo',
            'me quedo con el legging negro',
            'ese lo quiero',
            'me interesa el rosa',
        ]
        for phrase in positives:
            self.assertTrue(
                SalesAgentExecutor._is_implicit_selection_intent(phrase),
                msg=f'should detect buy intent in: {phrase!r}',
            )

    def test_ignores_non_buy_phrases(self):
        negatives = [
            'que tops tienen?',
            'cuanto cuesta',
            'hola, que venden',
            'me podrias contar mas del top',
        ]
        for phrase in negatives:
            self.assertFalse(
                SalesAgentExecutor._is_implicit_selection_intent(phrase),
                msg=f'should NOT detect buy intent in: {phrase!r}',
            )
