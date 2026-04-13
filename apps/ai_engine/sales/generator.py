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

        lines = [
            f'You are {org.name}\'s sales agent.',
            'Respond naturally, concisely, and helpfully.',
            'Channel: app (max 3 sentences, short and scannable).',
            '',
            '## Rules (ALWAYS follow)',
            '- NEVER invent products, prices, or facts',
            '- If you mention a product, use ONLY data provided in Products section',
            '- Never discuss competitors or politics',
            '- Max 2 product recommendations at once',
            '- If out of scope, redirect kindly in 1 sentence',
            '',
            '## Current Context',
            f'Customer stage: {session.stage}',
            f'Situation: {situation}',
            f'Strategy: {action.get("response_strategy", "default")}',
            '',
        ]

        # Add session state summary
        if session.selected_products:
            lines.append(f'Customer selected: {len(session.selected_products)} products')
        if session.budget_min or session.budget_max:
            lines.append(f'Budget: ${session.budget_min or "?"}-${session.budget_max or "?"}')
        if session.objections:
            lines.append(f'Objections: {", ".join(session.objections[:2])}')

        lines.append('')

        # Add KB context if provided
        if context.get('kb_content'):
            lines.append('## Relevant Info')
            lines.append(context['kb_content'][:500])
            lines.append('')

        # Add products if provided
        if context.get('recommended_products'):
            lines.append('## Available Products')
            for product in context['recommended_products'][:3]:
                price_str = f"${product['price_min']}" if product.get('price_min') else "Contact for price"
                lines.append(f"- {product['title']}: {price_str}")
                if product.get('promotion'):
                    promo = product['promotion']
                    lines.append(f"  Promo: {promo['title']}")
            lines.append('')

        # Add promotions if applicable
        if context.get('promotions'):
            lines.append('## Active Promotions')
            for promo in context['promotions'][:2]:
                lines.append(f"- {promo['title']}: {promo['description'][:50]}")
            lines.append('')

        # Add strategy guidance
        strategy_guidance = {
            'discover': 'Ask what they\'re looking for, understand needs.',
            'recommend': 'Suggest 1-2 best matches from available products.',
            'close': 'Move toward checkout, remove friction, confirm intent.',
            'inform': 'Provide requested information clearly and concisely.',
            'clarify': 'Ask clarifying questions to understand their needs better.',
            'redirect': 'Kindly explain you only help with our products, offer to help if relevant.',
        }

        strategy = action.get('response_strategy', 'discover')
        if strategy in strategy_guidance:
            lines.append(f'## Strategy: {strategy_guidance[strategy]}')

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
