"""
Response Generator — LLM that generates sales conversation replies.
Uses gpt-5.4-mini as default (main sales model).
Falls back to gpt-5.4 for complex cases if confidence is low.
"""
import logging
from typing import Optional, Dict, List

from django.conf import settings
import openai

from .llm_router import LLMRouter

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
            # Fallback to safe generic reply
            return ResponseGenerator._fallback_reply(situation, action)

        try:
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            model = LLMRouter.model_for_task(action.get('response_strategy', 'main_response'))

            # Build system prompt
            system_prompt = ResponseGenerator._build_system_prompt(session, situation, action, context)

            # Build conversation for LLM
            messages = ResponseGenerator._build_messages(conversation_history, user_message)

            # Call LLM
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
                temperature=0.7,
                max_tokens=350,
            )

            reply = response.choices[0].message.content.strip()
            logger.info(f'Generated reply ({len(reply)} chars, model={model})')
            return reply

        except Exception as e:
            logger.error(f'Response generation failed: {e}')
            return ResponseGenerator._fallback_reply(situation, action)

    @staticmethod
    def _build_system_prompt(session, situation: str, action: dict, context: dict) -> str:
        """
        Build comprehensive system prompt.

        Includes: identity, rules, state, KB, products, strategy.

        Args:
            session: SalesSession
            situation: Customer situation
            action: DecisionEngine action
            context: Loaded context

        Returns:
            System prompt string
        """
        org = session.organization
        has_products = bool(context.get('recommended_products'))

        lines = [
            f'Eres el agente de ventas de {org.name}. Respondes en español, de forma natural y concisa.',
            'Canal: app (máximo 2-3 oraciones, directo al punto).',
            'Responde SIEMPRE en español.',
            '',
            '## REGLAS ABSOLUTAS — nunca las rompas',
            '- SOLO puedes hablar de productos que aparecen en la sección "## Productos disponibles" de este prompt.',
            '- Si esa sección está vacía o no tiene lo que el cliente pide: dile claramente que no tienes ese producto.',
            '- NUNCA inventes productos, marcas, modelos, precios, materiales ni características.',
            '- NUNCA digas "estaré atento" ni "lo buscaré" — si no está en el catálogo, no lo tienes.',
            '- Si el cliente pregunta algo fuera de ventas (historia, noticias, política, etc.): una sola oración amable redirigiéndolo.',
            '- Máximo 2 productos mencionados por turno.',
            '- No hables de competidores.',
            '',
        ]

        # Explicit instruction when no products in context
        if not has_products:
            lines += [
                '## IMPORTANTE: Sin productos disponibles',
                'No hay productos en el catálogo que coincidan con lo que el cliente pide.',
                'Dile honestamente que no tienes ese producto específico.',
                'Puedes preguntar si le interesa ver otras opciones similares que sí tenemos.',
                '',
            ]

        lines += [
            '## Contexto actual',
            f'Etapa: {session.stage}',
            f'Situación: {situation}',
            f'Estrategia: {action.get("response_strategy", "default")}',
            '',
        ]

        # Session state
        state_lines = []
        if session.selected_products:
            state_lines.append(f'Productos seleccionados: {len(session.selected_products)}')
        if session.budget_min or session.budget_max:
            state_lines.append(f'Presupuesto: ${session.budget_min or "?"}-${session.budget_max or "?"}')
        if session.objections:
            state_lines.append(f'Objeciones: {", ".join(session.objections[:2])}')
        if session.category_interest:
            state_lines.append(f'Categoría de interés: {session.category_interest}')
        if state_lines:
            lines += state_lines + ['']

        # KB content
        if context.get('kb_content'):
            lines.append('## Información relevante')
            lines.append(context['kb_content'][:500])
            lines.append('')

        # Products — the source of truth
        if has_products:
            lines.append('## Productos disponibles (SOLO estos puedes mencionar)')
            for product in context['recommended_products'][:3]:
                price_str = f"${product['price_min']}" if product.get('price_min') else "Consultar precio"
                desc = product.get('description', '')[:80]
                lines.append(f"- **{product['title']}**: {price_str}")
                if desc:
                    lines.append(f"  {desc}")
                if product.get('promotion'):
                    lines.append(f"  Promoción: {product['promotion']['title']}")
            lines.append('')

        # Promotions
        if context.get('promotions'):
            lines.append('## Promociones activas')
            for promo in context['promotions'][:2]:
                lines.append(f"- {promo['title']}: {promo['description'][:60]}")
            lines.append('')

        # Strategy guidance
        strategy_guidance = {
            'discover': 'Muestra 1-2 productos disponibles del catálogo. Si el cliente dio preferencias, muestra los que más encajan.',
            'recommend': 'Recomienda 1-2 productos SOLO del listado de productos disponibles. Menciona precio y característica clave.',
            'close': 'Enfócate en cerrar la venta. Pregunta si quiere proceder.',
            'inform': 'Da la información solicitada de forma clara y concisa.',
            'clarify': 'Haz UNA sola pregunta para entender mejor qué necesita.',
            'redirect': 'En una oración, explica que solo puedes ayudar con los productos de la tienda.',
        }

        strategy = action.get('response_strategy', 'discover')
        if strategy in strategy_guidance:
            lines.append(f'## Estrategia: {strategy_guidance[strategy]}')

        return '\n'.join(lines)

    @staticmethod
    def _build_messages(conversation_history: list, user_message: str) -> list:
        """
        Build conversation turns for LLM.

        Args:
            conversation_history: Recent Message objects
            user_message: Current message

        Returns:
            List of {"role": ..., "content": ...} dicts
        """
        messages = []

        # Add recent history (last 8 turns, alternating user/bot)
        for msg in conversation_history[-8:]:
            if msg.role == 'user':
                messages.append({"role": "user", "content": msg.content})
            elif msg.role == 'bot':
                messages.append({"role": "assistant", "content": msg.content})

        # Add current message
        messages.append({"role": "user", "content": user_message})

        return messages

    @staticmethod
    def _fallback_reply(situation: str, action: dict) -> str:
        """
        Safe fallback reply when LLM unavailable.

        Args:
            situation: Customer situation
            action: DecisionEngine action

        Returns:
            Generic safe reply
        """
        if situation == 'off_topic':
            return 'Disculpa, puedo ayudarte con nuestros productos. ¿Hay algo que quieras conocer?'
        elif situation == 'prompt_injection':
            return '¿En qué puedo ayudarte con nuestros productos?'
        elif situation == 'out_of_catalog':
            return 'Ese producto no lo tenemos, pero te puedo mostrar alternativas similares. ¿Qué tipo de producto buscas?'
        elif action.get('response_strategy') == 'close':
            return '¿Quieres confirmar tu orden para proceder al pago?'
        else:
            return 'Gracias por tu mensaje. ¿En qué puedo ayudarte?'
