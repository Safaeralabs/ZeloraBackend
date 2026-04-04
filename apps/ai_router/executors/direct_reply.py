"""
DirectReplyExecutor: generates a bot reply using KB context + LLM or heuristic fallback.
"""
from __future__ import annotations

from .base import BaseExecutor

_INTENT_HEURISTICS: dict[str, str] = {
    'buy_intent': 'Gracias por tu interes. Que producto o servicio estas buscando?',
    'order_status': 'Para consultar el estado de tu pedido necesito tu numero de orden. Me lo puedes compartir?',
    'product_inquiry': 'Claro. Cuentame que producto o categoria te interesa y te doy la informacion disponible.',
    'price_inquiry': 'Te ayudo con precios. Sobre que producto o servicio quieres saber el costo?',
    'return_request': 'Entiendo que quieres gestionar una devolucion. Me puedes indicar el numero de tu pedido?',
    'general_faq': 'Recibi tu consulta. Hay algo mas especifico en lo que pueda ayudarte?',
    'check_subsidy': 'Puedo ayudarte con el subsidio. Comparte tu numero de cedula para continuar.',
    'request_certificate': 'Puedo ayudarte con el certificado. Necesito tu numero de cedula.',
    'book_appointment': 'Vamos a agendar tu cita. Que servicio necesitas y cual es tu disponibilidad?',
    'unknown': 'Recibi tu mensaje. En que puedo ayudarte hoy?',
}


class DirectReplyExecutor(BaseExecutor):
    def execute(self, *, conversation, message, decision, organization) -> str | None:
        from apps.knowledge_base.models import KBArticle
        from django.conf import settings
        from django.db.models import Q

        user_message = message.content
        words = [w for w in user_message.lower().split() if len(w) > 3][:5]
        q_filter = Q()
        for w in words:
            q_filter |= Q(title__icontains=w) | Q(content__icontains=w)

        kb_articles = KBArticle.objects.filter(
            organization=organization,
            status='published',
        ).filter(q_filter)[:3]

        context = '\n'.join([f'### {a.title}\n{a.content[:400]}' for a in kb_articles])

        if getattr(settings, 'ENABLE_REAL_AI', False) and getattr(settings, 'OPENAI_API_KEY', ''):
            reply = self._call_llm(user_message, context, decision, organization, settings)
            if reply:
                return reply

        return self._heuristic(user_message, context, decision)

    def _call_llm(self, user_message, context, decision, organization, settings) -> str | None:
        try:
            import openai
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            org_name = getattr(organization, 'name', 'la empresa')
            system_prompt = (
                f'Eres el asistente virtual de {org_name}. '
                'Responde de manera amable, clara y concisa. Maximo 3 oraciones. '
                'Ayuda con preguntas sobre productos, pedidos y atencion al cliente.'
            )
            if context:
                system_prompt += f'\n\nBase de conocimiento:\n{context}'
            completion = client.chat.completions.create(
                model=decision.model_name or getattr(settings, 'OPENAI_ROUTER_MODEL', 'gpt-4.1-nano'),
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ],
                max_tokens=300,
                temperature=0.6,
            )
            return completion.choices[0].message.content or None
        except Exception:
            return None

    def _heuristic(self, user_message: str, context: str, decision) -> str:
        base = _INTENT_HEURISTICS.get(decision.intent, _INTENT_HEURISTICS['unknown'])
        if context and decision.intent in ('general_faq', 'unknown'):
            return f'Basado en nuestra informacion: {context[:280]}... Te ayudo con algo mas?'
        return base
