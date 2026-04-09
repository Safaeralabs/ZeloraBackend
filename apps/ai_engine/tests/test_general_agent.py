"""
General Agent — test suite completo (19 casos en 3 capas).

Capa 1 — Lógica pura, sin DB ni LLM (SimpleTestCase):
  Tests  1-7  : _is_out_of_scope — corrección del scope guard
  Test   8    : _build_scope_terms — construcción del vocabulario

Capa 2 — GeneralAgent.run() con contexto mockeado (SimpleTestCase + patch):
  Tests  9-14 : flujo completo — greeting, out-of-scope, KB, handoff gap

Capa 3 — Respaldado por DB (Django TestCase):
  Tests 15-16 : _load_general_context — con y sin ChannelConfig
  Tests 17-18 : _lookup_relevant_knowledge — relevancia y límite duro
  Test  19    : _load_general_context — coerción de tipos en allowed_topics
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from apps.ai_engine.general_agent import (
    GeneralAgent,
    GeneralAgentContext,
    _build_scope_terms,
    _is_out_of_scope,
    _load_general_context,
    _lookup_relevant_knowledge,
)


# ─── fixture compartida ───────────────────────────────────────────────────────

def _comfaguajira_ctx(**overrides) -> GeneralAgentContext:
    """
    Contexto base de Comfaguajira reutilizado en todas las capas.
    Los overrides permiten variar campos específicos por test.
    """
    defaults = dict(
        agent_name='Comfa Asistente',
        organization_name='Comfaguajira',
        what_you_sell='Subsidios, creditos, educacion, recreacion y alquiler de espacios',
        who_you_sell_to='Afiliados, empresas afiliadas y particulares en La Guajira',
        mission='Mejorar la calidad de vida de los trabajadores guajiros',
        scope_notes='Responde sobre servicios de Comfaguajira y procesos de afiliacion.',
        allowed_topics=['recreacion', 'educacion', 'credito social', 'teatro', 'gimnasio'],
        blocked_topics=['politica partidista', 'competencia'],
        handoff_to_sales_when=['quiero inscribirme', 'quiero pagar'],
        handoff_to_human_when=['queja formal', 'tutela'],
        greeting_message='Hola, soy el asistente de Comfaguajira. ¿En qué te puedo ayudar hoy?',
        knowledge_snippets=[
            'Credito social: prestamos para salud, recreacion, turismo y educacion.',
            'Teatro Akuaipaa: alquiler para eventos educativos, culturales y empresariales.',
        ],
    )
    defaults.update(overrides)
    return GeneralAgentContext(**defaults)


# ══════════════════════════════════════════════════════════════════════════════
# CAPA 1 — Lógica pura
# ══════════════════════════════════════════════════════════════════════════════

class OutOfScopeTests(SimpleTestCase):
    """Tests 1-7: _is_out_of_scope"""

    def setUp(self):
        self.ctx = _comfaguajira_ctx()

    # ── Test 1 ────────────────────────────────────────────────────────────────
    def test_greeting_nunca_bloqueado(self):
        self.assertFalse(_is_out_of_scope('hola', self.ctx))
        self.assertFalse(_is_out_of_scope('buenas tardes', self.ctx))

    # ── Test 2 ────────────────────────────────────────────────────────────────
    def test_solicitud_ayuda_ambigua_no_bloqueada(self):
        self.assertFalse(_is_out_of_scope('necesito ayuda', self.ctx))
        self.assertFalse(_is_out_of_scope('tengo una pregunta', self.ctx))

    # ── Test 3 ────────────────────────────────────────────────────────────────
    def test_preguntas_sobre_servicios_propios_no_bloqueadas(self):
        """Servicios de la propia organización deben pasar el guard sin importar la phrasing."""
        self.assertFalse(_is_out_of_scope('cuanto cuesta el gimnasio?', self.ctx))
        self.assertFalse(_is_out_of_scope('como me inscribo al teatro akuaipaa', self.ctx))
        self.assertFalse(_is_out_of_scope('quiero saber sobre los cursos de educacion', self.ctx))

    # ── Test 4 ────────────────────────────────────────────────────────────────
    def test_senales_claramente_no_relacionadas_son_bloqueadas(self):
        self.assertTrue(_is_out_of_scope('como va a estar el clima manana', self.ctx))
        self.assertTrue(_is_out_of_scope('quien gano las elecciones', self.ctx))
        self.assertTrue(_is_out_of_scope('dame una receta de cocina', self.ctx))
        self.assertTrue(_is_out_of_scope('cual es el horoscopo de hoy', self.ctx))

    # ── Test 5 ────────────────────────────────────────────────────────────────
    def test_identidad_de_entidad_externa_bloqueada(self):
        """'hablame de X' o 'que es X' con X=marca externa → out of scope."""
        self.assertTrue(_is_out_of_scope('hablame de netflix', self.ctx))
        self.assertTrue(_is_out_of_scope('que es amazon', self.ctx))

    # ── Test 6 ────────────────────────────────────────────────────────────────
    def test_terminos_del_kb_expanden_el_scope(self):
        """
        'hablame de akuaipaa' sin KB snippets → bloqueado (entidad desconocida).
        Con KB snippets que mencionan akuaipaa → en scope (el agente conoce el término).
        """
        ctx_sin_kb = _comfaguajira_ctx(knowledge_snippets=[])
        self.assertTrue(_is_out_of_scope('hablame de akuaipaa', ctx_sin_kb))

        ctx_con_kb = _comfaguajira_ctx(knowledge_snippets=[
            'Teatro Akuaipaa: alquiler para eventos educativos, culturales y empresariales.',
        ])
        self.assertFalse(_is_out_of_scope('hablame de akuaipaa', ctx_con_kb))

    # ── Test 7 ────────────────────────────────────────────────────────────────
    def test_mensaje_vacio_nunca_fuera_de_scope(self):
        """Mensaje vacío o solo espacios no debe ser bloqueado — activa el greeting."""
        self.assertFalse(_is_out_of_scope('', self.ctx))
        self.assertFalse(_is_out_of_scope('   ', self.ctx))


class BuildScopeTermsTests(SimpleTestCase):
    """Test 8: _build_scope_terms — construcción del vocabulario de scope."""

    def test_incluye_tokens_del_nombre_de_org(self):
        ctx = _comfaguajira_ctx()
        terms = _build_scope_terms(ctx)
        self.assertIn('comfaguajira', terms)

    def test_incluye_allowed_topics(self):
        ctx = _comfaguajira_ctx()
        terms = _build_scope_terms(ctx)
        self.assertIn('recreacion', terms)
        self.assertIn('educacion', terms)
        self.assertIn('gimnasio', terms)

    def test_incluye_tokens_de_kb_snippets(self):
        ctx = _comfaguajira_ctx()
        terms = _build_scope_terms(ctx)
        # 'prestamos' viene del primer KB snippet
        self.assertIn('prestamos', terms)
        # 'akuaipaa' viene del segundo KB snippet
        self.assertIn('akuaipaa', terms)

    def test_excluye_blocked_topics_del_vocabulario(self):
        """Un token que está en blocked_topics no debe estar en el scope set."""
        ctx = _comfaguajira_ctx(
            allowed_topics=['competencia'],
            blocked_topics=['competencia'],
        )
        terms = _build_scope_terms(ctx)
        self.assertNotIn('competencia', terms)

    def test_tokens_cortos_excluidos(self):
        """Tokens de menos de 4 caracteres causan falsos positivos — deben filtrarse."""
        ctx = _comfaguajira_ctx(what_you_sell='luz gas sol pan')
        terms = _build_scope_terms(ctx)
        for short in ('luz', 'gas', 'sol', 'pan'):
            self.assertNotIn(short, terms)


# ══════════════════════════════════════════════════════════════════════════════
# CAPA 2 — GeneralAgent.run() con contexto mockeado
# ══════════════════════════════════════════════════════════════════════════════

class GeneralAgentRunTests(SimpleTestCase):
    """
    Tests 9-14: flujo completo del agente sin tocar DB ni LLM.
    Se mockea _load_general_context para aislar la lógica de run().
    """

    def _run(self, message: str, ctx_overrides: dict | None = None) -> object:
        ctx = _comfaguajira_ctx(**(ctx_overrides or {}))
        with patch('apps.ai_engine.general_agent._load_general_context', return_value=ctx):
            return GeneralAgent().run(
                message_text=message,
                conversation=MagicMock(),
                organization=MagicMock(),
            )

    # ── Test 9 ────────────────────────────────────────────────────────────────
    def test_mensaje_vacio_retorna_greeting_configurado(self):
        result = self._run('')
        self.assertEqual(
            result.reply_text,
            'Hola, soy el asistente de Comfaguajira. ¿En qué te puedo ayudar hoy?',
        )

    # ── Test 10 ───────────────────────────────────────────────────────────────
    def test_mensaje_vacio_sin_greeting_usa_agent_name(self):
        result = self._run('', {'greeting_message': ''})
        self.assertIn('Comfa Asistente', result.reply_text)

    # ── Test 11 ───────────────────────────────────────────────────────────────
    def test_fuera_de_scope_reply_menciona_what_you_sell(self):
        result = self._run('como va a estar el clima manana')
        self.assertTrue(result.out_of_scope)
        self.assertEqual(result.intent, 'out_of_scope')
        # El reply debe mencionar al menos uno de los términos del negocio
        reply_lower = result.reply_text.lower()
        business_words = ('subsidio', 'educacion', 'recreacion', 'credito', 'alquiler', 'espacio')
        self.assertTrue(
            any(word in reply_lower for word in business_words),
            msg=f'Reply fuera-de-scope no menciona el negocio: "{result.reply_text}"',
        )

    # ── Test 12 ───────────────────────────────────────────────────────────────
    def test_en_scope_con_kb_usa_contenido_del_snippet(self):
        """
        Con KB snippets cargados el agente responde en scope y reporta
        knowledge_found > 0. No acoplamos la aserción a una palabra exacta
        porque el LLM puede variar el phrasing (acentos, sinónimos).
        """
        result = self._run('como funciona el credito social?')
        self.assertFalse(result.out_of_scope)
        self.assertEqual(result.intent, 'general_help')
        # El agente debe saber que encontró contexto KB
        self.assertGreater(result.context_used.get('knowledge_found', 0), 0)
        # El reply no debe estar vacío
        self.assertTrue(result.reply_text.strip())

    # ── Test 13 ───────────────────────────────────────────────────────────────
    def test_en_scope_sin_kb_cae_al_fallback_de_what_you_sell(self):
        """
        Sin KB, el reply debe mencionar el negocio (what_you_sell).
        Comparamos en minúsculas para ser agnósticos al LLM y al heurístico.
        """
        result = self._run(
            'que ofrecen?',
            {
                'knowledge_snippets': [],
                'what_you_sell': 'Subsidios y recreacion familiar',
            },
        )
        self.assertFalse(result.out_of_scope)
        reply_lower = result.reply_text.lower()
        self.assertTrue(
            'subsidio' in reply_lower or 'recreacion' in reply_lower or 'recreación' in reply_lower,
            msg=f'Reply sin KB no menciona el negocio: "{result.reply_text}"',
        )

    # ── Test 14 ───────────────────────────────────────────────────────────────
    def test_handoff_to_sales_when_no_se_evalua__bug_conocido(self):
        """
        LIMITANTE DOCUMENTADA: handoff_to_sales_when se carga en el contexto
        pero nunca se compara contra el mensaje entrante.

        Un mensaje que coincide exactamente con un trigger configurado
        ('quiero inscribirme ya') NO produce escalate_to_human=True ni
        ningún flag de escalación a ventas. El agente continúa con intent
        'general_help' como si no hubiera trigger.

        Este test fija el comportamiento ACTUAL. Si el agente se corrige
        para evaluar handoff_to_sales_when, este test deberá actualizarse
        añadiendo 'escalate_to_sales' a GeneralAgentResult y afirmando True.
        """
        result = self._run(
            'quiero inscribirme ya',
            {'handoff_to_sales_when': ['quiero inscribirme']},
        )
        # Comportamiento actual (incorrecto pero conocido):
        self.assertFalse(result.escalate_to_human)
        self.assertEqual(result.intent, 'general_help')
        # No existe campo 'escalate_to_sales' — también es parte del gap.
        self.assertFalse(hasattr(result, 'escalate_to_sales'))


# ══════════════════════════════════════════════════════════════════════════════
# CAPA 3 — Respaldado por DB
# ══════════════════════════════════════════════════════════════════════════════

class LookupRelevantKnowledgeTests(TestCase):
    """Tests 17-18: _lookup_relevant_knowledge — relevancia, límite y truncado."""

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import Organization
        from apps.knowledge_base.models import KBArticle

        cls.org = Organization.objects.create(
            name='Org Lookup Test',
            slug='org-lookup-test-kb',
        )
        # 6 artículos publicados sobre crédito → verificar límite de 4
        for i in range(6):
            KBArticle.objects.create(
                organization=cls.org,
                title=f'Credito social articulo {i}',
                content=f'Informacion sobre prestamos y creditos para afiliados numero {i}.',
                status='published',
                is_active=True,
            )
        # 1 artículo sobre tema no relacionado
        KBArticle.objects.create(
            organization=cls.org,
            title='Receta de cocina',
            content='Ingredientes: harina, agua, sal.',
            status='published',
            is_active=True,
        )
        # 1 artículo en borrador — NO debe aparecer nunca
        KBArticle.objects.create(
            organization=cls.org,
            title='Credito borrador confidencial',
            content='Articulo sobre creditos en borrador.',
            status='draft',
            is_active=True,
        )
        # 1 artículo con contenido muy largo → probar truncado
        KBArticle.objects.create(
            organization=cls.org,
            title='Articulo largo reglamento',
            content='reglamento ' + 'x' * 1000,
            status='published',
            is_active=True,
        )

    # ── Test 17a ──────────────────────────────────────────────────────────────
    def test_retorna_maximo_cuatro_snippets(self):
        snippets = _lookup_relevant_knowledge(
            organization=self.org,
            query='credito social prestamos afiliados',
        )
        self.assertLessEqual(len(snippets), 4)

    # ── Test 17b ──────────────────────────────────────────────────────────────
    def test_no_retorna_articulos_en_borrador(self):
        snippets = _lookup_relevant_knowledge(
            organization=self.org,
            query='credito borrador',
        )
        for snippet in snippets:
            self.assertNotIn('borrador', snippet.lower())

    # ── Test 17c ──────────────────────────────────────────────────────────────
    def test_query_irrelevante_no_retorna_articulos_no_relacionados(self):
        """Una query sobre recetas no debe devolver artículos sobre créditos."""
        snippets = _lookup_relevant_knowledge(
            organization=self.org,
            query='receta cocina harina',
        )
        for snippet in snippets:
            self.assertNotIn('credito', snippet.lower())

    # ── Test 17d ──────────────────────────────────────────────────────────────
    def test_query_vacia_retorna_lista_vacia(self):
        snippets = _lookup_relevant_knowledge(organization=self.org, query='')
        self.assertEqual(snippets, [])

    # ── Test 18 ───────────────────────────────────────────────────────────────
    def test_contenido_del_snippet_truncado_a_320_chars(self):
        """Cada snippet tiene formato 'titulo: contenido[:320]' — el contenido no supera 320 chars."""
        snippets = _lookup_relevant_knowledge(
            organization=self.org,
            query='reglamento largo articulo',
        )
        self.assertGreater(len(snippets), 0, msg='No se encontró el artículo largo.')
        for snippet in snippets:
            # El formato es "Título: contenido" — extraemos la parte del contenido
            content_part = snippet.split(': ', 1)[-1]
            self.assertLessEqual(
                len(content_part), 320,
                msg=f'Snippet supera 320 chars: {len(content_part)} chars.',
            )


class LoadGeneralContextTests(TestCase):
    """Tests 15-16: _load_general_context — carga desde ChannelConfig."""

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import Organization
        cls.org = Organization.objects.create(
            name='OrgContextTest',
            slug='org-context-test-ga',
        )

    # ── Test 15 ───────────────────────────────────────────────────────────────
    def test_sin_channel_config_retorna_defaults_seguros(self):
        """Sin ChannelConfig configurado el contexto no explota y tiene valores vacíos."""
        ctx = _load_general_context(self.org)

        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.organization_name, 'OrgContextTest')
        self.assertIsInstance(ctx.allowed_topics, list)
        self.assertIsInstance(ctx.blocked_topics, list)
        self.assertIsInstance(ctx.knowledge_snippets, list)
        # Nombre de agente fallback cuando no hay config
        self.assertEqual(ctx.agent_name, 'General Agent')

    # ── Test 16 ───────────────────────────────────────────────────────────────
    def test_config_completo_carga_todos_los_campos(self):
        """Con ChannelConfig completo todos los campos llegan correctamente al contexto."""
        from apps.channels_config.models import ChannelConfig

        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings={
                'general_agent_name': 'Asistente Pro',
                'what_you_sell': 'Planes de salud y recreacion',
                'who_you_sell_to': 'Afiliados activos',
                'general_agent_profile': {
                    'mission_statement': 'Servir con calidad',
                    'agent_persona': 'Amable y directa',
                    'scope_notes': 'Solo temas de salud y recreacion',
                    'allowed_topics': ['salud', 'recreacion', 'turismo'],
                    'blocked_topics': ['politica'],
                    'handoff_to_sales_when': ['quiero comprar', 'cuanto cuesta'],
                    'handoff_to_human_when': ['queja formal', 'tutela'],
                    'greeting_message': 'Hola, bienvenido a la caja.',
                    'response_language': 'es',
                },
                'ai_preferences': {
                    'general_agent': {
                        'handoff_mode': 'temprano',
                        'max_response_length': 'brief',
                        'model_name': 'gpt-4.1-nano',
                    },
                },
            },
        )

        ctx = _load_general_context(self.org)

        self.assertEqual(ctx.agent_name, 'Asistente Pro')
        self.assertEqual(ctx.what_you_sell, 'Planes de salud y recreacion')
        self.assertEqual(ctx.who_you_sell_to, 'Afiliados activos')
        self.assertEqual(ctx.mission, 'Servir con calidad')
        self.assertEqual(ctx.agent_persona, 'Amable y directa')
        self.assertEqual(ctx.scope_notes, 'Solo temas de salud y recreacion')
        self.assertIn('salud', ctx.allowed_topics)
        self.assertIn('recreacion', ctx.allowed_topics)
        self.assertIn('politica', ctx.blocked_topics)
        self.assertIn('quiero comprar', ctx.handoff_to_sales_when)
        self.assertIn('cuanto cuesta', ctx.handoff_to_sales_when)
        self.assertIn('queja formal', ctx.handoff_to_human_when)
        self.assertEqual(ctx.greeting_message, 'Hola, bienvenido a la caja.')
        self.assertEqual(ctx.response_language, 'es')
        self.assertEqual(ctx.handoff_mode, 'temprano')
        self.assertEqual(ctx.max_response_length, 'brief')
        self.assertEqual(ctx.model_name, 'gpt-4.1-nano')


class AllowedTopicsTypeCoercionTests(TestCase):
    """
    Test 19: _load_general_context con tipos no-string en allowed_topics/blocked_topics.

    Un campo JSON malformado puede contener dicts, ints o booleans.
    El contexto debe ignorarlos silenciosamente y solo conservar strings válidos.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import Organization
        cls.org = Organization.objects.create(
            name='OrgTypeTest',
            slug='org-type-coercion-ga',
        )

    def test_valores_no_string_en_allowed_topics_son_ignorados(self):
        """
        allowed_topics con [dict, int, bool, None, str] → solo el str válido pasa.
        El campo JSON acepta cualquier tipo; el agente debe ser robusto.
        """
        from apps.channels_config.models import ChannelConfig

        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings={
                'general_agent_profile': {
                    'allowed_topics': [{'clave': 'valor'}, 42, True, None, 'gimnasio', ''],
                    'blocked_topics': [False, 99, 'competencia'],
                },
            },
        )

        ctx = _load_general_context(self.org)

        # Solo el string válido 'gimnasio' debe estar en allowed_topics
        self.assertIn('gimnasio', ctx.allowed_topics)
        # Los no-strings y el string vacío deben ser ignorados
        for garbage in ("{'clave': 'valor'}", '42', 'True', 'False', '99', 'None', ''):
            self.assertNotIn(garbage, ctx.allowed_topics)

        # blocked_topics solo conserva 'competencia'
        self.assertIn('competencia', ctx.blocked_topics)
        self.assertNotIn('False', ctx.blocked_topics)
        self.assertNotIn('99', ctx.blocked_topics)

    def test_build_scope_terms_no_incluye_basura_de_tipos_mal_formados(self):
        """
        El vocabulario de scope no debe contener tokens como 'true', 'none', 'false'
        provenientes de valores booleanos o nulos mal convertidos.
        """
        from apps.channels_config.models import ChannelConfig

        ChannelConfig.objects.get_or_create(
            organization=self.org,
            channel='onboarding',
            defaults={
                'is_active': True,
                'settings': {
                    'general_agent_profile': {
                        'allowed_topics': [True, None, 'salud'],
                    },
                },
            },
        )

        ctx = _load_general_context(self.org)
        terms = _build_scope_terms(ctx)

        self.assertNotIn('true', terms)
        self.assertNotIn('none', terms)
        self.assertIn('salud', terms)
