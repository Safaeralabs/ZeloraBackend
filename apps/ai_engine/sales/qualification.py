"""
Qualification guard for unbounded catalog requests — "mandame foto y precio
de cada una", "quiero ver todos los productos".

Real transcript that motivated this (rosado_joyeria, IG-sourced WhatsApp lead,
analyzed 2026-07-19): the customer asked for a photo and price of every item;
the human seller neither dumped the catalog nor refused — they asked budget,
then recipient, then narrowed to a category the customer could actually
choose from. This module is the deterministic version of that first move:
detect the unbounded ask and, if the session has no budget yet and no product
already selected, ask ONE qualifying question instead of running a noisy
catalog search that would either flood the customer or return nothing.

Pure Python, no LLM — mirrors DecisionEngine's design (system decides WHAT to
do, the LLM only decides HOW to phrase it).
"""
from .text_normalize import normalize_for_matching

UNBOUNDED_PATTERNS = (
    'de cada una', 'de cada uno', 'de cada cosa', 'de cada producto',
    'de cada prenda', 'de cada item', 'de cada articulo',
    'todo lo que tienen', 'todo lo que tienes', 'todo lo que manejan',
    'todos los productos', 'toda la tienda', 'todo el catalogo',
    'fotos de todo', 'foto de todo', 'precio de todo', 'precios de todo',
    'manda todo', 'mandame todo', 'enviame todo', 'envia todo',
    'de todo un poco', 'que tienen en general', 'que tienes en general',
    'todo lo que hay',
)


def is_unbounded_catalog_request(text: str) -> bool:
    normalized = normalize_for_matching(text).strip().lower()
    if not normalized:
        return False
    return any(pattern in normalized for pattern in UNBOUNDED_PATTERNS)


def needs_budget_qualification(*, message_text: str, session) -> bool:
    """
    True when the message is an unbounded catalog request AND the session
    doesn't yet have enough signal (a budget, or a product already on the
    table) to answer it narrowly.
    """
    if not is_unbounded_catalog_request(message_text):
        return False
    if getattr(session, 'selected_products', None):
        return False
    if getattr(session, 'budget_min', None) or getattr(session, 'budget_max', None):
        return False
    return True


def apply_budget_qualification(action: dict) -> dict:
    """Override a DecisionEngine action so the turn asks for budget instead
    of running a product search that would either flood the customer with
    the whole catalog or return a noisy/empty result."""
    normalized = dict(action or {})
    normalized['fetch_products'] = False
    normalized['fetch_promotions'] = False
    normalized['response_strategy'] = 'clarify'
    normalized['qualify_question'] = 'budget'
    return normalized
