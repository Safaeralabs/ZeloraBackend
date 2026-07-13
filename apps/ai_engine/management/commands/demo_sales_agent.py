"""
Live demo of the Sales Agent: brand voice + selling behaviour + proactive follow-up.

Runs a REAL multi-turn conversation through the full pipeline (situation detection,
decision engine, catalog, brand-aware prompt, validator, contracts) against the
configured LLM, then ages a quiet session and fires the FollowUpEngine so you can
see the proactive nudge.

Usage:
    python manage.py demo_sales_agent
    python manage.py demo_sales_agent --keep   # don't delete the demo org afterwards
"""
from __future__ import annotations

import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


DEMO_SLUG = 'demo-pulse'

ONBOARDING_SETTINGS = {
    'settings_version': 2,
    'org_profile': {
        'what_you_sell': 'ropa deportiva femenina de alto rendimiento',
        'who_you_sell_to': 'mujeres que entrenan en serio (gym, running, crossfit)',
        'payment_methods': ['nequi', 'efectivo'],
        'brand': {
            'tone_of_voice': 'cercano, energico y directo, como una coach que te entiende',
            'formality_level': 'informal, tutea siempre',
            'brand_personality': 'energica, honesta y sin humo',
            'value_proposition': 'tallaje real, telas que aguantan y asesoria honesta',
            'key_differentiators': ['tallaje real probado', 'tela de compresion nacional', 'cambios sin lio'],
            'recommended_phrases': ['de una', 'te cuento', 'va a aguantar lo que le metas'],
            'avoid_phrases': ['te aviso luego', 'no estoy segura'],
            'preferred_closing_style': 'cierre suave: resumo y pregunto directo, sin presionar',
            'urgency_style': 'urgencia baja y honesta, solo si de verdad queda poco stock',
            'customer_style_notes': 'tutea, habla como gente de gym, nada corporativo',
        },
    },
    'sales_agent': {
        'enabled': True,
        'name': 'Lia',
        'persona': 'asesora deportiva consultiva y agil, vende como una vendedora real de mostrador',
        'mission_statement': 'entender que entrena la clienta y llevarla a la prenda correcta y al cierre',
        'response_language': 'es',
        'max_response_length': 'standard',
        'followup_mode': 'suave',
        'max_followups': 2,
        'playbook': {
            'opening_style': 'saludo corto y pregunta por que tipo de entrenamiento hace',
            'recommendation_style': 'maximo dos opciones, cada una con un beneficio concreto',
            'objection_style': 'valida la objecion y responde con un beneficio real, sin pelear',
            'closing_style': 'resumen corto del pedido y una pregunta directa de cierre',
            'upsell_style': 'sugiere un complemento de menor precio que combine',
        },
        'buyer_model': {
            'common_objections': ['esta caro', 'no se si me quedara la talla', 'no confio en comprar online'],
        },
        'commerce_rules': {
            'discount_policy': 'maximo 10% y solo si hay una promo activa, nunca inventes descuentos',
            'return_policy_summary': 'cambios dentro de 15 dias con etiqueta puesta',
            'forbidden_promises': ['entrega el mismo dia', 'garantia de por vida'],
        },
    },
    'payment_settings': {
        'nequi_enabled': True,
        'nequi_number': '300 123 4567',
        'nequi_holder': 'Pulse Activewear SAS',
        'nequi_note': 'Envia el comprobante por este chat y validamos.',
        'cash_enabled': True,
    },
}

PRODUCTS = [
    {
        'title': 'Top Motion Support Arena',
        'category': 'Tops',
        'price': 119900,
        'stock': 6,
        'description': 'Top de alto soporte para entrenamiento de impacto, tela de compresion que sujeta sin apretar.',
    },
    {
        'title': 'Legging Heat Control Negro',
        'category': 'Leggings',
        'price': 149900,
        'stock': 4,
        'description': 'Legging de compresion tiro alto, tela termica que no transparenta en sentadillas.',
    },
    {
        'title': 'Top Light Flow Rosa',
        'category': 'Tops',
        'price': 89900,
        'stock': 8,
        'description': 'Top de soporte ligero para yoga y entrenamiento de bajo impacto.',
    },
]

# Scripted buyer turns. The agent's replies are generated live by the real LLM.
CONVERSATION = [
    'hola! que venden?',
    'busco un top que aguante bien para crossfit, salto mucha cuerda y hago box jumps',
    'uy y no tienen algo mas economico? 120 me parece un poco alto la verdad',
    'mmm vale, me convences. me llevo el Top Motion Support Arena',
]


class Command(BaseCommand):
    help = 'Run a live Sales Agent conversation + follow-up demo against the real LLM.'

    def add_arguments(self, parser):
        parser.add_argument('--keep', action='store_true', help='Keep the demo org after running.')

    def handle(self, *args, **options):
        from django.conf import settings as dj_settings

        from apps.accounts.models import Organization
        from apps.channels_config.models import ChannelConfig
        from apps.conversations.models import Conversation, Message
        from apps.ecommerce.models import Order, Product, ProductVariant
        from apps.ai_engine.models import SalesSession
        from apps.ai_router.executors.sales_agent import SalesAgentExecutor
        from apps.ai_engine.sales.followup import FollowUpEngine

        real_ai = bool(dj_settings.OPENAI_API_KEY) and dj_settings.ENABLE_REAL_AI
        self._hr()
        if real_ai:
            self.stdout.write(self.style.SUCCESS('LLM REAL activo — el agente genera respuestas en vivo.'))
        else:
            self.stdout.write(self.style.WARNING('Sin LLM (OPENAI_API_KEY/ENABLE_REAL_AI) — respuestas de fallback.'))

        # ── Clean slate ───────────────────────────────────────────────────────
        Organization.objects.filter(slug=DEMO_SLUG).delete()
        org = Organization.objects.create(
            name='Pulse Activewear', slug=DEMO_SLUG, plan='pilot', country='Colombia',
            industry='Ropa deportiva',
        )
        ChannelConfig.objects.create(
            organization=org, channel='onboarding', is_active=True, settings=ONBOARDING_SETTINGS,
        )
        products = {}
        for spec in PRODUCTS:
            product = Product.objects.create(
                organization=org, title=spec['title'], category=spec['category'],
                description=spec['description'], status='active', is_active=True, is_bestseller=True,
            )
            ProductVariant.objects.create(
                product=product, sku=f"{spec['title'][:6].replace(' ', '')}-U",
                name='Unica', price=spec['price'], stock=spec['stock'],
            )
            products[spec['title']] = product

        self.stdout.write(f'\nMarca: {org.name}  |  Agente: Lia  |  Catalogo: {len(products)} productos')
        self.stdout.write('Voz: cercana, energica, tutea; tallaje real; sin prometer entrega el mismo dia.')

        # ── Scenario 1: live selling conversation ─────────────────────────────
        self._section('ESCENARIO 1 — Conversacion de venta en vivo')
        conv = Conversation.objects.create(organization=org, canal='web', estado='nuevo')
        executor = SalesAgentExecutor()

        for user_text in CONVERSATION:
            reply = self._run_turn(executor, conv, org, user_text)
            self._print_turn(user_text, reply)
            if real_ai:
                time.sleep(0.4)

        session = SalesSession.objects.get(conversation=conv)
        self.stdout.write(self.style.HTTP_INFO(
            f'\n   [estado interno] etapa={session.stage} | situacion={session.situation} '
            f'| seleccionados={len(session.selected_products)}'
        ))

        # ── Scenario 2: close with structured checkout → real Order ───────────
        self._section('ESCENARIO 2 — Cierre con datos de envio (crea pedido real)')
        checkout_payload = {
            'structured_payload': {
                'interactive': {
                    'action': 'submit_compact_checkout',
                    'data': {
                        'full_name': 'Ana Perez',
                        'phone': '+573001112233',
                        'payment_method': 'nequi',
                        'address_line1': 'Calle 10 #23-45, Apto 302',
                        'city': 'Bogota',
                        'reference': 'Porteria principal',
                    },
                },
            },
        }
        reply = self._run_turn(executor, conv, org, 'Confirmo mi pedido.', payload=checkout_payload)
        self._print_turn('Confirmo mi pedido. [+ datos de envio y pago: Nequi]', reply)

        order = Order.objects.filter(organization=org).order_by('-created_at').first()
        if order:
            self.stdout.write(self.style.SUCCESS(
                f'\n   PEDIDO CREADO: #{getattr(order, "order_number", "") or str(order.id)[:8]} '
                f'| estado={order.status} | total=${int(order.total or 0):,} COP'
            ))
        else:
            self.stdout.write(self.style.WARNING('\n   (no se creo pedido en este turno)'))

        # ── Scenario 3: proactive follow-up on a quiet warm lead ──────────────
        self._section('ESCENARIO 3 — Follow-up proactivo (lead tibio en silencio)')
        warm_conv = Conversation.objects.create(organization=org, canal='web', estado='en_proceso')
        Message.objects.create(conversation=warm_conv, role='user', content='me interesa el legging negro')
        Message.objects.create(conversation=warm_conv, role='bot',
                               content='Te cuento, el Legging Heat Control Negro es tiro alto y no transparenta. ¿Te muestro tallas?')
        warm_session = SalesSession.objects.create(
            conversation=warm_conv, organization=org, stage='considering',
            selected_products=[str(products['Legging Heat Control Negro'].id)],
        )
        # Age the activity 6 hours so the lead looks "quiet but warm".
        quiet_at = timezone.now() - timedelta(hours=6)
        Conversation.objects.filter(id=warm_conv.id).update(last_message_at=quiet_at)
        SalesSession.objects.filter(id=warm_session.id).update(updated_at=quiet_at)
        warm_session.refresh_from_db()
        warm_conv.refresh_from_db()

        self.stdout.write('   Cliente preguntó por el legging hace 6h y se quedó en silencio (sin pedido).')
        self.stdout.write('   Disparando barrido de follow-up...\n')

        result = FollowUpEngine.sweep()
        nudge = warm_conv.messages.filter(role='bot').order_by('-timestamp').first()
        if result.get('sent'):
            self.stdout.write(self.style.SUCCESS('   >> El agente reactivó la conversación solo:'))
            self.stdout.write(self.style.HTTP_INFO(f'      Lia: {nudge.content}'))
        else:
            self.stdout.write(self.style.WARNING(f'   (no se envió follow-up: {result})'))

        # ── Wrap up ───────────────────────────────────────────────────────────
        self._section('RESUMEN')
        self.stdout.write(f'  Pedidos creados:        {Order.objects.filter(organization=org).count()}')
        self.stdout.write(f'  Follow-ups enviados:    {result.get("sent", 0)}')
        self.stdout.write('  Voz de marca aplicada:  identidad + reglas comerciales en cada turno')

        if options['keep']:
            self.stdout.write(self.style.SUCCESS(f'\nOrg demo conservada (slug={DEMO_SLUG}).'))
        else:
            Organization.objects.filter(slug=DEMO_SLUG).delete()
            self.stdout.write('\nOrg demo eliminada (usa --keep para conservarla).')
        self._hr()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _run_turn(self, executor, conv, org, text, payload=None):
        from apps.conversations.models import Message
        message = Message.objects.create(
            conversation=conv, role='user', content=text, metadata=payload or {},
        )
        try:
            reply = executor.execute(conversation=conv, message=message, decision=None, organization=org)
        except Exception as exc:  # noqa: BLE001 — demo must keep going
            reply = f'[error: {exc}]'
        if reply:
            Message.objects.create(conversation=conv, role='bot', content=reply)
        return reply or '(sin respuesta)'

    def _print_turn(self, user_text, reply):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(f'   Cliente: {user_text}'))
        self.stdout.write(self.style.HTTP_INFO(f'   Lia:     {reply}'))

    def _section(self, title):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_LABEL('=' * 70))
        self.stdout.write(self.style.MIGRATE_LABEL(f'  {title}'))
        self.stdout.write(self.style.MIGRATE_LABEL('=' * 70))

    def _hr(self):
        self.stdout.write(self.style.MIGRATE_LABEL('=' * 70))
