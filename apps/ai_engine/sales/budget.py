"""
Deterministic budget extraction from a customer message.

Feeds SessionManager.update's context['detected_budget'] hook, which existed
in session.py but had no caller anywhere in the codebase — budget_min/max were
effectively dead fields. Mirrors what a good human seller does when asked
"para regalo, presupuesto de $300": capture the number without needing an LLM
round trip for something this mechanical.

Deliberately conservative: only fires on an explicit number attached to a
money/budget cue (currency symbol, "mil" suffix, or a budget/price keyword).
A bare "300" with no context is too ambiguous (could be a quantity, a size, a
phone digit) to treat as a budget.
"""
import re
from typing import Optional

_CUE_WORDS = (
    'presupuesto', 'presupueto',  # common typo
    'gastar', 'invertir', 'pagar', 'pago',
    'maximo', 'máximo', 'minimo', 'mínimo',
    'hasta', 'unos', 'unas', 'como',
    'dolares', 'dólares', 'usd', 'pesos', 'cop',
)

# "$300", "$ 300.000", "300$"
_CURRENCY_SIGN = re.compile(r'\$\s*([\d][\d.,]*)|([\d][\d.,]*)\s*\$')

# "35mil", "35 mil" -> 35 * 1000
_MIL_SUFFIX = re.compile(r'\b(\d+(?:[.,]\d+)?)\s*mil\b', re.IGNORECASE)

# A bare number near one of the cue words, e.g. "presupuesto de 300",
# "hasta 300000", "unos 300 dolares".
_CUE_NUMBER = re.compile(
    r'\b(?:' + '|'.join(re.escape(w) for w in _CUE_WORDS) + r')\b[^\d]{0,15}([\d][\d.,]*)',
    re.IGNORECASE,
)


def _parse_amount(raw: str) -> Optional[float]:
    """'300', '35.000', '1,200' -> float. Treats '.'/',' as thousand
    separators when they group in 3s (LatAm convention), else as decimals."""
    cleaned = raw.strip()
    if not cleaned:
        return None
    # Both separators present: last one is the decimal point.
    if '.' in cleaned and ',' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        # "1,200" (thousands) vs "12,5" (decimal) — 3-digit group after the
        # comma reads as thousands, anything else as a decimal comma.
        parts = cleaned.split(',')
        if len(parts[-1]) == 3:
            cleaned = cleaned.replace(',', '')
        else:
            cleaned = cleaned.replace(',', '.')
    elif '.' in cleaned:
        parts = cleaned.split('.')
        if len(parts[-1]) == 3:
            cleaned = cleaned.replace('.', '')
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


def extract_budget(text: str) -> Optional[dict]:
    """
    Returns {'max': float} if a budget figure is confidently found, else None.
    A single figure is treated as a ceiling ("presupuesto de $300" = up to
    $300), matching how session.py already consumes budget.get('max').
    """
    normalized = (text or '').strip()
    if not normalized:
        return None

    mil_match = _MIL_SUFFIX.search(normalized)
    if mil_match:
        amount = _parse_amount(mil_match.group(1))
        if amount:
            return {'max': amount * 1000}

    currency_match = _CURRENCY_SIGN.search(normalized)
    if currency_match:
        raw = currency_match.group(1) or currency_match.group(2)
        amount = _parse_amount(raw)
        if amount:
            return {'max': amount}

    cue_match = _CUE_NUMBER.search(normalized)
    if cue_match:
        amount = _parse_amount(cue_match.group(1))
        if amount:
            return {'max': amount}

    return None


def rank_by_budget(products: list, budget_max) -> list:
    """
    Soft budget preference: products within budget (plus 15% grace, since a
    customer's stated ceiling is rarely a hard cutoff) sort first, everything
    else follows in its original order. Never drops a product — an empty
    catalog response is worse than showing something slightly over budget.
    """
    if not products or not budget_max:
        return products
    try:
        ceiling = float(budget_max) * 1.15
    except (TypeError, ValueError):
        return products

    within, over = [], []
    for product in products:
        price = product.get('price_min')
        if price is not None and price <= ceiling:
            within.append(product)
        else:
            over.append(product)
    return within + over
