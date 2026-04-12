"""
P2.4: Pre-send reply evaluator.

Evaluates a draft reply on 4 dimensions (coherence, naturalness, brand fit, CTA quality).
Uses gpt-4o-mini for speed. Returns score + flags + action (send | rewrite | escalate).

Only evaluates in high-friction stages: intent_to_buy, considering, checkout_blocked.
"""
from __future__ import annotations

import json
import structlog
from typing import Any

from .sales_models import BuyerProfile, CommerceRules, STAGE_INTENT_TO_BUY, STAGE_CONSIDERING, STAGE_CHECKOUT_BLOCKED

logger = structlog.get_logger(__name__)


def evaluate_reply(
    reply: str, stage: str, buyer: BuyerProfile, commerce_rules: CommerceRules, settings
) -> dict[str, Any]:
    """
    P2.4: Evaluate reply quality before sending.

    Scores on 4 dimensions (0-5):
      - coherencia: does it make sense, is it logically consistent?
      - naturalidad: does it sound human, conversational, natural?
      - brand_fit: does it align with brand tone, avoid forbidden phrases?
      - cta_quality: is the CTA clear, actionable, and appropriate?

    Returns:
        {
            'score': float 0-1,
            'coherencia': int 0-5,
            'naturalidad': int 0-5,
            'brand_fit': int 0-5,
            'cta_quality': int 0-5,
            'flags': list[str],  # 'forbidden_claim', 'too_long', 'no_cta', 'off_topic', 'unnatural'
            'action': 'send' (score>=0.7) | 'rewrite' (0.4-0.7) | 'escalate' (<0.4 or forbidden)
            'feedback': str,  # brief human-readable feedback
        }
    """
    # Only evaluate in high-friction stages
    if stage not in (STAGE_INTENT_TO_BUY, STAGE_CONSIDERING, STAGE_CHECKOUT_BLOCKED):
        return {
            'score': 1.0,
            'coherencia': 5,
            'naturalidad': 5,
            'brand_fit': 5,
            'cta_quality': 5,
            'flags': [],
            'action': 'send',
            'feedback': 'Low-friction stage, skipped evaluation',
        }

    try:
        import openai

        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

        forbidden_claims = (commerce_rules.forbidden_claims or [])[:5]
        forbidden_promises = (commerce_rules.forbidden_promises or [])[:5]

        system_prompt = """Evalúa la calidad de este mensaje de ventas en 4 dimensiones (0-5 cada una).

Dimensiones:
1. coherencia: ¿Tiene sentido lógico? ¿Es consistente?
2. naturalidad: ¿Suena humano, conversacional, natural (no robótico)?
3. brand_fit: ¿Respeta el tono de marca? ¿Evita claims prohibidos?
4. cta_quality: ¿Tiene CTA clara, accionable? ¿Es apropiada para el stage?

Responde con JSON:
{
  "coherencia": <0-5>,
  "naturalidad": <0-5>,
  "brand_fit": <0-5>,
  "cta_quality": <0-5>,
  "flags": ["flag1", "flag2"],
  "feedback": "texto corto"
}

Flags posibles: forbidden_claim, too_long, no_cta, off_topic, unnatural, generic."""

        user_prompt = f"""Evalúa este mensaje de ventas:

MENSAJE:
---
{reply}
---

CONTEXTO:
- Stage: {stage}
- Buyer urgency: {buyer.urgency}
- Buyer priority: {buyer.priority}
- Forbidden claims: {', '.join(forbidden_claims) or 'ninguno'}
- Forbidden promises: {', '.join(forbidden_promises) or 'ninguno'}"""

        completion = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            max_tokens=250,
            temperature=0,
            response_format={'type': 'json_object'},
        )

        result_text = completion.choices[0].message.content or '{}'
        result = json.loads(result_text)

        # Extract scores
        coherencia = int(result.get('coherencia', 3))
        naturalidad = int(result.get('naturalidad', 3))
        brand_fit = int(result.get('brand_fit', 3))
        cta_quality = int(result.get('cta_quality', 3))
        flags = result.get('flags', [])
        feedback = result.get('feedback', '')

        # Compute composite score (0-1)
        mean_score = (coherencia + naturalidad + brand_fit + cta_quality) / 20.0

        # Decide action
        if 'forbidden_claim' in flags:
            action = 'escalate'
        elif mean_score >= 0.7:
            action = 'send'
        elif mean_score >= 0.4:
            action = 'rewrite'
        else:
            action = 'escalate'

        return {
            'score': round(mean_score, 2),
            'coherencia': coherencia,
            'naturalidad': naturalidad,
            'brand_fit': brand_fit,
            'cta_quality': cta_quality,
            'flags': flags,
            'action': action,
            'feedback': feedback,
        }

    except Exception as exc:
        logger.warning('evaluate_reply_error', error=str(exc))
        # Safe fallback: allow send with low confidence
        return {
            'score': 0.5,
            'coherencia': 3,
            'naturalidad': 3,
            'brand_fit': 3,
            'cta_quality': 3,
            'flags': ['evaluation_error'],
            'action': 'send',
            'feedback': f'Evaluation failed: {str(exc)[:50]}',
        }
