from __future__ import annotations

from dataclasses import dataclass, field
import re

import structlog
from django.conf import settings
from django.db.models import Q

from apps.knowledge_base.models import KBArticle

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class GeneralAgentContext:
    agent_name: str
    organization_name: str
    what_you_sell: str = ''
    who_you_sell_to: str = ''
    mission: str = ''
    agent_persona: str = ''
    scope_notes: str = ''
    allowed_topics: list[str] = field(default_factory=list)
    blocked_topics: list[str] = field(default_factory=list)
    handoff_to_sales_when: list[str] = field(default_factory=list)
    handoff_to_human_when: list[str] = field(default_factory=list)
    greeting_message: str = ''
    response_language: str = 'auto'
    handoff_mode: str = 'balanceado'
    max_response_length: str = 'brief'
    model_name: str = 'gpt-4.1-nano'
    brand_profile: dict = field(default_factory=dict)
    knowledge_snippets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GeneralAgentResult:
    agent: str = 'general_agent'
    reply_text: str = ''
    intent: str = 'general_help'
    confidence: float = 0.65
    escalate_to_human: bool = False
    out_of_scope: bool = False
    context_used: dict = field(default_factory=dict)


class GeneralAgent:
    def run(self, *, message_text: str, conversation, organization, router_decision=None, **kwargs) -> GeneralAgentResult:
        general_ctx = _load_general_context(organization)
        cleaned = (message_text or '').strip()
        if not cleaned:
            return GeneralAgentResult(
                reply_text=general_ctx.greeting_message or f'Hola, soy {general_ctx.agent_name}. ¿En qué puedo ayudarte hoy?',
                context_used={'knowledge_found': len(general_ctx.knowledge_snippets)},
            )

        if _is_out_of_scope(cleaned, general_ctx, conversation=conversation):
            return GeneralAgentResult(
                reply_text=_out_of_scope_reply(general_ctx),
                intent='out_of_scope',
                confidence=0.9,
                out_of_scope=True,
                context_used={'knowledge_found': len(general_ctx.knowledge_snippets)},
            )

        reply = _generate_reply(cleaned, general_ctx, router_decision=router_decision, conversation=conversation)
        return GeneralAgentResult(
            reply_text=reply,
            intent='general_help',
            confidence=0.72 if general_ctx.knowledge_snippets else 0.58,
            context_used={
                'knowledge_found': len(general_ctx.knowledge_snippets),
                'agent_name': general_ctx.agent_name,
                'model_name': general_ctx.model_name,
            },
        )


def _load_general_context(organization) -> GeneralAgentContext:
    from apps.channels_config.models import ChannelConfig
    from apps.channels_config.settings_schema import normalise_settings

    cfg = ChannelConfig.objects.filter(organization=organization, channel='onboarding').first()
    s = normalise_settings((cfg.settings if cfg else {}) or {})
    op = s['org_profile']
    ga = s['general_agent']

    what_you_sell = op.get('what_you_sell') or ''
    who_you_sell_to = op.get('who_you_sell_to') or ''

    snippets = _lookup_relevant_knowledge(
        organization=organization,
        query=' '.join(filter(None, [what_you_sell, who_you_sell_to, organization.name])),
        max_snippets=ga.get('max_kb_snippets') or 4,
    )

    return GeneralAgentContext(
        agent_name=ga.get('name') or 'General Agent',
        organization_name=organization.name,
        what_you_sell=what_you_sell,
        who_you_sell_to=who_you_sell_to,
        mission=ga.get('mission_statement') or '',
        agent_persona=ga.get('persona') or '',
        scope_notes=ga.get('scope_notes') or '',
        allowed_topics=ga.get('allowed_topics') or [],
        blocked_topics=ga.get('blocked_topics') or [],
        handoff_to_sales_when=ga.get('handoff_to_sales_when') or [],
        handoff_to_human_when=ga.get('handoff_to_human_when') or [],
        greeting_message=ga.get('greeting_message') or '',
        response_language=ga.get('response_language') or 'auto',
        handoff_mode=ga.get('handoff_mode') or 'balanceado',
        max_response_length=ga.get('max_response_length') or 'brief',
        model_name=ga.get('model_name') or 'gpt-4.1-nano',
        brand_profile=op.get('brand') or {},
        knowledge_snippets=snippets,
    )


def _lookup_relevant_knowledge(*, organization, query: str, max_snippets: int = 4) -> list[str]:
    terms = [word.strip() for word in (query or '').split() if len(word.strip()) > 3][:6]
    if not terms:
        return []
    filters = Q()
    for term in terms:
        filters |= Q(title__icontains=term) | Q(content__icontains=term)
    limit = max(1, min(int(max_snippets), 20))
    articles = KBArticle.objects.filter(
        organization=organization,
        status='published',
        is_active=True,
    ).filter(filters)[:limit]
    return [f'{article.title}: {article.content[:320]}' for article in articles]


def _is_out_of_scope(message_text: str, ctx: GeneralAgentContext, conversation=None) -> bool:
    text = ' '.join((message_text or '').lower().split())
    if not text:
        return False

    allowed_terms = _build_scope_terms(ctx)
    # If prior conversation context is in-scope, augment allowed_terms with prior user message content
    prior_texts = _get_recent_user_messages(conversation, limit=3)
    for prior_msg in prior_texts:
        prior_lower = ' '.join(prior_msg.lower().split())
        for chunk in re.split(r'[^a-z0-9áéíóúñ]+', prior_lower):
            if len(chunk.strip()) >= 4:
                allowed_terms.add(chunk.strip())

    if _asks_about_other_entity(text, allowed_terms):
        return True

    unrelated_signals = (
        'clima', 'tiempo hoy', 'pronostico', 'pronóstico', 'lluvia', 'temperatura',
        'presidente', 'alcalde', 'gobierno', 'politica', 'política', 'elecciones',
        'partido', 'futbol', 'fútbol', 'campeon', 'campeón', 'liga',
        'capital de', 'pais de', 'país de', 'historia de',
        'traduceme', 'tradúceme', 'traduce esto',
        'ecuacion', 'ecuación', 'programacion', 'programación', 'codigo', 'código',
        'python', 'javascript', 'horoscopo', 'horóscopo', 'tarot', 'receta',
    )
    if any(signal in text for signal in unrelated_signals):
        return not any(term in text for term in allowed_terms)

    asks_for_general_info = any(
        signal in text for signal in (
            'hablame de ', 'háblame de ', 'hablame sobre ', 'háblame sobre ',
            'cuentame de ', 'cuéntame de ', 'cuentame sobre ', 'cuéntame sobre ',
            'dime algo de ', 'dime algo sobre ', 'que sabes de ', 'qué sabes de ',
            'informacion de ', 'información de ', 'quiero saber de ',
        )
    )
    business_anchor_terms = allowed_terms | {
        'producto', 'productos', 'servicio', 'servicios', 'precio', 'precios', 'pago', 'pagos',
        'disponible', 'disponibilidad', 'compra', 'comprar', 'pedido', 'pedidos', 'envio', 'envíos',
        'entrega', 'politica', 'política', 'politicas', 'políticas', 'horario', 'horarios',
        'afiliado', 'afiliados', 'subsidio', 'subsidios', 'credito', 'crédito', 'creditos', 'créditos',
        'teatro', 'educacion', 'educación', 'alquiler', 'espacios',
    }
    if asks_for_general_info and not any(term in text for term in business_anchor_terms):
        return True

    return False


def _get_recent_user_messages(conversation, limit: int = 3) -> list[str]:
    """Returns last N user message texts for scope context. Excludes the current message."""
    if not conversation:
        return []
    try:
        msgs = list(conversation.messages.filter(role='user').order_by('-timestamp')[:limit + 1])
        # Skip the most recent (current) message, take the ones before it
        return [' '.join((m.content or '').split()) for m in msgs[1:limit + 1] if m.content]
    except Exception:
        return []


def _build_scope_terms(ctx: GeneralAgentContext) -> set[str]:
    allowed_terms: set[str] = set()
    for raw in (
        ctx.organization_name,
        ctx.what_you_sell,
        ctx.who_you_sell_to,
        ctx.mission,
        ctx.scope_notes,
        ' '.join(ctx.allowed_topics),
        ' '.join(ctx.handoff_to_sales_when),
    ):
        for chunk in re.split(r'[^a-z0-9áéíóúñ]+', (raw or '').lower()):
            if len(chunk.strip()) >= 4:
                allowed_terms.add(chunk.strip())
    for raw in ctx.blocked_topics:
        for chunk in re.split(r'[^a-z0-9Ã¡Ã©Ã­Ã³ÃºÃ±]+', raw.lower()):
            token = chunk.strip()
            if len(token) >= 4 and token in allowed_terms:
                allowed_terms.discard(token)
    for snippet in ctx.knowledge_snippets[:8]:
        for chunk in re.split(r'[^a-z0-9áéíóúñ]+', snippet.lower()):
            if len(chunk.strip()) >= 4:
                allowed_terms.add(chunk.strip())
    return allowed_terms


def _asks_about_other_entity(text: str, allowed_terms: set[str]) -> bool:
    asks_for_identity = any(
        signal in text for signal in (
            'que es ', 'qué es ', 'quien es ', 'quién es ',
            'que hace ', 'qué hace ', 'informacion de ', 'información de ',
            'hablame de ', 'háblame de ', 'cuentame de ', 'cuéntame de ',
        )
    )
    if not asks_for_identity:
        return False

    referenced_terms = {
        token.strip()
        for token in re.split(r'[^a-z0-9áéíóúñ]+', text)
        if len(token.strip()) >= 4
    }
    ignored_terms = {
        'que', 'qué', 'quien', 'quién', 'hace', 'sobre', 'marca', 'tienda', 'producto',
        'productos', 'info', 'informacion', 'información', 'hablame', 'háblame', 'cuentame',
        'cuéntame', 'como', 'cómo', 'para', 'esta', 'este', 'tienen', 'quiero', 'saber',
    }
    candidate_terms = referenced_terms - ignored_terms
    external_terms = [term for term in candidate_terms if term not in allowed_terms]
    return bool(external_terms)


def _out_of_scope_reply(ctx: GeneralAgentContext) -> str:
    offer = ctx.what_you_sell or 'lo relacionado con esta marca'
    return f'Puedo ayudarte solo con {offer}. Si quieres, cuéntame qué necesitas dentro de ese contexto.'


def _generate_reply(message_text: str, ctx: GeneralAgentContext, router_decision=None, conversation=None) -> str:
    knowledge_context = '\n'.join(ctx.knowledge_snippets[:3])
    prompt = (
        f'Eres {ctx.agent_name}, el asistente general de {ctx.organization_name}. '
        'Tu trabajo es responder preguntas basicas de la marca, mantenerte en scope y orientar al usuario. '
        'No cierres ventas agresivamente, no negocies y no prometas condiciones comerciales no confirmadas. '
        f'Que ofrece la marca: {ctx.what_you_sell or "No definido"}.\n'
        f'A quien sirve: {ctx.who_you_sell_to or "No definido"}.\n'
        f'Mision: {ctx.mission or "No definida"}.\n'
        f'Persona: {ctx.agent_persona or "Clara y util"}.\n'
        f'Notas de scope: {ctx.scope_notes or "Responde solo sobre la organizacion y sus servicios/productos."}\n'
        f'Puede responder sobre: {", ".join(ctx.allowed_topics) or "servicios, FAQs, politicas y contexto de marca"}.\n'
        f'Debe bloquear o evitar: {", ".join(ctx.blocked_topics) or "temas fuera del negocio"}.\n'
        f'Debe pasar a Sales cuando: {", ".join(ctx.handoff_to_sales_when) or "detecte intencion comercial real"}.\n'
        f'Debe escalar a humano cuando: {", ".join(ctx.handoff_to_human_when) or "falten datos, haya sensibilidad o reglas especiales"}.\n'
        f'Contexto KB:\n{knowledge_context or "Sin contexto adicional."}'
    )
    if getattr(settings, 'ENABLE_REAL_AI', False) and getattr(settings, 'OPENAI_API_KEY', ''):
        try:
            import openai

            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            chat_history = _build_chat_history_messages(conversation)
            completion = client.chat.completions.create(
                model=(router_decision.model_name if router_decision and router_decision.model_name else ctx.model_name),
                messages=[
                    {'role': 'system', 'content': prompt},
                    *chat_history,
                    {'role': 'user', 'content': message_text},
                ],
                max_tokens=220 if ctx.max_response_length == 'brief' else 320,
                temperature=0.45,
            )
            reply = completion.choices[0].message.content
            if reply:
                return reply.strip()
        except Exception as exc:
            logger.warning('general_agent_llm_error', error=str(exc))

    return _heuristic_reply(message_text, ctx)


def _build_chat_history_messages(conversation) -> list[dict]:
    """
    Build conversation history as real OpenAI message turns.
    Excludes the current (most recent) user message — it is added separately.
    """
    if not conversation:
        return []
    try:
        all_msgs = list(conversation.messages.order_by('-timestamp')[:7])
        prior = list(reversed(all_msgs[1:]))
        result = []
        for msg in prior:
            role = 'user' if msg.role == 'user' else 'assistant'
            content = ' '.join((msg.content or '').split()).strip()
            if content:
                result.append({'role': role, 'content': content[:500]})
        return result
    except Exception:
        return []


def _heuristic_reply(message_text: str, ctx: GeneralAgentContext) -> str:
    if ctx.knowledge_snippets:
        return f'{ctx.knowledge_snippets[0]} Si quieres, te doy el detalle puntual de eso.'
    if ctx.what_you_sell:
        return f'{ctx.organization_name} te puede ayudar con {ctx.what_you_sell}. Cuéntame qué necesitas y te oriento.'
    return f'Soy {ctx.agent_name} y puedo ayudarte con información general de {ctx.organization_name}. ¿Qué te gustaría saber?'
