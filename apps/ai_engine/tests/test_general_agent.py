from django.test import SimpleTestCase

from apps.ai_engine.general_agent import GeneralAgentContext, _is_out_of_scope


class GeneralAgentScopeTests(SimpleTestCase):
    def setUp(self) -> None:
        self.ctx = GeneralAgentContext(
            agent_name='General Agent',
            organization_name='Comfaguajira',
            what_you_sell='Subsidios, creditos, educacion, alquiler de espacios y teatro',
            who_you_sell_to='Afiliados, empresas y particulares',
            mission='Atencion y servicios de caja de compensacion',
            scope_notes='Responde sobre servicios de Comfaguajira y procesos de afiliacion.',
            knowledge_snippets=[
                'Credito social: prestamos para salud, recreacion, turismo y educacion.',
                'Teatro Akuaipaa: alquiler para eventos educativos, culturales y empresariales.',
            ],
        )

    def test_does_not_block_generic_greeting(self) -> None:
        self.assertFalse(_is_out_of_scope('hola', self.ctx))

    def test_does_not_block_ambiguous_help_request(self) -> None:
        self.assertFalse(_is_out_of_scope('necesito ayuda', self.ctx))

    def test_blocks_clear_unrelated_topic(self) -> None:
        self.assertTrue(_is_out_of_scope('como va a estar el clima manana', self.ctx))

    def test_blocks_other_entity_identity_request(self) -> None:
        self.assertTrue(_is_out_of_scope('hablame de netflix', self.ctx))

    def test_allows_business_question_without_exact_scope_term_overlap(self) -> None:
        self.assertFalse(_is_out_of_scope('quiero saber sobre afiliaciones', self.ctx))
