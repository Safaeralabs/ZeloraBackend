"""
Sales Agent unit tests.
Tests stage classification, handoff detection, topic detection and active sales replies.
"""
from django.test import SimpleTestCase
from unittest.mock import MagicMock, patch

from apps.ai_engine.sales_agent import (
    BuyerProfile,
    BrandProfile,
    BusinessContext,
    CommerceRules,
    DECISION_ESCALATE,
    SalesPlaybook,
    STAGE_CHECKOUT_BLOCKED,
    STAGE_CONSIDERING,
    STAGE_DISCOVERING,
    STAGE_FOLLOW_UP_NEEDED,
    STAGE_INTENT_TO_BUY,
    SalesAgent,
    SalesContext,
    _build_context_block,
    _build_system_prompt,
    _guard_general_scope_request,
    _guard_out_of_scope_request,
    _guard_out_of_scope_brand_query,
    _avoid_consecutive_repeat,
    _check_handoff,
    _classify_stage,
    _create_followup_task,
    _detect_topics,
    _detect_close_signals,
    _handle_affiliation_qualification_flow,
    _handle_comfaguajira_service_flow,
    _heuristic_reply,
    _humanize_sales_reply,
    _strengthen_closing_reply,
)


class SalesAgentStageClassificationTests(SimpleTestCase):
    def _stage(self, text):
        stage, _ = _classify_stage(text.lower())
        return stage

    def test_intent_to_buy_price_query(self):
        self.assertEqual(self._stage('cuanto cuesta el producto?'), STAGE_INTENT_TO_BUY)

    def test_intent_to_buy_availability(self):
        self.assertEqual(self._stage('tienen disponible la talla l?'), STAGE_INTENT_TO_BUY)

    def test_intent_to_buy_shipping(self):
        self.assertEqual(self._stage('cuando llega si lo pido hoy?'), STAGE_INTENT_TO_BUY)

    def test_considering(self):
        self.assertEqual(self._stage('cual es la diferencia entre los dos modelos?'), STAGE_CONSIDERING)

    def test_checkout_blocked(self):
        self.assertEqual(self._stage('el pago rechazado no se que pasa'), STAGE_CHECKOUT_BLOCKED)

    def test_follow_up_needed(self):
        self.assertEqual(self._stage('lo pienso y despues les escribo'), STAGE_FOLLOW_UP_NEEDED)

    def test_discovering_fallback(self):
        self.assertEqual(self._stage('hola buenos dias'), STAGE_DISCOVERING)


class SalesAgentHandoffTests(SimpleTestCase):
    def _needs_handoff(self, text):
        from apps.ai_engine.sales_agent import _profile_buyer

        buyer = _profile_buyer(text.lower())
        return _check_handoff(text.lower(), buyer, SalesContext().business, SalesContext().playbook).needed

    def test_large_order_triggers_handoff(self):
        self.assertTrue(self._needs_handoff('necesito 100 unidades para mi negocio'))

    def test_negotiation_triggers_handoff(self):
        self.assertTrue(self._needs_handoff('quiero una negociacion especial'))

    def test_wholesale_triggers_handoff(self):
        self.assertTrue(self._needs_handoff('somos mayoristas, como funciona?'))

    def test_normal_query_no_handoff(self):
        self.assertFalse(self._needs_handoff('cuanto cuesta el producto x?'))


class SalesAgentHeuristicReplyTests(SimpleTestCase):
    def _reply(self, text, stage, products=None):
        from apps.ai_engine.sales_agent import _profile_buyer

        buyer = _profile_buyer(text.lower())
        return _heuristic_reply(
            message_text=text,
            stage=stage,
            buyer=buyer,
            products=products or [],
            stock_info=None,
            promotions=[],
            sales_ctx=SalesContext(),
        )

    def test_price_query_with_product(self):
        products = [{'title': 'Camiseta Basica', 'min_price': 45000, 'any_in_stock': True, 'variants': []}]
        reply = self._reply('cuanto cuesta?', STAGE_INTENT_TO_BUY, products)
        self.assertIn('45', reply)
        self.assertIn('Camiseta', reply)

    def test_shipping_query_reply_pushes_forward(self):
        reply = self._reply('cuando llega si lo pido hoy?', STAGE_INTENT_TO_BUY)
        self.assertTrue(any(token in reply.lower() for token in ('envios', 'tiempo estimado', 'opcion')))

    def test_payment_query_reply_is_actionable(self):
        reply = self._reply('como puedo pagar?', STAGE_INTENT_TO_BUY)
        self.assertTrue(any(token in reply.lower() for token in ('tarjeta', 'transferencia', 'siguiente paso')))

    def test_considering_with_products(self):
        products = [
            {'title': 'Modelo A', 'min_price': 50000, 'any_in_stock': True, 'variants': []},
            {'title': 'Modelo B', 'min_price': 70000, 'any_in_stock': False, 'variants': []},
        ]
        reply = self._reply('cual me recomiendas?', STAGE_CONSIDERING, products)
        self.assertIn('Modelo A', reply)
        self.assertTrue(any(token in reply.lower() for token in ('yo me iria por', 'te conviene', 'te cuento por que')))

    def test_follow_up_reply_still_advances(self):
        reply = self._reply('lo pienso', STAGE_FOLLOW_UP_NEEDED)
        self.assertTrue(any(token in reply.lower() for token in ('opcion', 'economica', 'durable', 'precio', 'entrega')))
        self.assertTrue(any(token in reply.lower() for token in ('dime', 'prefieres', 'te frena', 'conviene')))

    def test_checkout_blocked_reply_is_empatic(self):
        reply = self._reply('no me deja pagar', STAGE_CHECKOUT_BLOCKED)
        self.assertIn('inconveniente', reply.lower())

    def test_discovering_no_products_asks_for_need(self):
        reply = self._reply('hola', STAGE_DISCOVERING)
        self.assertTrue(any(token in reply.lower() for token in ('necesitas', 'recomiendo', 'producto')))

    def test_reply_avoids_robotic_formula(self):
        reply = self._reply('cuanto cuesta?', STAGE_INTENT_TO_BUY)
        self.assertNotIn('con gusto', reply.lower())
        self.assertNotIn('la mejor opcion para tu caso', reply.lower())

    def test_avoid_consecutive_repeat_advances_after_personal_use_answer(self):
        conversation = MagicMock()
        last_bot = MagicMock(role='bot', content='Tenemos estas opciones disponibles: - Legging Heat Control Negro - $119,900 disponible Es para ti, para regalo o para algo puntual?')
        last_user = MagicMock(role='user', content='es para mi')
        conversation.messages.order_by.return_value = [last_user, last_bot]

        reply = _avoid_consecutive_repeat(
            reply='Tenemos estas opciones disponibles: - Legging Heat Control Negro - $119,900 disponible Es para ti, para regalo o para algo puntual?',
            conversation=conversation,
            message_text='es para mi',
            stage=STAGE_DISCOVERING,
            buyer=BuyerProfile(),
            products=[{'title': 'Legging Heat Control Negro'}],
        )

        self.assertNotIn('es para ti, para regalo o para algo puntual', reply.lower())
        self.assertTrue(any(token in reply.lower() for token in ('talla', 'color', 'set')))


class SalesAgentTopicDetectionTests(SimpleTestCase):
    def test_detects_price_topic(self):
        topics = _detect_topics('cuanto cuesta?')
        self.assertIn('price', topics)

    def test_detects_shipping_topic(self):
        topics = _detect_topics('cuando llega el envio?')
        self.assertIn('shipping', topics)

    def test_detects_payment_topic(self):
        topics = _detect_topics('acepta transferencia?')
        self.assertIn('payment', topics)

    def test_detects_stock_topic(self):
        topics = _detect_topics('tienen disponible?')
        self.assertIn('stock', topics)


class SalesAgentClosingSignalTests(SimpleTestCase):
    def test_detects_payment_and_buy_signals(self):
        signals = _detect_close_signals('lo quiero, como pago y si tienen disponible')
        self.assertIn('explicit_buy_intent', signals)
        self.assertIn('payment_intent', signals)
        self.assertIn('availability_check', signals)

    def test_strengthens_closing_reply_when_ready(self):
        reply = _strengthen_closing_reply(
            reply_text='Te confirmo que si hay disponibilidad.',
            stage=STAGE_INTENT_TO_BUY,
            close_signals=['payment_intent'],
            products=[{'title': 'Legging Heat Control Negro'}],
            sales_ctx=SalesContext(),
        )
        self.assertIn('prefieres pagar', reply.lower())


class SalesAgentRunIntegrationTest(SimpleTestCase):
    def setUp(self):
        self.agent = SalesAgent()

    @patch('apps.ai_engine.sales_agent._create_followup_task')
    @patch('apps.ai_engine.sales_tools.lookup_products', return_value=[
        {
            'id': 'prod-001',
            'title': 'Zapatos deportivos',
            'brand': 'RunFast',
            'category': 'Calzado',
            'description': 'Zapatos para correr',
            'offer_type': 'physical',
            'price_type': 'fixed',
            'requires_shipping': True,
            'requires_booking': False,
            'min_price': 120000,
            'variants': [{'id': 'v1', 'sku': 'ZD-42', 'name': 'Talla 42', 'price': '120000', 'available': 5, 'in_stock': True}],
            'any_in_stock': True,
            'tags': ['deporte', 'running'],
        }
    ])
    @patch('apps.ai_engine.sales_tools.get_active_promotions', return_value=[])
    @patch('apps.ai_engine.sales_tools.get_order_history', return_value=[])
    def test_buy_intent_with_product_returns_stage_and_reply(
        self, mock_history, mock_promos, mock_products, mock_followup
    ):
        org = MagicMock()
        org.id = 'org-test'
        org.name = 'Tienda Test'

        conversation = MagicMock()
        conversation.id = 'conv-test'
        conversation.contact_id = 'contact-test'
        conversation.contact = MagicMock()
        conversation.messages.order_by.return_value = []
        conversation.organization = org

        result = self.agent.run(
            message_text='cuanto cuesta y tienen disponible la talla 42?',
            conversation=conversation,
            organization=org,
        )

        self.assertEqual(result.agent, 'sales_agent')
        self.assertEqual(result.stage, STAGE_INTENT_TO_BUY)
        self.assertFalse(result.handoff.needed)
        self.assertIn('zapatos', result.reply_text.lower())
        self.assertGreater(result.confidence, 0.5)
        self.assertTrue(len(result.recommended_actions) > 0)

    @patch('apps.ai_engine.sales_tools.lookup_products', return_value=[])
    @patch('apps.ai_engine.sales_tools.get_active_promotions', return_value=[])
    @patch('apps.ai_engine.sales_tools.get_order_history', return_value=[])
    def test_high_value_order_triggers_handoff(
        self, mock_history, mock_promos, mock_products
    ):
        org = MagicMock()
        conversation = MagicMock()
        conversation.contact_id = None
        conversation.messages.order_by.return_value = []
        conversation.organization = org

        result = self.agent.run(
            message_text='necesito 100 unidades para distribucion mayorista',
            conversation=conversation,
            organization=org,
        )

        self.assertTrue(result.handoff.needed)
        self.assertEqual(result.decision, DECISION_ESCALATE)
        self.assertIn('asesor', result.reply_text.lower())


class SalesAgentFollowupTaskTests(SimpleTestCase):
    @patch('apps.ai_engine.models.AITask.objects.create')
    @patch('apps.ai_engine.models.AITask.objects.filter')
    def test_followup_task_is_deduplicated(self, mock_filter, mock_create):
        mock_filter.return_value.exists.return_value = True
        conversation = MagicMock()
        conversation.id = 'conv-1'
        conversation.contact_id = 'contact-1'
        organization = MagicMock()

        _create_followup_task(
            conversation=conversation,
            organization=organization,
            stage=STAGE_FOLLOW_UP_NEEDED,
            message_text='lo pienso y te aviso',
            buyer=BuyerProfile(priority='price', urgency='exploring'),
        )

        mock_create.assert_not_called()

    @patch('apps.ai_engine.models.AITask.objects.create')
    @patch('apps.ai_engine.models.AITask.objects.filter')
    def test_followup_task_sets_soft_cadence(self, mock_filter, mock_create):
        mock_filter.return_value.exists.return_value = False
        conversation = MagicMock()
        conversation.id = 'conv-2'
        conversation.contact_id = 'contact-2'
        organization = MagicMock()

        _create_followup_task(
            conversation=conversation,
            organization=organization,
            stage=STAGE_FOLLOW_UP_NEEDED,
            message_text='mas tarde vuelvo',
            buyer=BuyerProfile(priority='quality', urgency='this_week'),
        )

        _, kwargs = mock_create.call_args
        self.assertEqual(kwargs['task_type'], 'sales_followup')
        self.assertEqual(kwargs['input_data']['cadence'], 'soft')
        self.assertEqual(kwargs['input_data']['max_attempts'], 2)


class SalesAgentHumanizationTests(SimpleTestCase):
    def test_humanize_reply_removes_corporate_phrases(self):
        reply = _humanize_sales_reply(
            'Con gusto te ayudo. Si quieres, te digo si esta es la mejor opcion para tu caso.',
            STAGE_INTENT_TO_BUY,
            'balanced',
        )
        self.assertNotIn('con gusto', reply.lower())
        self.assertNotIn('la mejor opcion para tu caso', reply.lower())
        self.assertIn('te cuento', reply.lower())


class SalesAgentPromptContextTests(SimpleTestCase):
    def test_system_prompt_includes_brand_playbook_buyer_and_rules(self):
        sales_ctx = SalesContext(
            business=BusinessContext(
                org_name='Safaera',
                what_you_sell='Tenis urbanos y accesorios',
                who_you_sell_to='Clientes jovenes que compran por chat',
            ),
            brand=BrandProfile(
                brand_name='Safaera',
                tone_of_voice='Cercano',
                formality_level='Casual profesional',
                brand_personality='Directa y agil',
                value_proposition='Ayudamos a elegir rapido',
                key_differentiators=['Envio rapido', 'Asesoria real'],
                recommended_phrases=['Te recomiendo esta opcion'],
                avoid_phrases=['Estimado cliente'],
            ),
            playbook=SalesPlaybook(
                opening_style='Entender necesidad',
                recommendation_style='Dar maximo 2 opciones',
                objection_style='Responder con empatia',
                closing_style='Cerrar con pregunta',
                follow_up_style='Retomar suave',
                upsell_style='Complemento util',
            ),
            commerce_rules=CommerceRules(
                discount_policy='Hasta 10% en combos',
                negotiation_policy='Solo en volumen',
                inventory_promise_rule='No prometer sin validar',
                delivery_promise_rule='No prometer mismo dia',
                return_policy_summary='Cambios en 30 dias',
                forbidden_promises=['Entrega garantizada hoy'],
            ),
            buyer_model={
                'ideal_buyers': ['Compradores frecuentes'],
                'common_objections': ['Esta caro'],
                'purchase_signals': ['Cuanto cuesta'],
                'low_intent_signals': ['Lo pienso'],
            },
        )

        prompt = _build_system_prompt(sales_ctx)
        self.assertIn('Frases recomendadas', prompt)
        self.assertIn('Playbook follow-up', prompt)
        self.assertIn('Compradores ideales', prompt)
        self.assertIn('Regla de descuentos', prompt)
        self.assertIn('Frases a evitar', prompt)

    def test_context_block_includes_operational_brand_memory(self):
        conversation = MagicMock()
        conversation.messages.order_by.return_value = []
        conversation.organization = MagicMock()

        sales_ctx = SalesContext(
            business=BusinessContext(
                org_name='Safaera',
                what_you_sell='Tenis urbanos',
                who_you_sell_to='Clientes que buscan estilo y comodidad',
                commercial_policies=['Cambios faciles'],
            ),
            brand=BrandProfile(
                brand_name='Safaera',
                tone_of_voice='Cercano',
                formality_level='Casual',
                brand_personality='Agil',
                value_proposition='Compra guiada por chat',
                key_differentiators=['Asesoria real'],
                recommended_phrases=['Te recomiendo'],
                avoid_phrases=['Con gusto'],
            ),
            playbook=SalesPlaybook(
                opening_style='Pregunta primero',
                closing_style='Cierra con una pregunta',
            ),
            commerce_rules=CommerceRules(
                discount_policy='10% en combos',
                return_policy_summary='Cambios en 30 dias',
            ),
            buyer_model={
                'ideal_buyers': ['Compradores frecuentes'],
                'common_objections': ['Esta caro'],
            },
            catalog_snapshot=[{'title': 'Tenis Core', 'category': 'Calzado', 'min_price': 120000, 'any_in_stock': True}],
            knowledge_snapshot=[{'type': 'article', 'title': 'Cambios', 'category': 'Politicas', 'content': 'Cambios en 30 dias'}],
        )

        block = _build_context_block(
            stage=STAGE_CONSIDERING,
            buyer=BuyerProfile(priority='quality', urgency='this_week'),
            products=[],
            stock_info=None,
            promotions=[],
            sales_ctx=sales_ctx,
            conversation=conversation,
        )
        self.assertIn('Playbook activo', block)
        self.assertIn('Buyer model', block)
        self.assertIn('Frases a evitar', block)
        self.assertIn('Regla devoluciones', block)


class SalesAgentBrandScopeTests(SimpleTestCase):
    def test_guard_blocks_other_company_identity_question(self):
        sales_ctx = SalesContext(
            business=BusinessContext(
                org_name='Valdiri Move',
                what_you_sell='Ropa deportiva femenina',
                who_you_sell_to='Mujeres que compran por chat',
            ),
            brand=BrandProfile(
                brand_name='Valdiri Move',
                tone_of_voice='Cercano',
            ),
            catalog_snapshot=[
                {'title': 'Enterizo Shape Black', 'brand': 'Valdiri Move', 'category': 'Enterizos'},
            ],
        )

        reply = _guard_out_of_scope_brand_query('Que es Comfaguajira?', sales_ctx)

        self.assertIsNotNone(reply)
        self.assertIn('Valdiri Move', reply)
        self.assertNotIn('caja de compensacion', reply.lower())

    def test_guard_allows_same_brand_identity_question(self):
        sales_ctx = SalesContext(
            business=BusinessContext(
                org_name='Valdiri Move',
                what_you_sell='Ropa deportiva femenina',
            ),
            brand=BrandProfile(
                brand_name='Valdiri Move',
                tone_of_voice='Cercano',
            ),
        )

        reply = _guard_out_of_scope_brand_query('Que es Valdiri Move?', sales_ctx)

        self.assertIsNone(reply)

    def test_system_prompt_explicitly_forbids_other_companies(self):
        prompt = _build_system_prompt(
            SalesContext(
                business=BusinessContext(org_name='Valdiri Move', what_you_sell='Ropa deportiva femenina'),
                brand=BrandProfile(brand_name='Valdiri Move'),
            )
        )

        self.assertIn('Nunca des informacion sobre otra empresa', prompt)

    def test_guard_blocks_unrelated_topic_even_without_other_brand(self):
        sales_ctx = SalesContext(
            business=BusinessContext(
                org_name='Valdiri Move',
                what_you_sell='Ropa deportiva femenina',
            ),
            brand=BrandProfile(
                brand_name='Valdiri Move',
                tone_of_voice='Cercano',
            ),
            catalog_snapshot=[
                {'title': 'Enterizo Shape Black', 'brand': 'Valdiri Move', 'category': 'Enterizos'},
            ],
        )

        result = _guard_out_of_scope_request('Como va a estar el clima en Barranquilla mañana?', sales_ctx)

        self.assertIsNotNone(result)
        self.assertEqual(result['kind'], 'unrelated_topic')
        self.assertIn('Valdiri Move', result['reply'])

    def test_guard_blocks_general_information_request_outside_scope(self):
        sales_ctx = SalesContext(
            business=BusinessContext(
                org_name='Comfaguajira',
                what_you_sell='Subsidios, afiliaciones, certificados y servicios para afiliados',
            ),
            brand=BrandProfile(
                brand_name='Comfaguajira',
                tone_of_voice='Cercano',
            ),
        )

        result = _guard_general_scope_request('Hablame sobre la guajira', sales_ctx)

        self.assertIsNotNone(result)
        self.assertEqual(result['kind'], 'unrelated_topic')
        self.assertIn('Comfaguajira', result['reply'])
        self.assertIn('afiliaciones', result['reply'].lower())

    def test_run_marks_out_of_scope_in_context_when_topic_is_unrelated(self):
        agent = SalesAgent()
        org = MagicMock()
        org.name = 'Valdiri Move'
        conversation = MagicMock()
        conversation.contact_id = None
        conversation.contact = None
        conversation.messages.order_by.return_value = []
        conversation.organization = org

        with patch('apps.ai_engine.sales_agent._load_sales_context', return_value=SalesContext(
            business=BusinessContext(org_name='Valdiri Move', what_you_sell='Ropa deportiva femenina'),
            brand=BrandProfile(brand_name='Valdiri Move'),
        )):
            result = agent.run(
                message_text='Quien gano el partido ayer?',
                conversation=conversation,
                organization=org,
            )

        self.assertEqual(result.decision, 'discard')
        self.assertTrue(result.context_used.get('out_of_scope'))
        self.assertEqual(result.context_used.get('out_of_scope_kind'), 'unrelated_topic')


class SalesAgentStructuredFlowTests(SimpleTestCase):
    def _comfaguajira_context(self):
        return SalesContext(
            business=BusinessContext(
                org_name='Comfaguajira',
                org_slug='comfaguajira',
                what_you_sell='Subsidios, creditos, educacion y servicios para afiliados',
            ),
            brand=BrandProfile(
                brand_name='Comfaguajira',
                tone_of_voice='Cercano',
            ),
        )

    def test_flow_starts_for_comfaguajira_service_interest(self):
        conversation = MagicMock()
        conversation.metadata = {}
        conversation.contact = None

        result = _handle_affiliation_qualification_flow(
            message_text='Quiero saber el precio del teatro',
            conversation=conversation,
            sales_ctx=self._comfaguajira_context(),
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.decision, 'qualify')
        self.assertIn('eres afiliado', result.reply_text.lower())
        self.assertEqual(conversation.metadata['active_flow']['step'], 'ask_affiliation')

    def test_flow_moves_to_category_when_user_is_affiliated(self):
        conversation = MagicMock()
        conversation.metadata = {
            'active_flow': {
                'name': 'comfaguajira_affiliation',
                'step': 'ask_affiliation',
                'status': 'active',
                'data': {},
            },
            'qualification': {},
        }
        conversation.contact = None

        result = _handle_affiliation_qualification_flow(
            message_text='Soy afiliado',
            conversation=conversation,
            sales_ctx=self._comfaguajira_context(),
        )

        self.assertIsNotNone(result)
        self.assertIn('categoria es a, b o c', result.reply_text.lower())
        self.assertEqual(conversation.metadata['active_flow']['step'], 'ask_category')

    def test_flow_completes_for_particular(self):
        conversation = MagicMock()
        conversation.metadata = {
            'active_flow': {
                'name': 'comfaguajira_affiliation',
                'step': 'ask_affiliation',
                'status': 'active',
                'data': {},
            },
            'qualification': {},
        }
        conversation.contact = None

        result = _handle_affiliation_qualification_flow(
            message_text='Soy particular',
            conversation=conversation,
            sales_ctx=self._comfaguajira_context(),
        )

        self.assertIsNotNone(result)
        self.assertEqual(conversation.metadata['qualification']['affiliate_status'], 'particular')
        self.assertNotIn('active_flow', conversation.metadata)

    def test_affiliation_flow_hands_over_to_theater_flow(self):
        conversation = MagicMock()
        conversation.metadata = {
            'active_flow': {
                'name': 'comfaguajira_affiliation',
                'step': 'ask_category',
                'status': 'active',
                'data': {'pending_service': 'theater'},
            },
            'qualification': {'affiliate_status': 'afiliado'},
        }
        conversation.contact = None

        result = _handle_affiliation_qualification_flow(
            message_text='Categoria B',
            conversation=conversation,
            sales_ctx=self._comfaguajira_context(),
        )

        self.assertIsNotNone(result)
        self.assertEqual(conversation.metadata['active_flow']['name'], 'comfaguajira_theater_booking')
        self.assertEqual(conversation.metadata['active_flow']['step'], 'ask_event_type')
        self.assertIn('tipo de evento', result.reply_text.lower())

    def test_theater_flow_completes_with_quote(self):
        conversation = MagicMock()
        conversation.metadata = {
            'active_flow': {
                'name': 'comfaguajira_theater_booking',
                'step': 'ask_duration',
                'status': 'active',
                'data': {'event_type': 'cultural', 'schedule': 'diurno'},
            },
            'qualification': {'affiliate_status': 'afiliado', 'affiliate_category': 'B'},
        }
        conversation.contact = None

        result = _handle_comfaguajira_service_flow(
            message_text='Lo necesito 4 horas',
            conversation=conversation,
            sales_ctx=self._comfaguajira_context(),
        )

        self.assertIsNotNone(result)
        self.assertNotIn('active_flow', conversation.metadata)
        self.assertIn('50% de anticipo', result.reply_text.lower())
        self.assertIn('$1,057,400', result.reply_text)

    def test_nutrition_flow_uses_affiliate_category_for_subsidy(self):
        conversation = MagicMock()
        conversation.metadata = {
            'active_flow': {
                'name': 'comfaguajira_nutrition_quote',
                'step': 'ask_interest',
                'status': 'active',
                'data': {'child_age_months': 24},
            },
            'qualification': {'affiliate_status': 'afiliado', 'affiliate_category': 'A'},
        }
        conversation.contact = None

        result = _handle_comfaguajira_service_flow(
            message_text='Consulta y formula',
            conversation=conversation,
            sales_ctx=self._comfaguajira_context(),
        )

        self.assertIsNotNone(result)
        self.assertNotIn('active_flow', conversation.metadata)
        self.assertIn('$13,000', result.reply_text)
        self.assertIn('75%', result.reply_text)
