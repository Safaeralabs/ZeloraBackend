from django.test import SimpleTestCase

from apps.ai_engine.sales.contracts import ResponseContractEnforcer


class ResponseContractEnforcerTests(SimpleTestCase):
    def test_replaces_internal_error_phrase_with_helpful_reply(self):
        reply = 'Disculpa, tuve un error procesando tu mensaje.'
        result = ResponseContractEnforcer.enforce(
            reply=reply,
            session_stage='discovery',
            action={},
            context={'recommended_products': [{'id': 'p1'}]},
            user_message='que tienes',
        )
        self.assertNotIn('error', result.lower())
        self.assertIn('opciones', result.lower())

    def test_checkout_without_payment_method_asks_for_payment_choice(self):
        result = ResponseContractEnforcer.enforce(
            reply='Perfecto, seguimos con tu pedido.',
            session_stage='checkout',
            action={'checkout_step': 2},
            context={
                'payment_profile': {
                    'methods': [
                        {'id': 'nequi', 'label': 'Nequi'},
                        {'id': 'transferencia_bancaria', 'label': 'Transferencia bancaria'},
                    ]
                },
                'checkout_data': {'compact_checkout_form': {}},
            },
            user_message='me lo llevo',
        )
        self.assertIn('metodo de pago', result.lower())

    def test_transfer_payment_includes_account_instructions(self):
        result = ResponseContractEnforcer.enforce(
            reply='Perfecto, puedes transferir.',
            session_stage='checkout',
            action={'checkout_step': 2},
            context={
                'payment_profile': {
                    'methods': [
                        {
                            'id': 'transferencia_bancaria',
                            'label': 'Transferencia bancaria',
                            'instructions': 'Banco: ABC. Cuenta: 123456. Titular: Vendly SAS.',
                        }
                    ]
                },
                'checkout_data': {
                    'order_id': 'abc-123',
                    'compact_checkout_form': {'payment_method': 'transferencia_bancaria'},
                },
            },
            user_message='transferencia',
        )
        lowered = result.lower()
        self.assertIn('transferencia', lowered)
        self.assertIn('cuenta', lowered)
        self.assertIn('titular', lowered)

    def test_preorder_transfer_does_not_share_account_details(self):
        result = ResponseContractEnforcer.enforce(
            reply='Perfecto, puedes transferir.',
            session_stage='checkout',
            action={'checkout_step': 2},
            context={
                'payment_profile': {
                    'methods': [
                        {
                            'id': 'transferencia_bancaria',
                            'label': 'Transferencia bancaria',
                            'instructions': 'Banco: ABC. Cuenta: 123456. Titular: Vendly SAS.',
                        }
                    ]
                },
                'checkout_data': {'compact_checkout_form': {'payment_method': 'transferencia_bancaria'}},
            },
            user_message='transferencia',
        )
        lowered = result.lower()
        self.assertIn('antes de pagar', lowered)
        self.assertNotIn('123456', lowered)

    def test_preorder_transfer_without_instructions_blocks_payment_until_order(self):
        result = ResponseContractEnforcer.enforce(
            reply='Perfecto, seguimos.',
            session_stage='checkout',
            action={'checkout_step': 2},
            context={
                'payment_profile': {
                    'methods': [
                        {'id': 'transferencia_bancaria', 'label': 'Transferencia bancaria', 'instructions': ''}
                    ]
                },
                'checkout_data': {'compact_checkout_form': {'payment_method': 'transferencia_bancaria'}},
            },
            user_message='transferencia',
        )
        self.assertIn('antes de pagar', result.lower())

    def test_similar_request_with_multiple_products_mentions_at_least_two(self):
        context = {
            'recommended_products': [
                {'title': 'Top Motion Support Arena', 'price_min': 79900},
                {'title': 'Enterizo Shape Black', 'price_min': 169900},
                {'title': 'Scrunchie Move Pack x3', 'price_min': 29900},
            ]
        }
        result = ResponseContractEnforcer.enforce(
            reply='Tengo un producto recomendado para ti.',
            session_stage='considering',
            action={},
            context=context,
            user_message='que otros productos similares tienes?',
        )
        lowered = result.lower()
        self.assertIn('top motion support arena', lowered)
        self.assertIn('enterizo shape black', lowered)
        metrics = (context.get('checkout_data') or {}).get('contract_metrics') or {}
        self.assertEqual(metrics.get('similar_contract_enforced'), 1)

    def test_similar_request_with_one_product_states_single_option(self):
        result = ResponseContractEnforcer.enforce(
            reply='Claro, te cuento.',
            session_stage='considering',
            action={},
            context={
                'recommended_products': [
                    {'title': 'Top Motion Support Arena', 'price_min': 79900},
                ]
            },
            user_message='tienes algo similar?',
        )
        self.assertIn('solo', result.lower())
        self.assertIn('top motion support arena', result.lower())

    def test_variant_question_enforces_real_sizes_when_context_has_variant_info(self):
        result = ResponseContractEnforcer.enforce(
            reply='No tengo informacion de tallas.',
            session_stage='considering',
            action={},
            context={
                'variant_info': {
                    'product_title': 'Enterizo Shape Black',
                    'labels_available': ['S', 'M'],
                    'labels_unavailable': ['L'],
                }
            },
            user_message='que tallas tienes disponibles?',
        )
        lowered = result.lower()
        self.assertIn('s', lowered)
        self.assertIn('m', lowered)
        self.assertIn('agotadas', lowered)

    def test_variant_question_without_snapshot_prompts_human_validation(self):
        result = ResponseContractEnforcer.enforce(
            reply='No tengo informacion de tallas.',
            session_stage='considering',
            action={},
            context={},
            user_message='la tienes en talla s?',
        )
        lowered = result.lower()
        self.assertIn('no tengo confirmacion de talla', lowered)
        self.assertIn('asesor humano', lowered)

    def test_post_order_transfer_question_returns_account_details(self):
        result = ResponseContractEnforcer.enforce(
            reply='Te compartiremos los datos luego.',
            session_stage='discovery',
            action={},
            context={
                'checkout_data': {
                    'order_id': 'abc-123',
                    'payment_method': 'transferencia_bancaria',
                    'payment_method_label': 'Transferencia bancaria',
                    'payment_instructions': 'Banco: ABC. Cuenta: 123456. Titular: Vendly SAS.',
                }
            },
            user_message='que cuenta es?',
        )
        lowered = result.lower()
        self.assertIn('cuenta', lowered)
        self.assertIn('titular', lowered)

    def test_post_order_transfer_where_to_transfer_phrase_returns_account_details(self):
        result = ResponseContractEnforcer.enforce(
            reply='No tengo ese producto disponible.',
            session_stage='discovery',
            action={},
            context={
                'checkout_data': {
                    'order_id': 'abc-123',
                    'payment_method': 'transferencia_bancaria',
                    'payment_method_label': 'Transferencia bancaria',
                    'payment_instructions': 'Banco: ABC. Cuenta: 123456. Titular: Vendly SAS.',
                }
            },
            user_message='donde transfiero?',
        )
        lowered = result.lower()
        self.assertIn('datos para pagar', lowered)
        self.assertIn('cuenta', lowered)
        self.assertIn('titular', lowered)
