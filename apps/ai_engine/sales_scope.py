"""
Sales scope enforcement: guard against out-of-scope requests and strengthen closing replies.
"""
from __future__ import annotations

import re
from typing import Any

from .sales_models import (
    STAGE_CHECKOUT_BLOCKED,
    STAGE_DISCOVERING,
    STAGE_INTENT_TO_BUY,
    BrandProfile,
    BuyerProfile,
    SalesContext,
    SalesPlaybook,
)


def _enforce_reply_scope(*, message_text: str, reply_text: str, sales_ctx: SalesContext, stage: str) -> str:
    """Block suspicious general-knowledge replies that don't anchor to the business."""
    from .sales_reply import _apply_brand_voice

    reply = ' '.join((reply_text or '').split()).strip()
    if not reply:
        return reply

    scope_terms = _build_scope_terms(sales_ctx)
    suspicious_general_patterns = (
        'es una region',
        'es una región',
        'conocida por',
        'hogar del',
        'destinos turisticos',
        'destinos turísticos',
        'paisajes',
        'capital de',
        'presidente',
        'gobierno',
        'historia de',
    )
    if any(pattern in reply.lower() for pattern in suspicious_general_patterns):
        if not any(term in reply.lower() for term in scope_terms):
            brand_name = sales_ctx.brand.brand_name or sales_ctx.business.org_name or 'la organizacion'
            what_you_sell = _normalize_offer_text(sales_ctx.business.what_you_sell) or 'sus servicios y procesos'
            safe_reply = (
                f'Solo te puedo ayudar con {brand_name}, {what_you_sell}, politicas, requisitos y atencion de la organizacion. '
                'Si quieres, dime tu duda concreta y te ayudo dentro de ese contexto.'
            )
            return _apply_brand_voice(safe_reply, sales_ctx.brand, sales_ctx.playbook, stage)
    return reply


def _strengthen_closing_reply(
    *,
    reply_text: str,
    stage: str,
    close_signals: list[str],
    products: list[dict[str, Any]],
    sales_ctx: SalesContext,
) -> str:
    """Enhance closing-stage replies with explicit CTAs aligned to purchase signals."""
    reply = ' '.join((reply_text or '').split()).strip()
    if not reply or stage not in (STAGE_INTENT_TO_BUY, STAGE_CHECKOUT_BLOCKED):
        return reply
    if not close_signals:
        return reply

    lowered = reply.lower()
    if any(token in lowered for token in ('prefieres', 'te lo dejo', 'lo dejamos listo', 'cerramos', 'te ayudo a dejarlo listo')):
        return reply

    product_title = products[0]['title'] if products else 'la opcion'
    payment_methods = sales_ctx.business.payment_methods or ['transferencia bancaria', 'efectivo']
    payment_label = ' o '.join(payment_methods[:2])

    if 'payment_intent' in close_signals:
        cta = f'Si te cuadra {product_title}, lo dejamos listo hoy. ¿Prefieres pagar por {payment_label}?'
    elif 'availability_check' in close_signals or 'delivery_check' in close_signals:
        cta = f'Si te sirve {product_title}, te ayudo a dejar el pedido listo hoy. ¿Lo armamos?'
    else:
        cta = f'Si esta es la opcion que te encaja, te ayudo a cerrarlo ahora mismo. ¿Te la dejo lista?'

    if reply.endswith('?'):
        return reply
    return f'{reply} {cta}'.strip()


def _guard_out_of_scope_request(message_text: str, sales_ctx: SalesContext) -> dict[str, str] | None:
    """Detect when a user asks about unrelated topics (weather, sports, etc.) outside business scope."""
    from .sales_reply import _apply_brand_voice

    brand_block = _guard_out_of_scope_brand_query(message_text, sales_ctx)
    if brand_block:
        return {
            'kind': 'other_brand',
            'reason': 'asked_about_other_company_or_brand',
            'reply': brand_block,
        }

    text = ' '.join((message_text or '').lower().split())
    if not text:
        return None

    unrelated_signals = (
        'clima', 'tiempo hoy', 'pronostico', 'pronóstico', 'llover', 'lluvia',
        'presidente', 'alcalde', 'gobierno', 'politica', 'política', 'elecciones',
        'partido', 'futbol', 'fútbol', 'gol', 'campeon', 'campeón', 'liga',
        'capital de', 'pais de', 'país de', 'historia de', 'quien descubrio', 'quién descubrió',
        'traduceme', 'tradúceme', 'traduce esto', 'resuelve', 'ecuacion', 'ecuación',
        'programacion', 'programación', 'codigo', 'código', 'python', 'javascript',
        'horoscopo', 'horóscopo', 'tarot', 'receta', 'cocinar',
    )
    if not any(signal in text for signal in unrelated_signals):
        return None

    try:
        scope_terms = _build_scope_terms(sales_ctx)
    except Exception:
        scope_terms = set()
    if any(term in text for term in scope_terms):
        return None

    brand_name = sales_ctx.brand.brand_name or sales_ctx.business.org_name or 'la marca'
    what_you_sell = _normalize_offer_text(sales_ctx.business.what_you_sell) or 'nuestros productos'
    reply = (
        f'Aqui solo te puedo ayudar con {brand_name}, {what_you_sell}, disponibilidad, politicas y compra por chat. '
        'Si quieres, te recomiendo una opcion o resolvemos una duda del producto.'
    )
    return {
        'kind': 'unrelated_topic',
        'reason': 'asked_about_topic_outside_business_scope',
        'reply': _apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
    }


def _guard_general_scope_request(message_text: str, sales_ctx: SalesContext) -> dict[str, str] | None:
    """Detect when a user asks for general information outside the business context."""
    from .sales_reply import _apply_brand_voice

    text = ' '.join((message_text or '').lower().split())
    if not text:
        return None

    try:
        scope_terms = _build_scope_terms(sales_ctx)
    except Exception:
        scope_terms = set()
    business_anchor_terms = scope_terms | {
        'producto', 'productos', 'servicio', 'servicios', 'precio', 'precios', 'pago', 'pagos',
        'disponible', 'disponibilidad', 'compra', 'comprar', 'pedido', 'pedidos', 'envio', 'envios',
        'entrega', 'politica', 'politicas', 'horario', 'horarios', 'stock', 'talla', 'tallas',
        'asesor', 'asesoria', 'promocion', 'promociones', 'catalogo', 'afiliacion', 'afiliaciones',
        'subsidio', 'subsidios', 'certificado', 'certificados', 'beneficiario', 'beneficiarios',
        'tramite', 'tramites',
    }
    asks_for_general_info = any(
        signal in text for signal in (
            'hablame de ', 'háblame de ', 'hablame sobre ', 'háblame sobre ',
            'cuentame de ', 'cuéntame de ', 'cuentame sobre ', 'cuéntame sobre ',
            'dime algo de ', 'dime algo sobre ', 'que sabes de ', 'qué sabes de ',
            'informacion de ', 'información de ', 'quiero saber de ',
        )
    )
    if asks_for_general_info and not any(term in text for term in business_anchor_terms):
        brand_name = sales_ctx.brand.brand_name or sales_ctx.business.org_name or 'la marca'
        what_you_sell = _normalize_offer_text(sales_ctx.business.what_you_sell) or 'nuestros productos y servicios'
        reply = (
            f'Solo te puedo ayudar con temas de {brand_name}: {what_you_sell}, procesos, politicas y atencion de la organizacion. '
            'Si quieres, dime tu duda concreta y te ayudo dentro de ese contexto.'
        )
        return {
            'kind': 'unrelated_topic',
            'reason': 'asked_for_general_information_outside_business_scope',
            'reply': _apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING),
        }

    return _guard_out_of_scope_request(message_text, sales_ctx)


def _guard_out_of_scope_brand_query(message_text: str, sales_ctx: SalesContext) -> str | None:
    """Detect when a user asks about other brands/companies instead of the current organization."""
    from .sales_reply import _apply_brand_voice

    text = ' '.join((message_text or '').lower().split())
    if not text:
        return None

    asks_for_identity = any(
        signal in text for signal in (
            'que es ',
            'qué es ',
            'quien es ',
            'quién es ',
            'que hace ',
            'qué hace ',
            'informacion de ',
            'información de ',
            'hablame de ',
            'háblame de ',
            'cuentame de ',
            'cuéntame de ',
        )
    )
    if not asks_for_identity:
        return None

    allowed_terms = _build_scope_terms(sales_ctx)

    referenced_terms = {
        token.strip()
        for token in re.split(r'[^a-z0-9áéíóúñ]+', text)
        if len(token.strip()) >= 4
    }
    ignored_terms = {
        'que', 'qué', 'quien', 'quién', 'hace', 'sobre', 'marca', 'tienda', 'producto',
        'productos', 'info', 'informacion', 'información', 'hablame', 'háblame', 'cuentame',
        'cuéntame', 'como', 'cómo', 'para', 'esta', 'este', 'tienen',
    }
    candidate_terms = referenced_terms - ignored_terms
    external_terms = [term for term in candidate_terms if term not in allowed_terms]
    if not external_terms:
        return None

    brand_name = sales_ctx.brand.brand_name or sales_ctx.business.org_name or 'la marca'
    what_you_sell = _normalize_offer_text(sales_ctx.business.what_you_sell) or 'nuestros productos'
    reply = (
        f'Solo te puedo ayudar con informacion de {brand_name} y de {what_you_sell}. '
        f'Si quieres, te cuento sobre un producto, disponibilidad o cual te conviene mas dentro de {brand_name}.'
    )
    return _apply_brand_voice(reply, sales_ctx.brand, sales_ctx.playbook, STAGE_DISCOVERING)


def _build_scope_terms(sales_ctx: SalesContext) -> set[str]:
    """Extract in-scope keywords from brand, business, products, and knowledge base."""
    allowed_terms = {
        chunk.strip()
        for raw in (
            sales_ctx.brand.brand_name,
            sales_ctx.business.org_name,
            sales_ctx.business.what_you_sell,
            sales_ctx.business.who_you_sell_to,
            sales_ctx.business.industry,
            sales_ctx.business.mission,
        )
        for chunk in re.split(r'[^a-z0-9áéíóúñ]+', (raw or '').lower())
        if len(chunk.strip()) >= 4
    }
    for product in sales_ctx.catalog_snapshot:
        for raw in (product.get('title', ''), product.get('brand', ''), product.get('category', '')):
            for chunk in re.split(r'[^a-z0-9áéíóúñ]+', (raw or '').lower()):
                if len(chunk.strip()) >= 4:
                    allowed_terms.add(chunk.strip())
    for item in sales_ctx.knowledge_snapshot[:12]:
        for raw in (item.get('title', ''), item.get('category', '')):
            for chunk in re.split(r'[^a-z0-9áéíóúñ]+', (raw or '').lower()):
                if len(chunk.strip()) >= 4:
                    allowed_terms.add(chunk.strip())
    return allowed_terms


def _normalize_offer_text(raw: str) -> str:
    cleaned = ' '.join((raw or '').split()).strip(' .,:;')
    if not cleaned:
        return ''

    lowered = cleaned.lower()
    prefixes = (
        'vendemos ', 'venden ', 'vendo ',
        'ofrecemos ', 'ofrecen ', 'ofrezco ',
        'comercializamos ', 'comercializan ',
        'somos ', 'nos dedicamos a ',
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip(' .,:;')
            break

    return cleaned
