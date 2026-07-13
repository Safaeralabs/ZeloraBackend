from types import SimpleNamespace

from django.test import TestCase

from apps.ai_engine.sales.generator import ResponseGenerator


class ResponseGeneratorTests(TestCase):
    def test_build_system_prompt_includes_runtime_identity(self):
        session = SimpleNamespace(
            organization=SimpleNamespace(name='Vendly'),
            stage='discovery',
            selected_products=[],
            budget_min=None,
            budget_max=None,
            objections=[],
            category_interest='camisetas',
        )
        prompt = ResponseGenerator._build_system_prompt(
            session=session,
            situation='specific_product_customer',
            action={'response_strategy': 'recommend'},
            context={'recommended_products': [], 'product_resolution': {}, 'kb_content': '', 'promotions': []},
            runtime_config={
                'sales_agent': {
                    'name': 'Lia',
                    'persona': 'consultiva y agil',
                    'mission_statement': 'llevar conversaciones a cierre',
                    'response_language': 'es',
                    'competitor_response': 'vuelve a los diferenciales reales',
                },
                'org_profile': {
                    'brand': {
                        'tone_of_voice': 'cercano y directo',
                        'value_proposition': 'asesoria clara',
                        'avoid_phrases': ['te aviso luego'],
                    },
                },
            },
        )

        self.assertIn('Eres Lia de Vendly.', prompt)
        self.assertIn('Personalidad del agente: consultiva y agil', prompt)
        self.assertIn('Tono de voz: cercano y directo', prompt)
        self.assertIn('Frases a evitar: te aviso luego', prompt)
        self.assertIn('Categoria de interes: camisetas', prompt)

    def test_max_tokens_follow_response_length(self):
        self.assertEqual(
            ResponseGenerator._max_tokens_for_response_length({'sales_agent': {'max_response_length': 'brief'}}),
            220,
        )
        self.assertEqual(
            ResponseGenerator._max_tokens_for_response_length({'sales_agent': {'max_response_length': 'detailed'}}),
            500,
        )

    def test_resolve_generation_task_uses_ambiguous_language_on_short_checkout_messages(self):
        session = SimpleNamespace(stage='checkout')
        task = ResponseGenerator._resolve_generation_task(
            user_message='nequi',
            session=session,
            action={'response_strategy': 'close'},
        )
        self.assertEqual(task, 'ambiguous_language')

    def test_resolve_generation_task_keeps_strategy_when_not_ambiguous(self):
        session = SimpleNamespace(stage='considering')
        task = ResponseGenerator._resolve_generation_task(
            user_message='quiero ver opciones de camisas negras',
            session=session,
            action={'response_strategy': 'recommend'},
        )
        self.assertEqual(task, 'recommend')
