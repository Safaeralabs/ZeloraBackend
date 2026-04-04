"""
OpenAI usage tracker.

Call `track(...)` after any OpenAI API call. It is fire-and-forget:
it runs in a daemon thread so it never adds latency to the hot path.

Cost reference (per 1M tokens, April 2025):
  gpt-4o           input $2.50  output $10.00
  gpt-4o-mini      input $0.15  output  $0.60
  gpt-4.1          input $2.00  output  $8.00
  gpt-4.1-mini     input $0.40  output  $1.60
  gpt-4.1-nano     input $0.10  output  $0.40
  text-embedding-3-small  $0.02 / 1M tokens (no output)
"""
from __future__ import annotations

import threading
from decimal import Decimal

import structlog

logger = structlog.get_logger(__name__)

# (input_per_1M, output_per_1M)  — USD
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    'gpt-4o':                    (2.50,  10.00),
    'gpt-4o-mini':               (0.15,   0.60),
    'gpt-4.1':                   (2.00,   8.00),
    'gpt-4.1-mini':              (0.40,   1.60),
    'gpt-4.1-nano':              (0.10,   0.40),
    'gpt-4-turbo':               (10.00,  30.00),
    'gpt-4':                     (30.00,  60.00),
    'text-embedding-3-small':    (0.02,   0.00),
    'text-embedding-3-large':    (0.13,   0.00),
    'text-embedding-ada-002':    (0.10,   0.00),
}


def _compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    key = next((k for k in _PRICE_TABLE if model.startswith(k)), None)
    if not key:
        return Decimal('0')
    input_price, output_price = _PRICE_TABLE[key]
    cost = (prompt_tokens / 1_000_000) * input_price + (completion_tokens / 1_000_000) * output_price
    return Decimal(str(round(cost, 6)))


def _write(organization_id: str, feature: str, model: str, prompt_tokens: int, completion_tokens: int, latency_ms: int) -> None:
    try:
        from .models import OpenAIUsageLog
        from apps.accounts.models import Organization
        org = Organization.objects.get(id=organization_id)
        total = prompt_tokens + completion_tokens
        cost = _compute_cost(model, prompt_tokens, completion_tokens)
        OpenAIUsageLog.objects.create(
            organization=org,
            feature=feature,
            model_name=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        logger.warning('openai_usage_track_error', error=str(exc))


def track(
    *,
    organization_id: str,
    feature: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int = 0,
) -> None:
    """Fire-and-forget — never blocks the caller."""
    threading.Thread(
        target=_write,
        args=(organization_id, feature, model, prompt_tokens, completion_tokens, latency_ms),
        daemon=True,
    ).start()
