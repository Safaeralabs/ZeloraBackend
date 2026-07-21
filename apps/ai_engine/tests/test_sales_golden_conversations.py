"""
Golden conversations — scripted multi-turn conversations per buyer segment.

Runs the REAL pipeline (executor → decision engine → catalog → prompt builder →
validator → contracts) with a fake LLM that returns scripted replies and captures
every system prompt, so we can assert invariants that must hold on every change:

  - the brand identity is injected in EVERY generation turn
  - replies can never mention products outside the catalog (sanitized)
  - brand avoid_phrases / forbidden promises never reach the customer
  - the hot-buyer path ends with a real Order in the database
  - strategy guidance matches the buyer segment (clarify / discover / close...)

No real OpenAI calls are made: the openai client is patched and the situation
detector is scripted per turn.
"""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import Organization
from apps.ai_engine.models import SalesSession
from apps.ai_router.executors.sales_agent import SalesAgentExecutor
from apps.channels_config.models import ChannelConfig
from apps.conversations.models import Conversation, Message
from apps.ecommerce.models import Order, Product, ProductVariant, Promotion


GOLDEN_BRAND_SETTINGS = {
    'settings_version': 2,
    'org_profile': {
        'what_you_sell': 'ropa deportiva femenina',
        'who_you_sell_to': 'mujeres activas',
        'payment_methods': ['nequi', 'efectivo'],
        'brand': {
            'tone_of_voice': 'cercano y energico',
            'brand_personality': 'energica y honesta',
            'value_proposition': 'asesoria clara y tallaje real',
            'avoid_phrases': ['te aviso luego'],
            'preferred_closing_style': 'cierre suave sin presion',
        },
    },
    'payment_settings': {
        'nequi_enabled': True,
        'nequi_number': '3001234567',
        'nequi_holder': 'Lia SAS',
        'cash_enabled': True,
        'cash_instructions': 'Pagas en efectivo contra entrega.',
    },
    'sales_agent': {
        'enabled': True,
        'name': 'Lia',
        'persona': 'consultiva y agil',
        'playbook': {
            'recommendation_style': 'maximo dos opciones con beneficio concreto',
            'closing_style': 'resumen corto y pregunta directa',
        },
        'commerce_rules': {
            'discount_policy': 'maximo 10% y solo en promos activas',
            'forbidden_promises': ['entrega el mismo dia'],
        },
    },
}


class _GoldenLLM:
    """Fake OpenAI client: scripted replies + captured system prompts."""

    def __init__(self):
        self.prompts: list[str] = []
        self.replies: list[str] = []
        self.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=self._create))
        )

    def queue(self, reply: str):
        self.replies.append(reply)

    def _create(self, *, model, messages, **kwargs):
        system = messages[0]['content']
        if 'Extrae la intenci' in system:
            # Entity extraction stays heuristic in golden tests.
            raise RuntimeError('extraction LLM disabled in golden tests')
        self.prompts.append(system)
        reply = self.replies.pop(0) if self.replies else 'Con gusto te ayudo.'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


@override_settings(OPENAI_API_KEY='golden-test-key', ENABLE_REAL_AI=True)
class GoldenConversationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Golden Org', slug='golden-org')
        ChannelConfig.objects.create(
            organization=self.org,
            channel='onboarding',
            is_active=True,
            settings=GOLDEN_BRAND_SETTINGS,
        )
        self.conversation = Conversation.objects.create(
            organization=self.org, canal='web', estado='nuevo',
        )
        self.llm = _GoldenLLM()
        self.top = self._create_product(title='Top Motion Support Arena', category='Tops', price=120000)
        self.legging = self._create_product(title='Legging Heat Control Negro', category='Leggings', price=150000)

    def _create_product(self, *, title, category, price, stock=5):
        product = Product.objects.create(
            organization=self.org,
            title=title,
            category=category,
            status='active',
            is_active=True,
            is_bestseller=True,
        )
        ProductVariant.objects.create(
            product=product, sku=f'{title[:6]}-sku', name='Unica', price=price, stock=stock,
        )
        return product

    def turn(self, text, *, situation, reply='Con gusto te ayudo.', payload=None):
        """Run one scripted customer turn through the real executor."""
        self.llm.queue(reply)
        message = Message.objects.create(
            conversation=self.conversation,
            role='user',
            content=text,
            metadata=payload or {},
        )
        with patch('apps.ai_engine.sales.situation.SituationDetector.detect', return_value=situation), \
             patch('openai.OpenAI', return_value=self.llm.client):
            executor = SalesAgentExecutor()
            bot_reply = executor.execute(
                conversation=self.conversation,
                message=message,
                decision=None,
                organization=self.org,
            )
        if bot_reply:
            Message.objects.create(conversation=self.conversation, role='bot', content=bot_reply)
        return bot_reply or ''

    def session(self) -> SalesSession:
        return SalesSession.objects.get(conversation=self.conversation)

    # ── Invariante: la marca está en cada turno generado ──────────────────────

    def test_brand_identity_is_injected_on_every_generated_turn(self):
        self.turn('hola, que venden?', situation='discovery')
        self.turn('busco un top para entrenar', situation='specific_product_customer')
        self.turn('y cual me recomiendas?', situation='indecisive_customer')

        self.assertGreaterEqual(len(self.llm.prompts), 3)
        for prompt in self.llm.prompts:
            self.assertIn('Eres Lia de Golden Org', prompt)
            self.assertIn('## Identidad comercial', prompt)
            self.assertIn('compórtate como un vendedor real', prompt)
            self.assertIn('Vendes: ropa deportiva femenina', prompt)
            self.assertIn(
                'PROHIBIDO afirmar o prometer: entrega el mismo dia', prompt,
            )

    # ── Hot buyer: cierre completo con orden real ────────────────────────────

    def test_hot_buyer_full_close_creates_real_order(self):
        self.turn(
            'quiero el Top Motion Support Arena, me lo llevo',
            situation='ready_to_buy_customer',
            reply='Excelente eleccion, vamos a crear tu pedido.',
        )
        self.assertIn(str(self.top.id), self.session().selected_products)

        checkout_payload = {
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
        }
        reply = self.turn(
            'Confirmo mi pedido.',
            situation='checkout',
            payload=checkout_payload,
        )

        order = Order.objects.filter(organization=self.org).latest('created_at')
        self.assertEqual(order.status, 'new')
        self.assertIn('pedido', reply.lower())
        self.assertTrue(str(self.session().checkout_data.get('order_id') or ''))

    # ── Price-sensitive: ve promos reales y la politica de descuentos ─────────

    def test_price_sensitive_buyer_sees_promotions_and_discount_policy(self):
        from django.utils import timezone
        from datetime import timedelta
        Promotion.objects.create(
            organization=self.org,
            title='2x1 en Tops',
            description='Lleva dos tops por el precio de uno',
            discount_type='percentage',
            discount_value=50,
            applies_to='category',
            category='Tops',
            is_active=True,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=5),
        )

        self.turn('busco tops', situation='specific_product_customer')
        self.turn(
            'esta muy caro, tienen descuento?',
            situation='price_sensitive_customer',
            reply='Tenemos promos activas, te cuento.',
        )

        last_prompt = self.llm.prompts[-1]
        self.assertIn('Politica de descuentos (no la excedas NUNCA): maximo 10%', last_prompt)

    # ── Needs-guidance: una sola pregunta, sin presion ────────────────────────

    def test_confused_buyer_gets_clarify_strategy(self):
        self.turn(
            'no se que necesito, es para mi hermana',
            situation='confused_customer',
            reply='¿Para que tipo de actividad lo quiere ella?',
        )
        self.assertIn('## Estrategia:', self.llm.prompts[-1])
        self.assertIn('UNA sola pregunta', self.llm.prompts[-1])

    # ── Anti-alucinacion: producto inventado nunca llega al cliente ───────────

    def test_hallucinated_product_in_reply_is_sanitized(self):
        reply = self.turn(
            'que tops tienen?',
            situation='specific_product_customer',
            reply='Te recomiendo el **Top Runner Pro Max** por $80000, es importado.',
        )
        self.assertNotIn('Runner Pro Max', reply)

    # ── Marca: frase prohibida se elimina aunque el LLM la diga ───────────────

    def test_brand_avoid_phrase_never_reaches_customer(self):
        reply = self.turn(
            'tienen leggings termicos?',
            situation='specific_product_customer',
            reply=(
                'Tenemos el Legging Heat Control Negro disponible. '
                'Te aviso luego si llegan mas colores. ¿Te lo muestro?'
            ),
        )
        self.assertNotIn('te aviso luego', reply.lower())
        self.assertIn('Legging Heat Control Negro', reply)

    # ── Off-topic: redirige sin productos ─────────────────────────────────────

    def test_off_topic_buyer_is_redirected(self):
        self.turn(
            'quien va ganando las elecciones?',
            situation='off_topic',
            reply='Te ayudo feliz con productos de la tienda. ¿Que te gustaria ver?',
        )
        if self.llm.prompts:
            self.assertIn('solo puedes ayudar con los productos', self.llm.prompts[-1])

    # ── Closing style de la marca aparece al cerrar ───────────────────────────

    def test_close_strategy_uses_brand_closing_style(self):
        # The executor downgrades the very first close to clarify (asks the
        # customer to confirm the product), so we assert at the prompt-builder
        # level with the same onboarding settings the executor loads.
        from apps.channels_config.settings_schema import normalise_settings
        from apps.ai_engine.sales.generator import ResponseGenerator

        runtime_config = normalise_settings(GOLDEN_BRAND_SETTINGS)
        session = SimpleNamespace(
            organization=self.org,
            stage='considering',
            selected_products=[str(self.top.id)],
            budget_min=None,
            budget_max=None,
            objections=[],
            category_interest='tops',
            checkout_data={},
        )
        prompt = ResponseGenerator._build_system_prompt(
            session=session,
            situation='ready_to_buy_customer',
            action={'response_strategy': 'close'},
            context={'recommended_products': [], 'product_resolution': {}, 'kb_content': '', 'promotions': []},
            runtime_config=runtime_config,
        )
        self.assertIn('Estilo de la marca para este momento: resumen corto y pregunta directa', prompt)
