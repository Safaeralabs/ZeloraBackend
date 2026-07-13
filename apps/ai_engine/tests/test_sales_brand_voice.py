from types import SimpleNamespace

from django.test import TestCase

from apps.ai_engine.sales.brand import BrandVoice
from apps.ai_engine.sales.generator import ResponseGenerator
from apps.ai_engine.sales.validator import ResponseValidator


FULL_RUNTIME_CONFIG = {
    'sales_agent': {
        'name': 'Lia',
        'persona': 'consultiva y agil',
        'mission_statement': 'llevar conversaciones a cierre',
        'response_language': 'es',
        'competitor_response': 'vuelve a los diferenciales reales',
        'playbook': {
            'opening_style': 'saludo breve y pregunta por la ocasion',
            'recommendation_style': 'maximo dos opciones con beneficio concreto',
            'objection_style': 'valida la objecion y responde con un beneficio',
            'closing_style': 'cierre directo con resumen del pedido',
            'follow_up_style': 'un solo recordatorio amable',
            'upsell_style': 'sugiere un complemento de menor precio',
        },
        'buyer_model': {
            'common_objections': ['es muy caro', 'no confio en pagos online'],
        },
        'commerce_rules': {
            'discount_policy': 'maximo 10% y solo en promos activas',
            'negotiation_policy': 'no se negocian precios de lista',
            'return_policy_summary': 'cambios dentro de 15 dias con etiqueta',
            'forbidden_claims': ['producto medicinal certificado'],
            'forbidden_promises': ['entrega el mismo dia'],
        },
    },
    'org_profile': {
        'what_you_sell': 'ropa deportiva femenina',
        'who_you_sell_to': 'mujeres activas de 20 a 40',
        'brand': {
            'tone_of_voice': 'cercano y directo',
            'formality_level': 'informal',
            'brand_personality': 'energica y honesta',
            'value_proposition': 'asesoria clara',
            'key_differentiators': ['tallaje real', 'tela nacional'],
            'preferred_closing_style': 'cierre suave sin presion',
            'urgency_style': 'urgencia baja, nunca presionar',
            'recommended_phrases': ['de una', 'te cuento'],
            'avoid_phrases': ['te aviso luego'],
            'customer_style_notes': 'tutea siempre',
        },
    },
}


class BrandVoicePromptTests(TestCase):
    def _build_prompt(self, strategy='recommend', runtime_config=None):
        session = SimpleNamespace(
            organization=SimpleNamespace(name='Vendly'),
            stage='discovery',
            selected_products=[],
            budget_min=None,
            budget_max=None,
            objections=[],
            category_interest='',
            checkout_data={},
        )
        return ResponseGenerator._build_system_prompt(
            session=session,
            situation='specific_product_customer',
            action={'response_strategy': strategy},
            context={'recommended_products': [], 'product_resolution': {}, 'kb_content': '', 'promotions': []},
            runtime_config=runtime_config if runtime_config is not None else FULL_RUNTIME_CONFIG,
        )

    def test_prompt_includes_full_brand_identity(self):
        prompt = self._build_prompt()
        self.assertIn('Vendes: ropa deportiva femenina', prompt)
        self.assertIn('Cliente tipico: mujeres activas de 20 a 40', prompt)
        self.assertIn('Personalidad de la marca: energica y honesta', prompt)
        self.assertIn('Nivel de formalidad: informal', prompt)
        self.assertIn('Notas de estilo con clientes: tutea siempre', prompt)
        self.assertIn('de una, te cuento', prompt)

    def test_prompt_includes_seller_directives_and_buyer_objections(self):
        prompt = self._build_prompt()
        self.assertIn('compórtate como un vendedor real', prompt)
        self.assertIn('Estilo para manejar objeciones: valida la objecion y responde con un beneficio', prompt)
        self.assertIn('es muy caro; no confio en pagos online', prompt)
        self.assertIn('sugiere un complemento de menor precio', prompt)
        self.assertIn('urgencia baja, nunca presionar', prompt)

    def test_prompt_includes_commerce_rules_as_hard_limits(self):
        prompt = self._build_prompt()
        self.assertIn('Politica de descuentos (no la excedas NUNCA): maximo 10% y solo en promos activas', prompt)
        self.assertIn('PROHIBIDO afirmar o prometer: producto medicinal certificado; entrega el mismo dia', prompt)

    def test_strategy_guidance_merges_playbook_style(self):
        recommend_prompt = self._build_prompt(strategy='recommend')
        self.assertIn('Estilo de la marca para este momento: maximo dos opciones con beneficio concreto', recommend_prompt)

        close_prompt = self._build_prompt(strategy='close')
        self.assertIn('Estilo de la marca para este momento: cierre directo con resumen del pedido', close_prompt)

    def test_close_strategy_falls_back_to_brand_closing_style(self):
        config = {
            'sales_agent': {'playbook': {}},
            'org_profile': {'brand': {'preferred_closing_style': 'cierre suave sin presion'}},
        }
        guidance = BrandVoice.strategy_guidance('close', config)
        self.assertIn('cierre suave sin presion', guidance)

    def test_empty_config_produces_valid_prompt_without_brand_sections(self):
        prompt = self._build_prompt(runtime_config={})
        self.assertNotIn('## Identidad comercial', prompt)
        self.assertIn('## Como vendes', prompt)
        self.assertIn('## Estrategia:', prompt)


class BrandVoiceExamplesTests(TestCase):
    def _config_with_examples(self, examples):
        config = {
            'sales_agent': dict(FULL_RUNTIME_CONFIG['sales_agent']),
            'org_profile': {
                **FULL_RUNTIME_CONFIG['org_profile'],
                'brand': {**FULL_RUNTIME_CONFIG['org_profile']['brand'], 'voice_examples': examples},
            },
        }
        return config

    def test_voice_examples_are_injected_as_imitation_section(self):
        config = self._config_with_examples([
            'Hola linda! Te cuento que esos leggings vuelan, ¿te separo uno?',
            'De una, te lo dejo listo para envio hoy mismo.',
        ])
        lines = BrandVoice.voice_example_lines(config)
        joined = '\n'.join(lines)
        self.assertIn('## Asi escribe la marca', joined)
        self.assertIn('te separo uno', joined)
        self.assertIn('NO su contenido', joined)

    def test_no_examples_produces_no_section(self):
        self.assertEqual(BrandVoice.voice_example_lines(self._config_with_examples([])), [])
        self.assertEqual(BrandVoice.voice_example_lines({}), [])

    def test_voice_examples_flow_from_v1_settings_blob(self):
        from apps.channels_config.settings_schema import normalise_settings

        raw_v1 = {
            'brand_profile': {
                'voice_examples': ['  Con gusto le muestro nuestra coleccion.  ', '', 42],
            },
        }
        normalized = normalise_settings(raw_v1)
        self.assertEqual(
            normalized['org_profile']['brand']['voice_examples'],
            ['Con gusto le muestro nuestra coleccion.'],
        )
        joined = '\n'.join(BrandVoice.voice_example_lines(normalized))
        self.assertIn('Con gusto le muestro nuestra coleccion.', joined)


class BrandVoiceConversationalStyleTests(TestCase):
    def _config_with_brand(self, **brand_fields):
        return {
            'sales_agent': {},
            'org_profile': {'brand': brand_fields},
        }

    def test_informal_brand_gets_colloquial_guidance(self):
        joined = '\n'.join(
            BrandVoice.conversational_style_lines(FULL_RUNTIME_CONFIG)
        )
        self.assertIn('"dale", "de una"', joined)
        self.assertNotIn('marca premium', joined)

    def test_formal_brand_does_not_get_street_colloquialisms(self):
        config = self._config_with_brand(
            formality_level='formal',
            tone_of_voice='elegante y sobrio',
            brand_personality='lujo discreto',
        )
        joined = '\n'.join(BrandVoice.conversational_style_lines(config))
        self.assertNotIn('"dale", "de una"', joined)
        self.assertIn('marca premium', joined)
        self.assertIn('## Estilo conversacional humano', joined)

    def test_informal_marker_wins_over_formal_substring(self):
        # 'informal' contains 'formal'; the informal marker must win.
        config = self._config_with_brand(formality_level='informal')
        self.assertFalse(BrandVoice._is_formal_brand(config))

    def test_empty_config_defaults_to_casual_style(self):
        joined = '\n'.join(BrandVoice.conversational_style_lines({}))
        self.assertIn('"dale", "de una"', joined)

    def test_system_prompt_uses_conditional_style_block(self):
        session = SimpleNamespace(
            organization=SimpleNamespace(name='Vendly'),
            stage='discovery',
            selected_products=[],
            budget_min=None,
            budget_max=None,
            objections=[],
            category_interest='',
            checkout_data={},
        )
        formal_config = self._config_with_brand(formality_level='formal', tone_of_voice='elegante')
        prompt = ResponseGenerator._build_system_prompt(
            session=session,
            situation='specific_product_customer',
            action={'response_strategy': 'recommend'},
            context={'recommended_products': [], 'product_resolution': {}, 'kb_content': '', 'promotions': []},
            runtime_config=formal_config,
        )
        self.assertIn('## Estilo conversacional humano', prompt)
        self.assertNotIn('"dale", "de una"', prompt)


class BrandGuardTests(TestCase):
    def test_brand_guard_collects_avoid_and_forbidden_phrases(self):
        guard = BrandVoice.brand_guard(FULL_RUNTIME_CONFIG)
        self.assertEqual(guard['avoid_phrases'], ['te aviso luego'])
        self.assertIn('producto medicinal certificado', guard['forbidden_claims'])
        self.assertIn('entrega el mismo dia', guard['forbidden_claims'])

    def test_validator_strips_avoid_phrases(self):
        context = {'brand_guard': {'avoid_phrases': ['te aviso luego'], 'forbidden_claims': []}}
        reply = 'Tenemos ese top disponible. Te aviso luego cuando llegue mas stock. ¿Quieres verlo?'
        cleaned = ResponseValidator.validate(reply, context)
        self.assertNotIn('aviso luego', cleaned.lower())
        self.assertIn('top disponible', cleaned)
        self.assertIn('¿Quieres verlo?', cleaned)

    def test_validator_strips_forbidden_claims(self):
        context = {'brand_guard': {'avoid_phrases': [], 'forbidden_claims': ['entrega el mismo dia']}}
        reply = 'Claro que si. Hacemos entrega el mismo dia en toda la ciudad.'
        cleaned = ResponseValidator.validate(reply, context)
        self.assertNotIn('mismo dia', cleaned.lower())
        self.assertIn('Claro que si.', cleaned)

    def test_validator_falls_back_when_everything_is_forbidden(self):
        context = {'brand_guard': {'avoid_phrases': ['te aviso luego'], 'forbidden_claims': []}}
        reply = 'Te aviso luego.'
        cleaned = ResponseValidator.validate(reply, context)
        self.assertTrue(cleaned)
        self.assertNotIn('aviso luego', cleaned.lower())

    def test_validator_without_brand_guard_keeps_reply(self):
        reply = 'Tenemos ese top disponible. ¿Quieres verlo?'
        self.assertEqual(ResponseValidator.validate(reply, {'recommended_products': []}), reply)
