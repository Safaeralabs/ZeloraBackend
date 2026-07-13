"""
Response Generator - LLM that generates sales conversation replies.
Uses the configured sales model (default gpt-4o-mini).
"""
import logging

import openai
from django.conf import settings

from .llm_router import LLMRouter
from .brand import BrandVoice

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """
    Generates natural, sales-focused responses.
    Called after DecisionEngine decides what to do.
    """

    @staticmethod
    def generate(
        user_message: str,
        conversation_history: list,
        session,
        situation: str,
        action: dict,
        context: dict,
    ) -> str:
        """
        Generate bot response.

        Args:
            user_message: Current user message
            conversation_history: Recent Message objects
            session: SalesSession
            situation: Detected customer situation
            action: DecisionEngine action (strategy, etc.)
            context: Loaded context (products, KB, promos)

        Returns:
            Reply string
        """
        if not settings.OPENAI_API_KEY or not settings.ENABLE_REAL_AI:
            return ResponseGenerator._fallback_reply(situation, action)

        try:
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            task = ResponseGenerator._resolve_generation_task(
                user_message=user_message,
                session=session,
                action=action,
            )
            model = LLMRouter.model_for_task(task)
            runtime_config = ResponseGenerator._load_runtime_config(session.organization)

            system_prompt = ResponseGenerator._build_system_prompt(
                session=session,
                situation=situation,
                action=action,
                context=context,
                runtime_config=runtime_config,
            )
            messages = ResponseGenerator._build_messages(conversation_history, user_message)

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
                temperature=0.7,
                max_tokens=ResponseGenerator._max_tokens_for_response_length(runtime_config),
            )

            reply = response.choices[0].message.content.strip()
            logger.info('Generated reply (%s chars, model=%s)', len(reply), model)
            return reply
        except Exception as exc:
            logger.error('Response generation failed: %s', exc)
            return ResponseGenerator._fallback_reply(situation, action)

    @staticmethod
    def _resolve_generation_task(*, user_message: str, session, action: dict) -> str:
        if ResponseGenerator._is_ambiguous_checkout_message(
            user_message=user_message,
            session_stage=str(getattr(session, 'stage', '') or ''),
            strategy=str((action or {}).get('response_strategy') or ''),
        ):
            return 'ambiguous_language'
        return str((action or {}).get('response_strategy') or 'main_response')

    @staticmethod
    def _is_ambiguous_checkout_message(*, user_message: str, session_stage: str, strategy: str) -> bool:
        text = str(user_message or '').strip().lower()
        if not text:
            return False
        in_checkout = session_stage == 'checkout' or strategy == 'close'
        if not in_checkout:
            return False
        short_ack = {'si', 'sí', 'sii', 'listo', 'dale', 'ok', 'oki', 'nequi', 'efectivo'}
        if text in short_ack:
            return True
        if len(text.split()) <= 3 and any(token in text for token in ('transferen', 'confirmo', 'pago', 'cuenta')):
            return True
        return False

    @staticmethod
    def _load_runtime_config(organization) -> dict:
        return BrandVoice.load_runtime_config(organization)

    @staticmethod
    def _max_tokens_for_response_length(runtime_config: dict) -> int:
        response_length = ((runtime_config.get('sales_agent') or {}).get('max_response_length') or 'standard')
        return {
            'brief': 220,
            'standard': 350,
            'detailed': 500,
        }.get(response_length, 350)

    @staticmethod
    def _language_rules(org_name: str, assistant_name: str, response_language: str) -> tuple[str, str, str]:
        if response_language == 'en':
            return (
                f'You are {assistant_name} for {org_name}. Respond naturally and concisely in English.',
                'Channel: app (maximum 2-3 sentences, direct and useful).',
                'Respond ALWAYS in English.',
            )
        if response_language == 'auto':
            return (
                f'Eres {assistant_name} de {org_name}. Responde de forma natural y concisa.',
                'Canal: app (maximo 2-3 oraciones, directo al punto).',
                'Responde en el mismo idioma del cliente. Si no es claro, usa espanol.',
            )
        return (
            f'Eres {assistant_name} de {org_name}. Respondes en espanol, de forma natural y concisa.',
            'Canal: app (maximo 2-3 oraciones, directo al punto).',
            'Responde SIEMPRE en espanol.',
        )

    @staticmethod
    def _build_system_prompt(
        session,
        situation: str,
        action: dict,
        context: dict,
        runtime_config: dict | None = None,
    ) -> str:
        """
        Build comprehensive system prompt.

        Includes identity, rules, state, KB, products, and strategy.
        """
        org = session.organization
        runtime_config = runtime_config or {}
        sales_agent = runtime_config.get('sales_agent') or {}
        has_products = bool(context.get('recommended_products'))
        unavailable_products = context.get('unavailable_products') or []
        resolution = context.get('product_resolution') or {}
        needs_confirmation = bool(resolution.get('needs_confirmation'))
        assistant_name = (sales_agent.get('name') or '').strip() or 'el agente de ventas'
        identity_line, channel_line, language_line = ResponseGenerator._language_rules(
            org.name,
            assistant_name,
            sales_agent.get('response_language') or 'auto',
        )

        lines = [
            identity_line,
            channel_line,
            language_line,
            '',
            '## REGLAS ABSOLUTAS - nunca las rompas',
            '- SOLO puedes hablar de productos que aparecen en la seccion "## Productos disponibles" o "## Productos agotados" de este prompt.',
            '- Si esa seccion esta vacia o no tiene lo que el cliente pide: dile claramente que no tienes ese producto.',
            '- NUNCA inventes productos, marcas, modelos, precios, materiales ni caracteristicas.',
            '- NUNCA digas "estare atento" ni "lo buscare" - si no esta en el catalogo, no lo tienes.',
            '- Si el cliente pregunta algo fuera de ventas (historia, noticias, politica, etc.): una sola oracion amable redirigiendolo.',
            '- Maximo 2 productos mencionados por turno.',
            '- No hables de competidores salvo para reforzar los diferenciadores de la marca sin inventar datos.',
            *BrandVoice.commerce_rule_lines(runtime_config),
            '',
        ]

        lines += BrandVoice.conversational_style_lines(runtime_config)
        lines += BrandVoice.identity_lines(runtime_config)
        lines += BrandVoice.voice_example_lines(runtime_config)
        lines += BrandVoice.seller_directives(runtime_config)

        if not has_products:
            lines += [
                '## IMPORTANTE: Sin productos disponibles',
                'No hay productos en el catalogo que coincidan con lo que el cliente pide.',
                'Dile honestamente que no tienes ese producto especifico.',
                'Puedes preguntar si le interesa ver otras opciones similares que si tenemos.',
                '',
            ]
        elif needs_confirmation:
            lines += [
                '## IMPORTANTE: Hay varias coincidencias posibles',
                'NO confirmes que ya encontraste el producto exacto.',
                'Pide al cliente que elija una de las opciones mostradas abajo.',
                'Menciona que puede tocar una tarjeta para confirmar cual producto busca.',
                '',
            ]

        if unavailable_products:
            lines.append('## Productos agotados (coinciden con lo que pide, pero sin stock)')
            for product in unavailable_products[:2]:
                lines.append(f"- **{product['title']}**: agotado ahora mismo")
            lines += [
                'Estos productos SI existen en el catalogo, no le digas al cliente que no los tienes.',
                'Dile con tu propio tono (el definido arriba) que estan agotados en este momento.',
                'Nunca los ofrezcas como si pudiera comprarlos ya ni des fecha de reposicion que no conoces.',
                'Ofrece avisarle cuando vuelva a haber stock, o sugierele algo similar de "## Productos disponibles" si aplica.',
                '',
            ]

        lines += [
            '## Contexto actual',
            f'Etapa: {session.stage}',
            f'Situacion: {situation}',
            f'Estrategia: {action.get("response_strategy", "default")}',
            '',
        ]

        if resolution:
            lines += [
                '## Resolucion de busqueda',
                f"Tipo de match: {resolution.get('match_type', '')}",
                f"Busqueda interpretada: {resolution.get('interpreted_query', '')}",
                f"Requiere confirmacion: {'si' if needs_confirmation else 'no'}",
                '',
            ]

        shipping_profile = context.get('shipping_profile') or {}
        payment_profile = context.get('payment_profile') or {}
        current_checkout = dict(getattr(session, 'checkout_data', {}) or {})
        incoming_checkout = context.get('checkout_data') or {}
        if incoming_checkout:
            current_checkout.update(incoming_checkout)
        shipping_form = current_checkout.get('shipping_form') or {}
        compact_form = current_checkout.get('compact_checkout_form') or {}

        if isinstance(shipping_profile, dict) and (shipping_profile.get('avg_days') or shipping_profile.get('ships_same_day')):
            ships_same_day = bool(shipping_profile.get('ships_same_day'))
            avg_days = str(shipping_profile.get('avg_days') or '').strip()
            lines += ['## Tiempos de envio']
            lines.append(
                'Este negocio SI despacha pedidos el mismo dia (si se piden antes del corte habitual).'
                if ships_same_day else
                'Este negocio NO garantiza despacho el mismo dia — no prometas eso.'
            )
            if avg_days:
                lines.append(
                    f'El tiempo estimado de ENTREGA (cuando llega a la direccion del cliente, distinto de cuando se despacha) es de {avg_days}.'
                )
            lines.append(
                'Si preguntan "llega hoy?" o "envian hoy?", responde estas dos cosas por separado — no las mezcles.'
            )
            lines.append('')

        if (session.stage == 'checkout' or action.get('checkout_step')) and isinstance(shipping_profile, dict):
            required_fields = ['full_name', 'phone', 'address_line1']
            if shipping_profile.get('require_city', True):
                required_fields.append('city')
            if shipping_profile.get('require_postal_code'):
                required_fields.append('postal_code')
            if shipping_profile.get('require_reference', True):
                required_fields.append('reference')
            missing_fields = [field for field in required_fields if not str((shipping_form or {}).get(field, '')).strip()]
            lines += [
                '## Checkout de envio',
                f"Pais: {shipping_profile.get('country_code') or 'CO'}",
                f"Campos requeridos: {', '.join(required_fields)}",
                f"Campos faltantes: {', '.join(missing_fields) if missing_fields else 'ninguno'}",
                'Si faltan datos, pide SOLO los campos faltantes de forma breve.',
                'Si ya estan completos, confirma resumen de envio y sigue al siguiente paso.',
                '',
            ]

        payment_methods = [
            item for item in (payment_profile.get('methods') or [])
            if isinstance(item, dict) and str(item.get('id') or '').strip()
        ]
        if payment_methods:
            lines.append('## Metodos de pago habilitados')
            for method in payment_methods[:3]:
                method_label = str(method.get('label') or method.get('id') or '').strip()
                method_description = str(method.get('description') or '').strip()
                method_instructions = str(method.get('instructions') or '').strip()
                lines.append(f'- {method_label}: {method_description or "Disponible"}')
                if method_instructions:
                    lines.append(f'  Instrucciones: {method_instructions[:180]}')
            selected_method = str((compact_form or {}).get('payment_method') or '').strip()
            if (session.stage == 'checkout' or action.get('checkout_step')) and not selected_method:
                lines.append('En checkout, solicita primero el metodo de pago antes de cerrar el pedido.')
            lines.append(
                'Si el metodo confirmado es transferencia bancaria, despues del pago pide una captura '
                'de pantalla del comprobante y explica que validaran el pago.'
            )
            lines.append('')

        cart_event = context.get('cart_event') or {}
        if isinstance(cart_event, dict) and cart_event.get('type') == 'item_removed':
            removed_title = str(cart_event.get('removed_product_title') or '').strip() or 'ese producto'
            retention_allowed = bool(cart_event.get('retention_allowed'))
            lines += [
                '## Evento de carrito',
                f'El cliente quito del carrito: {removed_title}.',
                (
                    'Responde con retencion breve: 1 beneficio concreto + 1 pregunta de cierre para recuperar ese producto.'
                    if retention_allowed
                    else 'No insistas con retencion. Confirma el cambio y ofrece alternativa breve.'
                ),
                'Nunca uses tono de presion.',
                '',
            ]

        state_lines: list[str] = []
        if session.selected_products:
            state_lines.append(f'Productos seleccionados: {len(session.selected_products)}')
        if session.budget_min or session.budget_max:
            state_lines.append(f'Presupuesto: ${session.budget_min or "?"}-${session.budget_max or "?"}')
        if session.objections:
            state_lines.append(f'Objeciones: {", ".join(session.objections[:2])}')
        if session.category_interest:
            state_lines.append(f'Categoria de interes: {session.category_interest}')
        if state_lines:
            lines += state_lines + ['']

        if context.get('kb_content'):
            # KBService caps each article at ~400 chars and fetches up to 3;
            # the budget here must fit them or articles get cut mid-sentence.
            lines.append('## Informacion relevante')
            lines.append(context['kb_content'][:1500])
            lines.append('')

        if context.get('sales_examples'):
            lines.append('## Asi respondio la marca en casos reales similares')
            lines.append(
                'Imita el tono y la tactica de estos ejemplos. '
                'NO copies precios, productos ni datos: usa solo el catalogo actual.'
            )
            lines.append(context['sales_examples'][:900])
            lines.append('')

        if context.get('customer_order_history'):
            lines.append(context['customer_order_history'])
            lines.append(
                'Usa este historial SOLO si el cliente pregunta por un pedido anterior o hace referencia a el. '
                'No lo menciones espontaneamente. No puedes modificar pedidos ya confirmados desde aqui.'
            )
            lines.append('')

        if context.get('contact_memory_summary'):
            lines.append(context['contact_memory_summary'])
            lines.append(
                'Usa esto para dar continuidad (ej. no repreguntes su presupuesto si ya lo conoces), '
                'pero no lo recites textualmente al cliente.'
            )
            lines.append('')

        if context.get('order_lookup'):
            lines.append(context['order_lookup'])
            lines.append('')

        if has_products:
            lines.append('## Productos disponibles (SOLO estos puedes mencionar)')
            for product in context['recommended_products'][:3]:
                price_str = f"${product['price_min']}" if product.get('price_min') else 'Consultar precio'
                desc = product.get('description', '')[:80]
                lines.append(f"- **{product['title']}**: {price_str}")
                if desc:
                    lines.append(f"  {desc}")
                if product.get('promotion'):
                    lines.append(f"  Promocion: {product['promotion']['title']}")
            lines.append('')

        if context.get('promotions'):
            lines.append('## Promociones activas')
            for promo in context['promotions'][:2]:
                lines.append(f"- {promo['title']}: {promo['description'][:60]}")
            lines.append('')

        strategy = action.get('response_strategy', 'discover')
        guidance = BrandVoice.strategy_guidance(strategy, runtime_config)
        if guidance:
            lines.append(f'## Estrategia: {guidance}')

        return '\n'.join(lines)

    @staticmethod
    def _build_messages(conversation_history: list, user_message: str) -> list:
        """
        Build conversation turns for LLM.
        """
        messages = []
        for msg in conversation_history[-8:]:
            if msg.role == 'user':
                messages.append({"role": "user", "content": msg.content})
            elif msg.role == 'bot':
                messages.append({"role": "assistant", "content": msg.content})

        messages.append({"role": "user", "content": user_message})
        return messages

    @staticmethod
    def _fallback_reply(situation: str, action: dict) -> str:
        """
        Safe fallback reply when LLM is unavailable.
        """
        if situation == 'off_topic':
            return 'Te ayudo feliz con productos de la tienda. ¿Qué te gustaría ver?'
        if situation == 'prompt_injection':
            return 'Cuéntame qué estás buscando y te ayudo con eso.'
        if situation == 'out_of_catalog':
            return 'Ese producto justo no lo tengo, pero si quieres te muestro opciones parecidas.'
        if action.get('response_strategy') == 'close':
            return 'Si quieres, lo cerramos ya. ¿Confirmas tu pedido para pasar al pago?'
        return 'Perfecto, te leo. ¿Qué necesitas y lo resolvemos?'
