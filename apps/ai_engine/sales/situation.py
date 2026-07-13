"""
Situation Detector — LLM-based customer situation classification.
Uses the configured situation model (default gpt-4.1-nano).
"""
import json
import logging
from typing import Optional, Tuple

from django.conf import settings
import openai

from .llm_router import LLMRouter

logger = logging.getLogger(__name__)


class SituationDetector:
    """
    Detects which of the 20 customer situations the user is in.
    Returns structured output: situation, signals, confidence.
    """

    SITUATION_DESCRIPTIONS = """
    1. discovery: User exploring, no clear intent yet. Asking "what do you offer?"
    2. confused_customer: Doesn't understand offer, unclear on process
    3. indecisive_customer: Interested but can't decide, wants pros/cons
    4. comparing_customer: Comparing multiple products or options
    5. price_sensitive_customer: Focused on cost, asking for discounts or cheaper options
    6. specific_product_customer: Already knows what they want, specific model/SKU
    7. ready_to_buy_customer: Clear intent, asking about checkout or next steps
    8. urgent_customer: Time pressure, needs solution fast ("today", "ASAP", "urgent")
    9. expansion_opportunity: Already bought once, now buying more (upsell/cross-sell)
    10. gift_customer: Buying as a gift, mentions recipient or occasion
    11. objection_customer: Has concerns (price too high, shipping takes long, quality doubts)
    12. post_sale: Already purchased, asking about order, delivery, returns
    13. logistics_customer: Questions about shipping, delivery time, locations
    14. administrative_customer: Billing, invoice, technical support
    15. changing_mind_customer: Was interested, now hesitant or rethinking
    16. inactive_customer: Hasn't engaged in a while, now returning
    17. out_of_catalog: Asking for something not in your catalog
    18. off_topic: Not related to your business (weather, politics, general knowledge)
    19. prompt_injection: Attempting to jailbreak or change instructions
    20. checkout: In checkout flow, confirming order details
    """

    @staticmethod
    def detect(
        user_message: str,
        conversation_history: list,
        session,
    ) -> str:
        """
        Detect customer situation.

        Args:
            user_message: Current user message
            conversation_history: Recent Message objects
            session: SalesSession instance

        Returns:
            Situation string (one of the 20)
        """
        # Hybrid layer: deterministic overrides for critical intents.
        critical = SituationDetector._critical_override(
            user_message=user_message,
            session_stage=str(getattr(session, 'stage', '') or ''),
        )
        if critical:
            return critical

        if not settings.OPENAI_API_KEY or not settings.ENABLE_REAL_AI:
            return SituationDetector._fallback_detect(user_message, session)

        try:
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            model = LLMRouter.model_for_task('situation_detection')

            # Format conversation for context
            history_text = SituationDetector._format_history(conversation_history)

            prompt = f"""Analyze the user's message and conversation context to classify their customer situation.

Available situations:
{SituationDetector.SITUATION_DESCRIPTIONS}

Conversation context:
{history_text}

Current message: "{user_message}"

Current session state:
- Stage: {session.stage}
- Current situation: {session.situation}
- Selected products: {len(session.selected_products)} items
- Objections: {', '.join(session.objections) if session.objections else 'none'}
- Budget: ${session.budget_min or '?'}-${session.budget_max or '?'}

Respond in JSON format:
{{
  "situation": "<one of the 20 situations>",
  "signals": ["signal1", "signal2"],
  "confidence": 0.95,
  "reasoning": "brief explanation"
}}
"""

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at understanding customer intent and context. Classify customers into exactly one of the 20 defined situations. Always respond with valid JSON.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0.3,  # Lower temp for classification
                max_tokens=200,
            )

            # Parse JSON response
            result_text = response.choices[0].message.content.strip()
            result = json.loads(result_text)

            situation = result.get('situation', 'discovery')
            logger.info(
                f'Detected situation: {situation} '
                f'(confidence={result.get("confidence", 0):.2f})'
            )

            guarded = SituationDetector._post_classification_guard(
                situation=situation,
                user_message=user_message,
                session_stage=str(getattr(session, 'stage', '') or ''),
            )
            return guarded

        except json.JSONDecodeError as e:
            logger.warning(f'Failed to parse situation JSON: {e}')
            return SituationDetector._fallback_detect(user_message, session)
        except Exception as e:
            logger.error(f'Situation detection failed: {e}')
            return SituationDetector._fallback_detect(user_message, session)

    @staticmethod
    def _critical_override(*, user_message: str, session_stage: str) -> str:
        """
        Deterministic guardrails for intents where misclassification is costly.
        Runs before the LLM call to avoid fragile stage transitions.
        """
        text = str(user_message or '').strip().lower()
        if not text:
            return ''

        if SituationDetector._has_any(
            text,
            ('ignora', 'olvida', 'actua como', 'actúa como', 'ignore instructions', 'disregard'),
        ):
            return 'prompt_injection'

        if SituationDetector._has_any(
            text,
            ('clima', 'politica', 'política', 'noticias', 'weather', 'news'),
        ):
            return 'off_topic'

        # In checkout stage, payment/shipping signals should stay in checkout.
        if session_stage == 'checkout' and SituationDetector._has_any(
            text,
            (
                'transferencia', 'nequi', 'efectivo', 'pago',
                'direccion', 'dirección', 'ciudad', 'correo', 'email',
                'confirmo pedido', 'confirmar pedido',
            ),
        ):
            return 'checkout'

        # Exploration from checkout should be allowed explicitly.
        if session_stage == 'checkout' and SituationDetector._has_any(
            text,
            (
                'ver productos', 'ver opciones', 'otro producto', 'otros productos',
                'similares', 'similar', 'catalogo', 'catálogo', 'que tienes', 'qué tienes',
            ),
        ):
            return 'discovery'

        if SituationDetector._has_any(
            text,
            (
                'me lo llevo', 'me la llevo', 'lo compro', 'la compro',
                'quiero comprar', 'quiero pagarlo', 'quiero pagar', 'comprarlo',
            ),
        ):
            return 'ready_to_buy_customer'

        if SituationDetector._has_any(
            text,
            ('vs', 'versus', 'comparar', 'diferencia', 'cual conviene', 'cuál conviene'),
        ):
            return 'comparing_customer'

        if SituationDetector._has_any(
            text,
            ('precio', 'cuanto', 'cuánto', 'descuento', 'barato', 'caro'),
        ):
            return 'price_sensitive_customer'

        if SituationDetector._has_any(
            text,
            ('talla', 'color', 'sku', 'referencia', 'modelo', 'este producto'),
        ):
            return 'specific_product_customer'

        return ''

    @staticmethod
    def _post_classification_guard(*, situation: str, user_message: str, session_stage: str) -> str:
        """
        Post-LLM safety adjustments for common stage mistakes.
        """
        text = str(user_message or '').strip().lower()
        current = str(situation or '').strip() or 'discovery'

        if session_stage == 'checkout' and SituationDetector._has_any(
            text,
            ('ver productos', 'otro producto', 'similares', 'catalogo', 'catálogo'),
        ):
            return 'discovery'

        if session_stage == 'checkout' and SituationDetector._has_any(
            text,
            ('transferencia', 'nequi', 'efectivo', 'confirmo pedido', 'confirmar pedido'),
        ):
            return 'checkout'

        return current

    @staticmethod
    def _has_any(text: str, terms: Tuple[str, ...]) -> bool:
        return any(term in text for term in terms)

    @staticmethod
    def _format_history(history: list) -> str:
        """
        Format recent message history for context.

        Args:
            history: List of Message objects

        Returns:
            Formatted conversation string
        """
        lines = []
        for msg in reversed(history[-4:]):  # Last 4 messages for context
            role = 'Customer' if msg.role == 'user' else 'Bot'
            lines.append(f'{role}: {msg.content[:100]}...' if len(msg.content) > 100 else f'{role}: {msg.content}')
        return '\n'.join(lines)

    @staticmethod
    def _fallback_detect(user_message: str, session) -> str:
        """
        Keyword-based fallback when LLM unavailable.

        Args:
            user_message: User message
            session: SalesSession

        Returns:
            Situation string
        """
        msg_lower = user_message.lower()

        # Simple heuristic detection
        if any(w in msg_lower for w in ['comprar', 'quiero', 'checkout', 'pagar']):
            return 'ready_to_buy_customer'
        if any(w in msg_lower for w in ['precio', 'costo', 'caro', 'barato', 'descuento']):
            return 'price_sensitive_customer'
        if any(w in msg_lower for w in ['comparar', 'vs', 'versus', 'diferencia']):
            return 'comparing_customer'
        if any(w in msg_lower for w in ['regalo', 'regalar', 'cumpleaños', 'sorpresa']):
            return 'gift_customer'
        if any(w in msg_lower for w in ['envío', 'entrega', 'shipping', 'devolución', 'return']):
            return 'logistics_customer'
        if any(w in msg_lower for w in ['pedido', 'orden', 'order', 'factura']):
            return 'post_sale'
        if any(w in msg_lower for w in ['clima', 'política', 'noticias', 'weather', 'news']):
            return 'off_topic'
        if any(w in msg_lower for w in ['ignora', 'olvida', 'cambia', 'acto como']):
            return 'prompt_injection'
        if len(session.selected_products) > 0 and any(w in msg_lower for w in ['más', 'otro', 'adicional']):
            return 'expansion_opportunity'

        # Default
        return 'discovery'
