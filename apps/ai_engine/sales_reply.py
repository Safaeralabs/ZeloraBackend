"""
Sales reply generation: LLM, heuristic, and brand voice post-processing.

All inter-app imports (openai, usage_tracker, etc.) are deferred inside function bodies.
"""
from __future__ import annotations

from typing import Any

import structlog

from .sales_models import (
    STAGE_CHECKOUT_BLOCKED,
    STAGE_CONSIDERING,
    STAGE_DISCOVERING,
    STAGE_FOLLOW_UP_NEEDED,
    BrandProfile,
    BuyerProfile,
    BusinessContext,
    SalesContext,
    SalesPlaybook,
)

logger = structlog.get_logger(__name__)

def _llm_reply(
    *,
    message_text: str,
    stage: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    stock_info: dict[str, Any] | None,
    promotions: list[dict[str, Any]],
    sales_ctx: SalesContext,
    router_decision,
    settings,
    conversation,
) -> str | None:
    try:
        import openai

        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        model = getattr(settings, 'OPENAI_SALES_MODEL', getattr(settings, 'OPENAI_MODEL', 'gpt-4o'))
        if router_decision and router_decision.model_name:
            model = router_decision.model_name

        import time as _time
        is_first = _conversation_user_message_count(conversation) <= 1
        chat_history = _build_chat_history_messages(conversation)
        t0 = _time.monotonic()
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': _build_system_prompt(sales_ctx, is_first_message=is_first)},
                {'role': 'system', 'content': _build_context_block(
                    stage=stage,
                    buyer=buyer,
                    products=products,
                    stock_info=stock_info,
                    promotions=promotions,
                    sales_ctx=sales_ctx,
                    conversation=conversation,
                )},
                *chat_history,
                {'role': 'user', 'content': message_text},
            ],
            max_tokens=180,
            temperature=0.6,
        )
        latency_ms = int((_time.monotonic() - t0) * 1000)
        try:
            from apps.ai_engine.usage_tracker import track
            usage = completion.usage
            track(
                organization_id=str(sales_ctx.business.org_id),
                feature='sales_agent',
                model=model,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
            )
        except Exception:
            pass
        return completion.choices[0].message.content or None
    except Exception as exc:
        logger.warning('sales_agent_llm_error', error=str(exc))
        return None


def _heuristic_reply(
    *,
    message_text: str,
    stage: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    stock_info: dict[str, Any] | None,
    promotions: list[dict[str, Any]],
    sales_ctx: SalesContext,
) -> str:
    text = message_text.lower()
    biz_ctx = sales_ctx.business
    brand_ctx = sales_ctx.brand
    playbook = sales_ctx.playbook
    rules = sales_ctx.commerce_rules
    product_lines = _build_product_lines(products, sales_ctx.business.org_slug)

    # Purchase-intent stages take priority over generic objection handling.
    # A price question in INTENT_TO_BUY is a purchase signal, not a price objection.
    # A payment failure in CHECKOUT_BLOCKED is more specific than any inferred objection.
    if stage == STAGE_INTENT_TO_BUY:
        reply = _reply_intent_to_buy(text, buyer, products, product_lines, stock_info, biz_ctx)
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)
    if stage == STAGE_CHECKOUT_BLOCKED:
        reply = f'Entiendo que hubo un inconveniente al pagar. Puedes intentar con {", ".join(biz_ctx.payment_methods[:2])}. Si me dices que paso, te ayudo a destrabar la compra.'
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)

    if buyer.objection == 'price':
        reply = (
            f'Tenemos una promocion activa que puede ayudarte: {promotions[0]}. Si quieres, te digo si encaja con lo que buscas.'
            if promotions else
            'Entiendo que el precio importa. Si me dices para que lo necesitas, te recomiendo la opcion con mejor balance entre valor y precio.'
        )
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)

    if buyer.objection == 'shipping':
        reply = f'El envio cubre {biz_ctx.shipping_coverage} con tiempo estimado de {biz_ctx.shipping_avg_days}. Si te encaja ese tiempo, te ayudo a elegir la mejor opcion disponible.'
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)

    if buyer.objection == 'availability':
        reply = (
            'Ese producto esta agotado ahora mismo. Puedo proponerte una alternativa disponible para que no pierdas tiempo.'
            if stock_info and not stock_info.get('any_in_stock')
            else 'Puedo ayudarte a validar el stock exacto, pero necesito saber que producto o variante te interesa.'
        )
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)

    if buyer.objection == 'trust':
        reply = 'Trabajamos con informacion verificada.'
        if rules.return_policy_summary:
            reply += f' {rules.return_policy_summary}.'
        elif biz_ctx.has_returns_policy:
            reply += f' Tienes {biz_ctx.returns_window_days} dias para devolucion si aplica.'
        reply += ' Si quieres, te recomiendo la opcion mas segura para tu caso.'
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)

    if stage == STAGE_CONSIDERING:
        reply = _reply_considering(buyer, products, product_lines)
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)
    if stage == STAGE_FOLLOW_UP_NEEDED:
        reply = _reply_follow_up_needed(buyer, products, promotions)
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)
    if stage == STAGE_DISCOVERING:
        reply = _reply_discovering(buyer, products, product_lines)
        return _apply_brand_voice(reply, brand_ctx, playbook, stage)
    return _apply_brand_voice('Cuantame que necesitas y te ayudo a decidir la mejor opcion para comprar.', brand_ctx, playbook, stage)


def _reply_intent_to_buy(
    text: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    product_lines: str,
    stock_info: dict[str, Any] | None,
    biz_ctx: BusinessContext,
) -> str:
    if any(token in text for token in ('precio', 'cuanto', 'vale', 'cuesta')):
        if products and products[0].get('min_price'):
            product = products[0]
            stock_msg = ' Hay disponibilidad ahora.' if product.get('any_in_stock') else ' Estoy revisando disponibilidad.'
            suffix = ' Si te cuadra, lo dejamos listo hoy?' if buyer.urgency == 'immediate' else ' Si quieres, te cuento si esta te conviene o si hay otra mejor.'
            return f'{product["title"]} esta desde ${product["min_price"]:,.0f}.{stock_msg}{suffix}'
        return 'Te ayudo con el precio. Dime que producto o uso tienes en mente y te recomiendo algo puntual.'
    if any(token in text for token in ('envio', 'llega', 'entrega', 'demora', 'delivery')):
        close = ' Si te sirve ese tiempo, lo dejamos pedido hoy?' if buyer.urgency == 'immediate' else ' Si quieres, revisamos que opcion te conviene mas segun entrega.'
        return f'Hacemos envios a {biz_ctx.shipping_coverage}, con tiempo estimado de {biz_ctx.shipping_avg_days}.{close}'
    if any(token in text for token in ('pago', 'pagar', 'tarjeta', 'transferencia', 'efectivo')):
        return f'Aceptamos {", ".join(biz_ctx.payment_methods)}. Si ya tienes una opcion elegida, te guio con el siguiente paso.'
    if any(token in text for token in ('stock', 'disponible', 'hay', 'tienen')):
        if stock_info:
            return 'Si, tenemos disponibilidad. Si quieres, avanzamos con la opcion que mejor te encaje.' if stock_info.get('any_in_stock') else 'Ese producto esta agotado actualmente. Puedo proponerte otra opcion disponible si te sirve.'
        if products:
            return f'{products[0]["title"]} esta disponible. Para recomendarte bien, dime cuantas unidades necesitas.'
        return 'Te ayudo a validar disponibilidad, pero necesito saber de cual producto se trata.'
    if product_lines:
        return f'Estas son las opciones disponibles:{product_lines} {"Si una te encaja, avanzamos hoy?" if buyer.urgency == "immediate" else "Cual se acerca mas a lo que buscas?"}'
    return 'Perfecto. Si me dices para que lo quieres o que presupuesto tienes, te propongo algo concreto.'


def _reply_considering(buyer: BuyerProfile, products: list[dict[str, Any]], product_lines: str) -> str:
    if len(products) >= 2:
        first = products[0]
        second = products[1]
        first_price = f'${first["min_price"]:,.0f}' if first.get('min_price') else 'precio a consultar'
        second_price = f'${second["min_price"]:,.0f}' if second.get('min_price') else 'precio a consultar'
        recommendation = first['title'] if buyer.priority == 'price' else second['title']
        return (
            f'{first["title"]}: {first_price}. {second["title"]}: {second_price}. '
            f'Si priorizas {"precio" if buyer.priority == "price" else "calidad"}, yo me iria por {recommendation}. Si quieres, te digo rapido por que.'
        )
    if product_lines:
        return f'Aqui tienes las opciones:{product_lines} Que te pesa mas para decidir: precio, calidad o entrega?'
    return 'Cuentame que estas comparando y te ayudo a elegir sin darte vueltas.'


def _reply_follow_up_needed(
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
) -> str:
    if products:
        primary = products[0]
        price_label = f' por ${primary["min_price"]:,.0f}' if primary.get('min_price') else ''
        promo_line = ''
        if promotions:
            promo_line = f' Ademas, ahora mismo tenemos {promotions[0]}.'
        if buyer.priority == 'price':
            return (
                f'Tranquilo, te dejo ubicada la opcion que mejor balance tiene en precio: {primary["title"]}{price_label}.{promo_line} '
            'Dime solo una cosa: prefieres irte por algo mas economico o por algo que te dure mas?'
        )
        if buyer.urgency in ('immediate', 'this_week'):
            return (
                f'Todo bien. Para no hacerte perder tiempo, la opcion que veo mas alineada es {primary["title"]}{price_label}.{promo_line} '
                'Si quieres, te confirmo en un mensaje corto si esta te conviene o si es mejor irse por otra.'
            )
        return (
            f'Claro. Por ahora la opcion que mejor encaja es {primary["title"]}{price_label}.{promo_line} '
            'Si te sirve, resolvemos lo principal: buscas algo mas economico o algo mas durable?'
        )
    return (
        'Sin problema. Dime que te frena mas para decidir: precio, entrega o no tener claro cual te conviene. '
        'Con eso te respondo puntual y sin darte vueltas.'
    )


def _reply_discovering(buyer: BuyerProfile, products: list[dict[str, Any]], product_lines: str) -> str:
    if buyer.style == 'direct' and products:
        return f'Encontre estas opciones:{product_lines} Si quieres, te digo cual te conviene mas segun lo que buscas.'
    if products:
        return f'Tenemos estas opciones disponibles:{product_lines} Es para ti, para regalo o para algo puntual?'
    return 'Hola, que andas buscando? Si me dices para que lo quieres, te recomiendo algo concreto.'


def _avoid_consecutive_repeat(
    *,
    reply: str,
    conversation,
    message_text: str,
    stage: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
) -> str:
    normalized_reply = ' '.join((reply or '').split()).strip().lower()
    if not normalized_reply or conversation is None:
        return reply

    try:
        recent_messages = list(conversation.messages.order_by('-timestamp')[:4])
    except Exception:
        return reply

    last_bot = next((item for item in recent_messages if getattr(item, 'role', '') == 'bot' and getattr(item, 'content', '')), None)
    last_user = next((item for item in recent_messages if getattr(item, 'role', '') == 'user' and getattr(item, 'content', '')), None)
    last_bot_text = ' '.join((getattr(last_bot, 'content', '') or '').split()).strip().lower()
    current_user_text = ' '.join((message_text or '').split()).strip().lower()
    last_user_text = ' '.join((getattr(last_user, 'content', '') or '').split()).strip().lower()

    if normalized_reply != last_bot_text:
        return reply

    if current_user_text in {'es para mi', 'para mi', 'es mío', 'es mio'} and products:
        first = products[0]
        return (
            f'Perfecto. Entonces te ubico rapido: de lo que te mostre, {first["title"]} pinta bien para uso personal. '
            'Te va mejor que te guie por set, talla o color?'
        )

    if current_user_text and current_user_text == last_user_text:
        if products:
            first = products[0]
            return (
                f'Te sigo por aqui sin repetir todo: si quieres, arrancamos por {first["title"]}. '
                'Dime que quieres definir primero y te respondo puntual.'
            )
        return 'Te sigo por aqui. Dime que quieres definir primero y te respondo puntual.'

    if stage == STAGE_DISCOVERING and products:
        first = products[0]
        return f'Perfecto. Si quieres, arrancamos por {first["title"]}. Dime si te importa mas talla, color o precio.'

    return reply


def _product_link(product: dict[str, Any], org_slug: str) -> str:
    product_id = product.get('id')
    title = product.get('title', '')
    if not product_id or not org_slug or not title:
        return title
    return f'[{title}](/shop/{org_slug}/{product_id})'


def _build_product_lines(products: list[dict[str, Any]], org_slug: str = '') -> str:
    if not products:
        return ''
    lines = []
    for product in products[:3]:
        line = f'\n- {_product_link(product, org_slug)}'
        if product.get('min_price'):
            line += f' - ${product["min_price"]:,.0f}'
        line += ' disponible' if product.get('any_in_stock') else ' sin stock'
        lines.append(line)
    return ''.join(lines)


def _append_product_links(reply: str, products: list[dict[str, Any]], org_slug: str) -> str:
    if not reply or not products or not org_slug:
        return reply
    if '/shop/' in reply:
        return reply
    updated_reply = reply
    replacements = 0

    for product in products[:2]:
        title = (product.get('title') or '').strip()
        link = _product_link(product, org_slug)
        if not title or not link:
            continue
        pattern = re.compile(rf'(\*\*|__)?\s*{re.escape(title)}\s*(\*\*|__)?', re.IGNORECASE)
        updated_reply, count = pattern.subn(link, updated_reply, count=1)
        replacements += count

    if replacements > 0:
        updated_reply = re.sub(r'(\*\*|__)\s*(\[[^\]]+\]\(/shop/[^)]+\))\s*(\*\*|__)', r'\2', updated_reply)
        return updated_reply

    # No product was mentioned in the reply — don't force-append an unrelated link.
    return reply


def _payment_option_link(method: str, org_slug: str) -> str:
    normalized_method = (method or '').strip()
    if not normalized_method or not org_slug:
        return normalized_method
    prompt = f'Quiero pagar por {normalized_method}. Guiame con el siguiente paso.'
    return f'[{normalized_method}](/{org_slug}/?prefill={quote(prompt)})'


def _append_payment_links(reply: str, payment_methods: list[str], org_slug: str) -> str:
    if not reply or not payment_methods or not org_slug:
        return reply

    updated_reply = reply
    replacements = 0
    normalized_methods = [method for method in payment_methods[:3] if isinstance(method, str) and method.strip()]

    for method in normalized_methods:
        link = _payment_option_link(method, org_slug)
        pattern = re.compile(re.escape(method), re.IGNORECASE)
        updated_reply, count = pattern.subn(link, updated_reply, count=1)
        replacements += count

    if replacements > 0:
        return updated_reply

    if any(token in reply.lower() for token in ('pago', 'pagar', 'metodo', 'metodo de pago', 'método', 'método de pago')):
        chips = ' o '.join(_payment_option_link(method, org_slug) for method in normalized_methods[:2])
        return f'{reply} Puedes elegir {chips}.'

    return reply


def _build_system_prompt(sales_ctx: SalesContext, *, is_first_message: bool = False) -> str:
    business = sales_ctx.business
    brand = sales_ctx.brand
    playbook = sales_ctx.playbook
    rules = sales_ctx.commerce_rules
    buyer_model = sales_ctx.buyer_model or {}
    prefs = sales_ctx.agent_preferences or {}
    prefs = sales_ctx.agent_preferences or {}
    forbidden = ', '.join((rules.forbidden_promises or business.forbidden_actions)[:4]) or 'ninguna definida'
    recommended_phrases = ', '.join(brand.recommended_phrases[:4]) or 'ninguna definida'
    avoid_phrases = ', '.join(brand.avoid_phrases[:4]) or 'ninguna definida'
    ideal_buyers = ', '.join((buyer_model.get('ideal_buyers') or [])[:4]) or 'no definidos'
    common_objections = ', '.join((buyer_model.get('common_objections') or [])[:5]) or 'no definidas'
    purchase_signals = ', '.join((buyer_model.get('purchase_signals') or [])[:5]) or 'no definidas'
    low_intent_signals = ', '.join((buyer_model.get('low_intent_signals') or [])[:5]) or 'no definidas'
    # Response length instruction
    _length_instruction = {
        'brief': 'Responde SIEMPRE en 1 frase, maximo 2. Sin listas, sin parrafos.',
        'standard': 'Por defecto responde en 1 o 2 frases cortas. Usa 3 solo si es estrictamente necesario.',
        'detailed': 'Puedes dar respuestas mas completas cuando el cliente necesite informacion detallada, pero sigue siendo conciso.',
    }.get(business.max_response_length, 'Por defecto responde en 1 o 2 frases cortas.')

    # Language instruction
    _lang_instruction = {
        'es': 'Responde SIEMPRE en español, independientemente del idioma del cliente.',
        'en': 'Always respond in English, regardless of the customer language.',
        'auto': 'Responde en el idioma del cliente.',
    }.get(business.response_language, 'Responde en el idioma del cliente.')

    # Persona line
    _persona_line = (
        f'Tu persona: {business.agent_persona}.\n' if business.agent_persona
        else f'Eres un asesor comercial experto de {brand.brand_name or business.org_name}.\n'
    )

    # Competitor handling
    _competitor_line = (
        f'Cuando el cliente mencione competidores: {playbook.competitor_response}.\n'
        if playbook.competitor_response
        else (
            f'Nunca des informacion sobre otra empresa, otra marca, otro negocio o '
            f'otra organizacion distinta de {brand.brand_name or business.org_name}. '
            'Si te preguntan por otra empresa, dilo claramente y redirige.\n'
        )
    )

    # Greeting — only inject when this is genuinely the first user message
    _greeting_line = (
        f'Este es el primer mensaje del cliente. Saluda con: "{business.greeting_message}"\n'
        if (is_first_message and business.greeting_message) else
        'NO saludes de nuevo. Ya existe historial de conversacion. Ve directo al punto.\n'
        if not is_first_message else ''
    )

    return (
        f'{_persona_line}'
        f'Trabajas para la marca {brand.brand_name or business.org_name or "la empresa"}.\n'
        'PRINCIPIO FUNDAMENTAL: Tu trabajo es resolver TODO dentro del chat. El cliente nunca deberia tener que salir de esta conversacion para obtener informacion. Si la respuesta existe en tu knowledge base o en el contexto disponible, dasela aqui y ahora. Redirigir a la web, a un numero de telefono o a una oficina como primera respuesta esta prohibido.\n'
        'La unica excepcion es cuando el tramite requiere presencia fisica obligatoria (ej. firma notarial, entrega de documentos originales) — y aun asi, primero da toda la informacion posible aqui.\n'
        'Tu objetivo principal no es solo responder: es ayudar al cliente a tomar una decision de compra.\n'
        'Debes comportarte como un vendedor experto: entiende la necesidad, pregunta cuando falte informacion, recomienda productos adecuados, resuelve dudas y objeciones y guia la conversacion hacia la compra.\n'
        'Nunca respondas de forma pasiva, fria o generica.\n'
        'Cada respuesta debe empujar la conversacion hacia una decision concreta.\n'
        'Si el cliente se enfria o dice que luego vuelve, haz seguimiento comercial suave: resume la mejor opcion y cierra con una sola pregunta util.\n'
        'Nunca seas abusivo ni spam. No presiones con urgencia falsa.\n'
        'Solo puedes usar informacion real del negocio. Nunca inventes precios, stock, politicas, tiempos de envio ni promociones.\n'
        'Si hay conflicto entre una politica publicada en Knowledge Base y un campo estructurado legacy, siempre debes priorizar Knowledge Base.\n'
        'Knowledge Base es la verdad operativa para pagos, envios, descuentos, devoluciones, inventario, restricciones y promesas permitidas. Los campos estructurados legacy solo son fallback.\n'
        f'{_length_instruction}\n'
        f'{_lang_instruction}\n'
        'No metas varias ideas densas en un mismo mensaje. Da una recomendacion concreta y una sola pregunta util.\n'
        'Debes absorber y respetar la identidad de marca, el playbook comercial, el buyer model, las reglas comerciales, el catalogo y la knowledge base en cada respuesta.\n'
        f'{_competitor_line}'
        'Si hay conflicto entre sonar natural y seguir la marca, prioriza sonar natural sin salirte del tono y reglas de la marca.\n'
        'Usa frases recomendadas solo si encajan de forma natural. Evita por completo las frases a evitar y cualquier claim prohibido.\n'
        f'{_greeting_line}'
        f'Nombre de marca: {brand.brand_name or business.org_name or "no definido"}.\n'
        f'Nombre del agente: {sales_ctx.agent_name or "Sales Agent"}.\n'
        f'Que vende la marca: {business.what_you_sell or "no definido"}.\n'
        f'Tipo de clientes: {business.who_you_sell_to or "no definido"}.\n'
        f'Mision de marca: {business.mission or "no definida"}.\n'
        f'Industria: {business.industry or "no definida"}. Pais: {business.country or "no definido"}. Web: {business.website or "no definida"}.\n'
        f'Tono de marca: {brand.tone_of_voice}. Formalidad: {brand.formality_level}. Personalidad: {brand.brand_personality or "no definida"}.\n'
        f'{"Estilo de escritura de los clientes (aprende a sonar como ellos): " + brand.customer_style_notes + chr(10) if brand.customer_style_notes else ""}'
        f'Propuesta de valor: {brand.value_proposition or "no definida"}.\n'
        f'Diferenciales clave: {", ".join(brand.key_differentiators[:4]) or "no definidos"}.\n'
        f'Estilo de cierre: {brand.preferred_closing_style}. Intensidad comercial permitida: {brand.urgency_style}.\n'
        f'Frases recomendadas: {recommended_phrases}.\n'
        f'Frases a evitar: {avoid_phrases}.\n'
        f'Metodos de pago aceptados: {", ".join(business.payment_methods) or "no definidos"}.\n'
        f'Politica de envios: {business.shipping_policy or business.shipping_coverage}.\n'
        f'Playbook apertura: {playbook.opening_style or "no definido"}.\n'
        f'Playbook recomendacion: {playbook.recommendation_style or "no definido"}.\n'
        f'Playbook objeciones: {playbook.objection_style or "no definido"}.\n'
        f'Playbook cierre: {playbook.closing_style or "no definido"}.\n'
        f'Playbook follow-up: {playbook.follow_up_style or "no definido"}.\n'
        f'Playbook upsell: {playbook.upsell_style or "no definido"}.\n'
        'P2.2 STORYTELLING: Cuando recomiendes productos, SIEMPRE incluye una narrativa breve: (1) para qué ocasión/momento sirve, (2) por qué le quedaría bien a este cliente. Máx 1 frase de narrativa por producto. Esto hace que la recomendación sea convincente y personal.\n'
        f'Autonomia del agente: {prefs.get("autonomy_level", "semi_autonomo")} | followup={prefs.get("followup_mode", "suave")} | escalado={prefs.get("handoff_mode", "balanceado")}.\n'
        f'Compradores ideales: {ideal_buyers}.\n'
        f'Objeciones comunes: {common_objections}.\n'
        f'Senales de compra: {purchase_signals}.\n'
        f'Senales de bajo interes: {low_intent_signals}.\n'
        f'Regla de descuentos: {rules.discount_policy or "no definida"}.\n'
        f'Regla de negociacion: {rules.negotiation_policy or "no definida"}.\n'
        f'Regla de inventario: {rules.inventory_promise_rule or "no definida"}.\n'
        f'Regla de entrega: {rules.delivery_promise_rule or "no definida"}.\n'
        f'Resumen de devoluciones: {rules.return_policy_summary or "no definida"}.\n'
        f'Acciones prohibidas: {forbidden}.'
    )


def _build_context_block(
    *,
    stage: str,
    buyer: BuyerProfile,
    products: list[dict[str, Any]],
    stock_info: dict[str, Any] | None,
    promotions: list[dict[str, Any]],
    sales_ctx: SalesContext,
    conversation,
) -> str:
    business = sales_ctx.business
    brand = sales_ctx.brand
    playbook = sales_ctx.playbook
    rules = sales_ctx.commerce_rules
    buyer_model = sales_ctx.buyer_model or {}
    prefs = sales_ctx.agent_preferences or {}
    history = _build_conversation_history(conversation)
    knowledge = _lookup_relevant_knowledge(conversation, business, products, sales_ctx, stage=stage)
    conversation_state = _map_stage_to_conversation_state(stage)
    qualification = ((getattr(conversation, 'metadata', None) or {}).get('qualification') or {})
    qualification_summary = (
        f"tipo={qualification.get('affiliate_status', 'sin_validar')}, "
        f"categoria={qualification.get('affiliate_category', 'sin_validar')}, "
        f"empresa_al_dia={qualification.get('company_status', 'sin_validar')}"
    )
    active_flow = ((getattr(conversation, 'metadata', None) or {}).get('active_flow') or {})
    flow_summary = (
        f"nombre={active_flow.get('name', 'sin_flujo')}, "
        f"paso={active_flow.get('step', 'sin_paso')}, "
        f"estado={active_flow.get('status', 'sin_estado')}, "
        f"datos={active_flow.get('data', {})}"
    )
    catalog_snapshot = _build_catalog_snapshot_block(sales_ctx.catalog_snapshot)
    full_knowledge_snapshot = _build_knowledge_snapshot_block(sales_ctx.knowledge_snapshot)
    structured_rules = _build_structured_rules_block(sales_ctx)
    product_lines = ['Sin productos encontrados para esta consulta.']
    if products:
        product_lines = []
        for product in products[:4]:
            is_svc = product.get('offer_type') == 'service'
            avail_label = 'disponible' if product.get('any_in_stock') else ('sin_stock' if not is_svc else 'no_disponible')
            price_label = f'${product["min_price"]:,.0f}' if product.get('min_price') else ('cotizar' if product.get('price_type') == 'quote_required' else 'precio a consultar')
            meta = product.get('offer_type', 'physical')
            if is_svc and product.get('requires_booking'):
                meta += '|requiere_reserva'
            # P2.2: Build narrative hints from enriched product attributes
            narrative_hints = []
            if product.get('occasion'):
                narrative_hints.append(f"ocasion: {', '.join(product['occasion'])}")
            if product.get('style'):
                narrative_hints.append(f"estilo: {product['style']}")
            if product.get('formality'):
                narrative_hints.append(f"formalidad: {product['formality']}")
            if product.get('target_audience'):
                narrative_hints.append(f"para: {product['target_audience']}")
            narrative_block = f" | {' | '.join(narrative_hints)}" if narrative_hints else ""
            product_lines.append(f'- {product["title"]} | {price_label} | {avail_label} | {meta}{narrative_block}')
    promotion_lines = '\n'.join(f'- {promo}' for promo in promotions[:2]) if promotions else 'Sin promociones activas.'
    stock_line = f'Stock validado: {stock_info.get("total_available")}' if stock_info else 'Stock no consultado.'
    return (
        '\n--- CONTEXTO ---\n'
        f'conversation_state: {conversation_state}\n'
        f'marca: {brand.brand_name or business.org_name or "no definida"}\n'
        f'nombre_del_agente: {sales_ctx.agent_name or "Sales Agent"}\n'
        f'que_vende_la_marca: {business.what_you_sell or "no definido"}\n'
        f'tipo_de_clientes: {business.who_you_sell_to or "no definido"}\n'
        f'mision: {business.mission or "no definida"}\n'
        f'identidad_visual: primary={brand.primary_color or "n/d"}, accent={brand.accent_color or "n/d"}, style={brand.visual_style or "n/d"}, logo={brand.logo_url or "n/d"}\n'
        f'Pagos: {", ".join(business.payment_methods)}\n'
        f'Envios: {business.shipping_coverage} ({business.shipping_avg_days})\n'
        f'Politicas: {", ".join(business.commercial_policies[:3]) or "estandar"}\n'
        f'Calificacion operativa: {qualification_summary}\n'
        f'Flujo estructurado: {flow_summary}\n'
        f'Politica descuentos: {rules.discount_policy or "no definida"}\n'
        f'Politica negociacion: {rules.negotiation_policy or "no definida"}\n'
        f'Regla inventario: {rules.inventory_promise_rule or "no definida"}\n'
        f'Regla entrega: {rules.delivery_promise_rule or "no definida"}\n'
        f'Regla devoluciones: {rules.return_policy_summary or "no definida"}\n'
        f'Comprador: prioridad={buyer.priority}, urgencia={buyer.urgency}, estilo={buyer.style}, objecion={buyer.objection or "ninguna"}, etapa={stage}\n'
        f'Regla de seguimiento: modo={prefs.get("followup_mode", "suave")} | max_followups={prefs.get("max_followups", 1)} | autonomia={prefs.get("autonomy_level", "semi_autonomo")} | recommendation_depth={prefs.get("recommendation_depth", 2)} | escalado={prefs.get("handoff_mode", "balanceado")}.\n'
        f'Marca: tono={brand.tone_of_voice}, formalidad={brand.formality_level}, personalidad={brand.brand_personality or "n/d"}, propuesta={brand.value_proposition or "n/d"}\n'
        f'Diferenciales marca: {", ".join(brand.key_differentiators[:4]) or "ninguno"}\n'
        f'Frases recomendadas: {", ".join(brand.recommended_phrases[:4]) or "ninguna"}\n'
        f'Frases a evitar: {", ".join(brand.avoid_phrases[:4]) or "ninguna"}\n'
        f'Playbook activo: apertura={playbook.opening_style or "n/d"} | recomendacion={playbook.recommendation_style or "n/d"} | objeciones={playbook.objection_style or "n/d"} | cierre={playbook.closing_style or "n/d"} | follow_up={playbook.follow_up_style or "n/d"} | upsell={playbook.upsell_style or "n/d"}\n'
        f'Buyer model: ideales={", ".join((buyer_model.get("ideal_buyers") or [])[:4]) or "n/d"} | objeciones={", ".join((buyer_model.get("common_objections") or [])[:4]) or "n/d"} | compra={", ".join((buyer_model.get("purchase_signals") or [])[:4]) or "n/d"} | bajo_interes={", ".join((buyer_model.get("low_intent_signals") or [])[:4]) or "n/d"}\n'
        f'Politicas operativas priorizadas (KB primero, fallback legacy):\n{structured_rules}\n'
        f'Catalogo activo:\n{catalog_snapshot}\n'
        f'Knowledge base completa resumida:\n{full_knowledge_snapshot}\n'
        f'Historial reciente:\n{history}\n'
        f'Knowledge relevante:\n{knowledge}\n'
        + '\n'.join(product_lines) + '\n'
        + promotion_lines + '\n'
        + stock_line + '\n--- FIN CONTEXTO ---\n'
    )


def _map_stage_to_conversation_state(stage: str) -> str:
    if stage == STAGE_INTENT_TO_BUY:
        return 'listo_para_comprar'
    if stage in (STAGE_CONSIDERING, STAGE_CHECKOUT_BLOCKED):
        return 'interesado'
    return 'explorando'


def _build_catalog_snapshot_block(catalog_snapshot: list[dict[str, Any]]) -> str:
    if not catalog_snapshot:
        return 'Sin catalogo activo disponible.'

    lines: list[str] = []
    for item in catalog_snapshot:
        price_parts: list[str] = []
        if item.get('min_price'):
            if item.get('max_price') and item['max_price'] != item['min_price']:
                price_parts.append(f'${item["min_price"]:,.0f}–${item["max_price"]:,.0f}')
            else:
                price_parts.append(f'${item["min_price"]:,.0f}')
        elif item.get('price_type') == 'quote_required':
            price_parts.append('cotizar')
        else:
            price_parts.append('precio a consultar')
        price = price_parts[0]
        stock = 'disponible' if item.get('any_in_stock') else 'sin stock'
        category = item.get('category') or 'sin categoria'
        offer_type = item.get('offer_type', 'physical')
        meta_parts: list[str] = [offer_type]
        if offer_type == 'service':
            if item.get('requires_booking'):
                meta_parts.append('requiere_reserva')
            svc_mode = item.get('service_mode', 'not_applicable')
            if svc_mode not in ('not_applicable', ''):
                meta_parts.append(svc_mode)
        elif offer_type == 'physical':
            if item.get('requires_shipping'):
                meta_parts.append('con_envio')
        meta = '|'.join(meta_parts)
        lines.append(f'- {item["title"]} | {category} | {price} | {stock} | {meta}')
    return '\n'.join(lines)


def _build_knowledge_snapshot_block(knowledge_snapshot: list[dict[str, Any]]) -> str:
    if not knowledge_snapshot:
        return 'Sin knowledge base publicada.'

    lines: list[str] = []
    for item in knowledge_snapshot:
        item_type = item.get('type', 'item')
        category = item.get('category') or 'general'
        content = item.get('content', '')
        lines.append(f'- [{item_type}] {item.get("title", "sin titulo")} | {category} | {content}')
    return '\n'.join(lines)


def _build_structured_rules_block(sales_ctx: SalesContext) -> str:
    rules = sales_ctx.commerce_rules
    business = sales_ctx.business

    lines: list[str] = []
    if business.payment_methods:
        lines.append(f'- metodos_de_pago: {", ".join(business.payment_methods[:5])}')
    if rules.discount_policy:
        lines.append(f'- descuentos: {rules.discount_policy}')
    if rules.negotiation_policy:
        lines.append(f'- negociacion: {rules.negotiation_policy}')
    if rules.inventory_promise_rule:
        lines.append(f'- inventario: {rules.inventory_promise_rule}')
    if rules.delivery_promise_rule:
        lines.append(f'- entrega: {rules.delivery_promise_rule}')
    if business.shipping_policy:
        lines.append(f'- envios: {business.shipping_policy}')
    elif business.shipping_coverage or business.shipping_avg_days:
        lines.append(f'- envios: cobertura={business.shipping_coverage}; tiempo={business.shipping_avg_days}')
    if rules.return_policy_summary:
        lines.append(f'- devoluciones: {rules.return_policy_summary}')
    if rules.forbidden_claims:
        lines.append(f'- claims_prohibidos: {", ".join(rules.forbidden_claims[:5])}')
    if rules.forbidden_promises:
        lines.append(f'- promesas_prohibidas: {", ".join(rules.forbidden_promises[:5])}')
    return '\n'.join(lines) if lines else 'Sin politicas operativas publicadas ni fallback legacy.'


def _build_conversation_history(conversation) -> str:
    try:
        if conversation is None:
            return 'Sin historial.'
        history = conversation.messages.order_by('-timestamp')[:6]
        items = []
        for item in reversed(list(history)):
            role = 'cliente' if item.role == 'user' else 'marca'
            content = ' '.join((item.content or '').split())
            if not content:
                continue
            items.append(f'- {role}: {content[:220]}')
        return '\n'.join(items) if items else 'Sin historial.'
    except Exception:
        return 'Sin historial.'


def _build_chat_history_messages(conversation) -> list[dict]:
    """
    Returns conversation history as real OpenAI message turns so the model
    has genuine context of prior exchanges. Excludes the current (most recent)
    user message — it is added separately as the final 'user' turn.
    """
    if not conversation:
        return []
    try:
        # Skip the latest message (the incoming one) — fetch the 6 before it
        all_msgs = list(conversation.messages.order_by('-timestamp')[:7])
        prior = list(reversed(all_msgs[1:]))  # oldest first, skip index 0 = latest
        result = []
        for msg in prior:
            role = 'user' if msg.role == 'user' else 'assistant'
            content = ' '.join((msg.content or '').split()).strip()
            if content:
                result.append({'role': role, 'content': content[:500]})
        return result
    except Exception:
        return []


def _conversation_user_message_count(conversation) -> int:
    """Returns how many user messages this conversation has (including the current one)."""
    try:
        return conversation.messages.filter(role='user').count() if conversation else 0
    except Exception:
        return 0


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_query(text: str) -> list[float] | None:
    """Get OpenAI embedding for query text."""
    try:
        import os
        from openai import OpenAI

        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            return None
        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(model='text-embedding-3-small', input=text[:512])
        return response.data[0].embedding
    except Exception:
        return None


# Maps conversation stage → KB purposes to prioritize (fetched first, injected top of context)
_STAGE_PURPOSE_MAP: dict[str, list[str]] = {
    STAGE_DISCOVERING:       ['faq', 'business'],
    STAGE_CONSIDERING:       ['business', 'faq'],
    STAGE_INTENT_TO_BUY:     ['sales_scripts', 'policy'],
    STAGE_FOLLOW_UP_NEEDED:  ['sales_scripts'],
    STAGE_LOST:              ['sales_scripts'],
    STAGE_CLOSED_LOST:       ['sales_scripts'],
    STAGE_CLOSED_WON:        ['sales_scripts'],
    STAGE_CHECKOUT_BLOCKED:  ['sales_scripts', 'policy'],
    STAGE_HUMAN_HANDOFF:     ['policy'],
}
# Always added unless already satisfied by stage-specific results
_BASELINE_PURPOSES = ['faq', 'business']


def _lookup_relevant_knowledge(
    conversation,
    business: BusinessContext,
    products: list[dict[str, Any]],
    sales_ctx: SalesContext | None = None,
    stage: str = STAGE_DISCOVERING,
) -> str:
    try:
        from apps.knowledge_base.models import KBArticle, KBDocument

        org = getattr(conversation, 'organization', None)
        if org is None:
            return 'Sin conocimiento adicional.'

        base_qs = KBArticle.objects.filter(organization=org, is_active=True, status='published')

        # --- Stage-aware purpose retrieval ---
        priority_purposes = _STAGE_PURPOSE_MAP.get(stage, _BASELINE_PURPOSES)
        # Always ensure faq is present as baseline
        all_purposes = list(dict.fromkeys(priority_purposes + _BASELINE_PURPOSES))

        purpose_articles: list[Any] = []
        seen_ids: set = set()

        # Fetch up to 2 articles per purpose, in priority order
        for purpose in all_purposes:
            if len(purpose_articles) >= 4:
                break
            qs = base_qs.filter(purpose=purpose).only('id', 'title', 'content', 'purpose', 'embedding_vector').order_by('-updated_at')[:4]
            for art in qs:
                if art.id not in seen_ids:
                    purpose_articles.append(art)
                    seen_ids.add(art.id)
                    if len(purpose_articles) >= 4:
                        break

        # --- Semantic re-ranking via cosine similarity ---
        # Build query text from last customer message + products
        query_parts: list[str] = []
        try:
            last_user_msg = conversation.messages.filter(role='user').order_by('-timestamp').first()
            if last_user_msg and last_user_msg.content:
                query_parts.append(last_user_msg.content[:120])
        except Exception:
            pass
        for product in products[:2]:
            t = product.get('title', '')
            if t:
                query_parts.append(t[:60])
        if business.what_you_sell:
            query_parts.append(business.what_you_sell[:60])
        query_text = ' '.join(query_parts).strip() or 'productos y servicios'

        # Broaden pool with general articles if purpose-filtered set is small
        if len(purpose_articles) < 3:
            extra = list(
                base_qs.exclude(id__in=seen_ids)
                .only('id', 'title', 'content', 'purpose', 'embedding_vector')
                .order_by('-updated_at')[:20]
            )
            purpose_articles.extend(extra)

        query_vec = _embed_query(query_text)
        articles_with_emb = [a for a in purpose_articles if a.embedding_vector]

        if query_vec and articles_with_emb:
            scored = [
                (a, _cosine_similarity(query_vec, a.embedding_vector))
                for a in articles_with_emb
            ]
            scored.sort(key=lambda t: t[1], reverse=True)
            top_articles = [a for a, score in scored[:4] if score > 0.20]
            # Add purpose-priority articles that didn't make cosine cut (low text but on-purpose)
            for art in purpose_articles[:2]:
                if art not in top_articles:
                    top_articles.insert(0, art)
            top_articles = top_articles[:4]
        else:
            # Fallback: keyword icontains on general pool
            terms = [w for w in query_text.lower().split() if len(w) > 3][:6]
            if terms:
                from django.db.models import Q
                kb_filter = Q()
                for term in terms:
                    kb_filter |= Q(title__icontains=term) | Q(content__icontains=term)
                top_articles = list(base_qs.filter(kb_filter).order_by('-updated_at')[:4])
            else:
                top_articles = purpose_articles[:3]

        snippets: list[str] = []
        for article in top_articles:
            purpose_label = f'[{article.purpose}] ' if getattr(article, 'purpose', '') else ''
            snippets.append(f'- {purpose_label}{article.title}: {" ".join(article.content.split())[:220]}')

        # --- Documents (keyword match) ---
        document_queryset = KBDocument.objects.filter(organization=org, is_active=True, processing_status='ready')
        terms = [w for w in query_text.lower().split() if len(w) > 3][:6]
        if terms:
            from django.db.models import Q
            doc_filter = Q()
            for term in terms:
                doc_filter |= Q(filename__icontains=term) | Q(extracted_text__icontains=term)
            documents = document_queryset.filter(doc_filter).order_by('-updated_at')[:2]
        else:
            documents = document_queryset.order_by('-updated_at')[:2]

        for document in documents:
            excerpt = ' '.join((document.extracted_text or '').split())[:220]
            if excerpt:
                snippets.append(f'- [doc] {document.filename}: {excerpt}')

        if snippets:
            return '\n'.join(snippets)

        if sales_ctx and sales_ctx.knowledge_snapshot:
            return _build_knowledge_snapshot_block(sales_ctx.knowledge_snapshot[:4])
        return 'Sin conocimiento adicional.'
    except Exception:
        if sales_ctx and sales_ctx.knowledge_snapshot:
            return _build_knowledge_snapshot_block(sales_ctx.knowledge_snapshot[:4])
        return 'Sin conocimiento adicional.'


def _apply_brand_voice(text: str, brand_ctx: BrandProfile, playbook: SalesPlaybook, stage: str) -> str:
    cleaned = ' '.join((text or '').split())
    for phrase in brand_ctx.avoid_phrases:
        if isinstance(phrase, str) and phrase.strip():
            cleaned = cleaned.replace(phrase.strip(), '')
    prefix = ''
    if stage == STAGE_DISCOVERING and playbook.opening_style:
        prefix = playbook.opening_style.strip()
    elif stage == STAGE_CONSIDERING and playbook.recommendation_style:
        prefix = playbook.recommendation_style.strip()
    elif stage == STAGE_FOLLOW_UP_NEEDED and playbook.follow_up_style:
        prefix = playbook.follow_up_style.strip()
    elif stage in (STAGE_INTENT_TO_BUY, STAGE_CHECKOUT_BLOCKED) and playbook.closing_style:
        prefix = playbook.closing_style.strip()
    elif brand_ctx.recommended_phrases:
        prefix = brand_ctx.recommended_phrases[0].strip()
    if prefix and len(prefix.split()) <= 6 and prefix.lower() not in cleaned.lower():
        cleaned = f'{prefix} {cleaned}'.strip()
    if brand_ctx.formality_level == 'formal':
        cleaned = cleaned.replace('Lo tomamos?', 'Desea avanzar con la compra?')
        cleaned = cleaned.replace('Lo pedimos?', 'Desea que avancemos con el pedido?')
    elif brand_ctx.formality_level == 'casual':
        cleaned = cleaned.replace('Desea avanzar con la compra?', 'Te animas a pedirlo?')
    if brand_ctx.urgency_style == 'soft':
        cleaned = cleaned.replace('hoy mismo', 'pronto')
    elif brand_ctx.urgency_style == 'strong' and stage == STAGE_INTENT_TO_BUY and '?' in cleaned and 'hoy' not in cleaned.lower():
        cleaned = cleaned[:-1] + ' hoy?'
    return _humanize_sales_reply(cleaned.strip(), stage, brand_ctx.formality_level)


def _humanize_sales_reply(text: str, stage: str, formality_level: str) -> str:
    cleaned = ' '.join((text or '').split()).strip()
    replacements = {
        'Con gusto te ayudo con el precio.': 'Te ayudo con el precio.',
    }
    for k, v in replacements.items():
        if isinstance(k, str) and isinstance(v, str):
            cleaned = cleaned.replace(k, v)
    return cleaned


# P2.1: 2-step reply generation with Human Rewrite (formerly missing _generate_reply)

_CHANNEL_RULES = {
    'whatsapp': (
        'Máximo 2 frases. Sin formato markdown. Máximo 1 emoji. 1 sola pregunta. '
        'Tono casual y cercano. Evita viñetas o listas.'
    ),
    'instagram': (
        'Casual, energético, visualmente atractivo. Puede usar 1-2 emojis. '
        'Sin tablas ni formatos complejos.'
    ),
    'web': (
        'Puede ser más estructurado. Usa saltos de línea si hay múltiples productos. '
        'Está OK usar pequeñas listas.'
    ),
    'email': (
        'Más formal. Incluye saludo al inicio y despedida al final. '
        'Puede ser más largo. Párrafos limpios.'
    ),
    'telegram': (
        'Similar a WhatsApp pero puedes usar formato markdown básico (negritas, cursivas). '
        'Máximo 2-3 frases.'
    ),
}


def _human_rewrite_reply(
    draft: str, brand: BrandProfile, channel: str, stage: str, settings
) -> str | None:
    """
    P2.1 Step 2: Rewrite reply to sound human and natural (tono conversacional).
    Uses gpt-4o-mini for speed + quality, applies channel-specific rules.

    Args:
        draft: Raw reply from Sales Brain (_llm_reply)
        brand: BrandProfile with tone, formality, avoid_phrases, customer_style_notes
        channel: 'whatsapp', 'instagram', 'web', 'email', 'telegram'
        stage: conversation stage (for context)
        settings: Django settings object

    Returns:
        Rewritten reply or None if LLM fails
    """
    try:
        import openai

        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

        channel_rules = _CHANNEL_RULES.get(channel, _CHANNEL_RULES['web'])

        system_prompt = f"""Reescribe este mensaje de ventas para que suene como un vendedor humano genuino.

TONO: {brand.tone_of_voice}
FORMALIDAD: {brand.formality_level}
REGLAS DEL CANAL ({channel}): {channel_rules}

FRASES A EVITAR: {', '.join(brand.avoid_phrases[:5]) if brand.avoid_phrases else 'ninguna'}

NOTAS DE ESTILO DEL CLIENTE: {brand.customer_style_notes if brand.customer_style_notes else 'sin observaciones'}

Reescribe el mensaje de manera que se sienta natural, amigable, y alineado con el estilo del vendedor.
No agregues información nueva. Solo mejora el tono y la fluidez."""

        completion = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': draft},
            ],
            max_tokens=150,
            temperature=0.7,
        )

        rewritten = completion.choices[0].message.content or None
        return rewritten

    except Exception as exc:
        logger.warning('human_rewrite_error', error=str(exc))
        return None


def _generate_reply(
    *,
    message_text: str,
    stage: str,
    buyer: BuyerProfile,
    products: list[dict],
    stock_info: dict | None,
    promotions: list[dict],
    sales_ctx: SalesContext,
    router_decision,
    conversation,
    channel: str = 'web',
) -> str:
    """
    P2.1: Orquestador de 2-step generation.
    Step 1 (Sales Brain): _llm_reply genera respuesta estructurada
    Step 2 (Human Rewrite): _human_rewrite_reply la reescribe con tono humano

    Args:
        All the usual parameters from the original _generate_reply
        channel: 'whatsapp', 'instagram', 'web', 'email', 'telegram' (default: 'web')

    Returns:
        Final reply text, ready to send
    """
    try:
        from django.conf import settings as django_settings

        # Guard: out-of-scope brand query check
        out_of_scope_reply = _guard_out_of_scope_brand_query(message_text, sales_ctx)
        if out_of_scope_reply:
            return out_of_scope_reply

        # P2.1 Step 1: Sales Brain (existing _llm_reply)
        if django_settings.ENABLE_REAL_AI and django_settings.OPENAI_API_KEY:
            brain_reply = _llm_reply(
                message_text=message_text,
                stage=stage,
                buyer=buyer,
                products=products,
                stock_info=stock_info,
                promotions=promotions,
                sales_ctx=sales_ctx,
                router_decision=router_decision,
                settings=django_settings,
                conversation=conversation,
            )

            if brain_reply:
                # P2.1 Step 2: Human Rewrite with channel adaptation
                rewritten = _human_rewrite_reply(
                    draft=brain_reply,
                    brand=sales_ctx.brand,
                    channel=channel,
                    stage=stage,
                    settings=django_settings,
                )
                # Use rewritten if successful, fallback to brain_reply
                reply = rewritten or brain_reply

                # Post-processing
                reply = _avoid_consecutive_repeat(reply, conversation)
                reply = _append_product_links(reply, products, sales_ctx.business.org_slug)
                final_reply = _append_payment_links(reply, sales_ctx.business.payment_methods, sales_ctx.business.org_slug)

                # P2.4: Optional pre-send evaluation (informative, doesn't block)
                try:
                    from .sales_evaluator import evaluate_reply
                    evaluation = evaluate_reply(final_reply, stage, buyer, sales_ctx.commerce_rules, django_settings)
                    # Store in conversation metadata for logging
                    if not hasattr(conversation, 'metadata') or not conversation.metadata:
                        conversation.metadata = {}
                    conversation.metadata['last_evaluation'] = {
                        'score': evaluation['score'],
                        'flags': evaluation['flags'],
                        'action': evaluation['action'],
                    }
                except Exception:
                    pass  # Evaluation failure doesn't block the reply

                return final_reply

        # Fallback to heuristic reply
        reply = _heuristic_reply(
            message_text=message_text,
            stage=stage,
            buyer=buyer,
            products=products,
            stock_info=stock_info,
            promotions=promotions,
            sales_ctx=sales_ctx,
        )
        reply = _avoid_consecutive_repeat(reply, conversation)
        reply = _append_product_links(reply, products, sales_ctx.business.org_slug)
        final_reply = _append_payment_links(reply, sales_ctx.business.payment_methods, sales_ctx.business.org_slug)

        # P2.4: Optional pre-send evaluation (informative, doesn't block)
        try:
            from .sales_evaluator import evaluate_reply
            from django.conf import settings as django_settings
            evaluation = evaluate_reply(final_reply, stage, buyer, sales_ctx.commerce_rules, django_settings)
            # Store in conversation metadata for logging
            if not hasattr(conversation, 'metadata') or not conversation.metadata:
                conversation.metadata = {}
            conversation.metadata['last_evaluation'] = {
                'score': evaluation['score'],
                'flags': evaluation['flags'],
                'action': evaluation['action'],
            }
        except Exception:
            pass  # Evaluation failure doesn't block the reply

        return final_reply

    except Exception as exc:
        logger.warning('generate_reply_error', error=str(exc))
        return 'Voy a ayudarte. Un momento, por favor.'


def _guard_out_of_scope_brand_query(message_text: str, sales_ctx: SalesContext) -> str | None:
    """
    Detect if user is asking about competitor or general knowledge (out of scope).
    Returns a scope-respecting reply if detected, else None.
    """
    forbidden_actions = getattr(sales_ctx.business, 'forbidden_actions', [])
    competitors = [
        'apple', 'samsung', 'iphone', 'galaxy', 'manzana', 'samsung', 'huawei',
        'xiaomi', 'motorola', 'lg', 'sony', 'nokia',
    ]
    text_lower = message_text.lower()
    for competitor in competitors:
        if competitor in text_lower and any(
            token in text_lower for token in ('mejor', 'vs ', 'versus', 'comparar', 'cual es mejor', 'precio')
        ):
            return (
                'Entiendo tu pregunta. Yo estoy aquí para ayudarte con nuestros productos, '
                'que están diseñados específicamente para ofrecerte la mejor relación calidad-precio. '
                '¿Qué características buscas?'
            )
    return None
