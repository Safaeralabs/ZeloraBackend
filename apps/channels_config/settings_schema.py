"""
settings_schema.py — Canonical normalizer for ChannelConfig['onboarding'].settings.

Supports two versions of the settings blob:
  v1 — flat/scattered structure (legacy, still stored in the DB for many orgs)
  v2 — clean hierarchical structure introduced in this refactor

Both are normalised to the same output dict so agents can read one shape.

Usage:
    from apps.channels_config.settings_schema import normalise_settings

    raw = config.settings or {}
    s = normalise_settings(raw)
    # Now read s['org_profile'], s['general_agent'], s['sales_agent'], s['ai_platform']
"""
from __future__ import annotations

from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Public entry-point
# ──────────────────────────────────────────────────────────────────────────────

def normalise_settings(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Accept either a v1 or v2 settings blob and return a fully-populated v2 dict.
    Never raises — returns safe defaults on any error.
    """
    if not isinstance(raw, dict):
        raw = {}
    version = raw.get('settings_version', 1)
    if version == 2:
        return _fill_defaults(_v2_passthrough(raw))
    return _fill_defaults(_v1_to_v2(raw))


# ──────────────────────────────────────────────────────────────────────────────
# V2 passthrough — already in canonical form, just ensure all keys exist
# ──────────────────────────────────────────────────────────────────────────────

def _v2_passthrough(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        'settings_version': 2,
        'org_profile': raw.get('org_profile') or {},
        'general_agent': raw.get('general_agent') or {},
        'sales_agent': raw.get('sales_agent') or {},
        'ai_platform': raw.get('ai_platform') or {},
    }


# ──────────────────────────────────────────────────────────────────────────────
# V1 → V2 migration
# ──────────────────────────────────────────────────────────────────────────────

def _v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    """Map the old flat/scattered v1 keys into the new hierarchical v2 shape."""
    # ── source sub-dicts ──────────────────────────────────────────────────────
    general_profile = raw.get('general_agent_profile') or {}
    sales_profile = raw.get('sales_agent_profile') or {}
    brand_cfg = sales_profile.get('brand_profile') or raw.get('brand_profile') or {}
    playbook_cfg = sales_profile.get('sales_playbook') or raw.get('sales_playbook') or {}
    rules_cfg = sales_profile.get('commerce_rules') or raw.get('commerce_rules') or {}
    buyer_model_cfg = sales_profile.get('buyer_model') or raw.get('buyer_model') or {}
    ai_prefs = raw.get('ai_preferences') or {}
    general_ai = ai_prefs.get('general_agent') or {}
    sales_ai = ai_prefs.get('sales_agent') or {}

    org_profile = {
        'what_you_sell': raw.get('what_you_sell') or '',
        'who_you_sell_to': raw.get('who_you_sell_to') or '',
        'payment_methods': raw.get('payment_methods') or [],
        'website': raw.get('website') or '',
        'industry': raw.get('industry') or '',
        'country': raw.get('country') or '',
        'brand': {
            'tone_of_voice': brand_cfg.get('tone_of_voice') or '',
            'formality_level': brand_cfg.get('formality_level') or '',
            'brand_personality': brand_cfg.get('brand_personality') or '',
            'value_proposition': brand_cfg.get('value_proposition') or '',
            'key_differentiators': brand_cfg.get('key_differentiators') or [],
            'preferred_closing_style': brand_cfg.get('preferred_closing_style') or '',
            'urgency_style': brand_cfg.get('urgency_style') or '',
            'recommended_phrases': brand_cfg.get('recommended_phrases') or [],
            'avoid_phrases': brand_cfg.get('avoid_phrases') or [],
            'customer_style_notes': brand_cfg.get('customer_style_notes') or '',
        },
    }

    general_agent = {
        'enabled': general_ai.get('enabled', True),
        'name': raw.get('general_agent_name') or '',
        'persona': general_profile.get('agent_persona') or '',
        'greeting_message': general_profile.get('greeting_message') or '',
        'mission_statement': general_profile.get('mission_statement') or '',
        'scope_notes': general_profile.get('scope_notes') or '',
        'allowed_topics': _coerce_str_list(general_profile.get('allowed_topics')),
        'blocked_topics': _coerce_str_list(general_profile.get('blocked_topics')),
        'handoff_to_sales_when': _coerce_str_list(general_profile.get('handoff_to_sales_when')),
        'handoff_to_human_when': _coerce_str_list(general_profile.get('handoff_to_human_when')),
        'out_of_scope_action': general_profile.get('out_of_scope_action') or 'reply',
        'response_language': general_profile.get('response_language') or general_ai.get('response_language') or 'auto',
        'max_response_length': general_ai.get('max_response_length') or 'brief',
        'handoff_mode': general_ai.get('handoff_mode') or 'balanceado',
        'model_name': general_ai.get('model_name') or 'gpt-4.1-nano',
        'max_kb_snippets': int(general_ai.get('max_kb_snippets') or 4),
    }

    sales_agent = {
        'enabled': sales_ai.get('enabled', True),
        'name': raw.get('sales_agent_name') or '',
        'persona': sales_profile.get('agent_persona') or raw.get('agent_persona') or '',
        'greeting_message': sales_profile.get('greeting_message') or raw.get('greeting_message') or '',
        'mission_statement': (
            sales_profile.get('mission_statement')
            or raw.get('mission')
            or raw.get('brand_mission')
            or ''
        ),
        'response_language': (
            sales_profile.get('response_language')
            or sales_ai.get('response_language')
            or raw.get('response_language')
            or 'auto'
        ),
        'max_response_length': sales_ai.get('max_response_length') or 'standard',
        'model_name': sales_ai.get('model_name') or 'gpt-4.1-nano',
        'autonomy_level': sales_ai.get('autonomy_level') or 'full',
        'handoff_mode': sales_ai.get('handoff_mode') or 'balanceado',
        'followup_mode': sales_ai.get('followup_mode') or 'suave',
        'max_followups': int(sales_ai.get('max_followups') or 3),
        'recommendation_depth': int(sales_ai.get('recommendation_depth') or 3),
        'competitor_response': (
            sales_profile.get('competitor_response')
            or playbook_cfg.get('competitor_response')
            or ''
        ),
        'shipping_policy': sales_profile.get('shipping_policy') or rules_cfg.get('shipping_policy') or '',
        'shipping_coverage': raw.get('shipping_coverage') or '',
        'shipping_avg_days': raw.get('shipping_avg_days') or '',
        'min_order_units': int(raw.get('min_order_units') or 1),
        'max_units_auto_approve': int(raw.get('max_units_auto_approve') or 10),
        'returns_window_days': int(raw.get('returns_window_days') or 15),
        'playbook': {
            'opening_style': playbook_cfg.get('opening_style') or '',
            'recommendation_style': playbook_cfg.get('recommendation_style') or '',
            'objection_style': playbook_cfg.get('objection_style') or '',
            'closing_style': playbook_cfg.get('closing_style') or '',
            'follow_up_style': playbook_cfg.get('follow_up_style') or '',
            'upsell_style': playbook_cfg.get('upsell_style') or '',
            'escalate_conditions': _coerce_str_list(playbook_cfg.get('escalate_conditions')),
        },
        'buyer_model': {
            'purchase_signals': _coerce_str_list(buyer_model_cfg.get('purchase_signals')),
            'bulk_buyer_signals': _coerce_str_list(buyer_model_cfg.get('bulk_buyer_signals')),
            'low_intent_signals': _coerce_str_list(buyer_model_cfg.get('low_intent_signals')),
            'common_objections': _coerce_str_list(buyer_model_cfg.get('common_objections')),
        },
        'commerce_rules': {
            'discount_policy': rules_cfg.get('discount_policy') or '',
            'negotiation_policy': rules_cfg.get('negotiation_policy') or '',
            'inventory_promise_rule': rules_cfg.get('inventory_promise_rule') or '',
            'delivery_promise_rule': rules_cfg.get('delivery_promise_rule') or '',
            'return_policy_summary': rules_cfg.get('return_policy_summary') or '',
            'forbidden_claims': _coerce_str_list(rules_cfg.get('forbidden_claims')),
            'forbidden_promises': _coerce_str_list(rules_cfg.get('forbidden_promises')),
        },
    }

    ai_platform = {
        'provider': ai_prefs.get('provider') or 'openai',
        'copilot_model': ai_prefs.get('copilot_model') or general_ai.get('model_name') or 'gpt-4.1-nano',
        'summary_model': ai_prefs.get('summary_model') or 'gpt-4.1-nano',
        'temperature': float(ai_prefs.get('temperature') or 0.45),
        'max_tokens': int(ai_prefs.get('max_tokens') or 220),
        'confidence_threshold': float(ai_prefs.get('confidence_threshold') or 0.65),
    }

    return {
        'settings_version': 2,
        'org_profile': org_profile,
        'general_agent': general_agent,
        'sales_agent': sales_agent,
        'ai_platform': ai_platform,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Default-filling — ensure every key exists after migration
# ──────────────────────────────────────────────────────────────────────────────

_ORG_PROFILE_DEFAULTS: dict[str, Any] = {
    'what_you_sell': '',
    'who_you_sell_to': '',
    'payment_methods': [],
    'website': '',
    'industry': '',
    'country': '',
    'brand': {},
}

_BRAND_DEFAULTS: dict[str, Any] = {
    'tone_of_voice': '',
    'formality_level': '',
    'brand_personality': '',
    'value_proposition': '',
    'key_differentiators': [],
    'preferred_closing_style': '',
    'urgency_style': '',
    'recommended_phrases': [],
    'avoid_phrases': [],
    'customer_style_notes': '',
}

_GENERAL_AGENT_DEFAULTS: dict[str, Any] = {
    'enabled': True,
    'name': '',
    'persona': '',
    'greeting_message': '',
    'mission_statement': '',
    'scope_notes': '',
    'allowed_topics': [],
    'blocked_topics': [],
    'handoff_to_sales_when': [],
    'handoff_to_human_when': [],
    'out_of_scope_action': '',
    'response_language': '',
    'max_response_length': '',
    'handoff_mode': '',
    'model_name': '',
    'max_kb_snippets': 4,
}

_SALES_AGENT_DEFAULTS: dict[str, Any] = {
    'enabled': True,
    'name': '',
    'persona': '',
    'greeting_message': '',
    'mission_statement': '',
    'response_language': '',
    'max_response_length': '',
    'model_name': '',
    'autonomy_level': '',
    'handoff_mode': '',
    'followup_mode': '',
    'max_followups': 3,
    'recommendation_depth': 3,
    'competitor_response': '',
    'shipping_policy': '',
    'shipping_coverage': '',
    'shipping_avg_days': '',
    'min_order_units': 1,
    'max_units_auto_approve': 10,
    'returns_window_days': 15,
    'playbook': {},
    'buyer_model': {},
    'commerce_rules': {},
}

_PLAYBOOK_DEFAULTS: dict[str, Any] = {
    'opening_style': '',
    'recommendation_style': '',
    'objection_style': '',
    'closing_style': '',
    'follow_up_style': '',
    'upsell_style': '',
    'escalate_conditions': [],
}

_BUYER_MODEL_DEFAULTS: dict[str, Any] = {
    'purchase_signals': [],
    'bulk_buyer_signals': [],
    'low_intent_signals': [],
    'common_objections': [],
}

_COMMERCE_RULES_DEFAULTS: dict[str, Any] = {
    'discount_policy': '',
    'negotiation_policy': '',
    'inventory_promise_rule': '',
    'delivery_promise_rule': '',
    'return_policy_summary': '',
    'forbidden_claims': [],
    'forbidden_promises': [],
}

_AI_PLATFORM_DEFAULTS: dict[str, Any] = {
    'provider': 'openai',
    'copilot_model': 'gpt-4.1-nano',
    'summary_model': 'gpt-4.1-nano',
    'temperature': 0.45,
    'max_tokens': 220,
    'confidence_threshold': 0.65,
}


def _fill_defaults(s: dict[str, Any]) -> dict[str, Any]:
    op = {**_ORG_PROFILE_DEFAULTS, **(s.get('org_profile') or {})}
    op['brand'] = {**_BRAND_DEFAULTS, **(op.get('brand') or {})}

    ga = {**_GENERAL_AGENT_DEFAULTS, **(s.get('general_agent') or {})}
    for key in ('allowed_topics', 'blocked_topics', 'handoff_to_sales_when', 'handoff_to_human_when'):
        if not isinstance(ga.get(key), list):
            ga[key] = []

    sa = {**_SALES_AGENT_DEFAULTS, **(s.get('sales_agent') or {})}
    sa['playbook'] = {**_PLAYBOOK_DEFAULTS, **(sa.get('playbook') or {})}
    sa['buyer_model'] = {**_BUYER_MODEL_DEFAULTS, **(sa.get('buyer_model') or {})}
    sa['commerce_rules'] = {**_COMMERCE_RULES_DEFAULTS, **(sa.get('commerce_rules') or {})}
    for key in ('escalate_conditions',):
        if not isinstance(sa['playbook'].get(key), list):
            sa['playbook'][key] = []
    for key in ('purchase_signals', 'bulk_buyer_signals', 'low_intent_signals', 'common_objections'):
        if not isinstance(sa['buyer_model'].get(key), list):
            sa['buyer_model'][key] = []
    for key in ('forbidden_claims', 'forbidden_promises'):
        if not isinstance(sa['commerce_rules'].get(key), list):
            sa['commerce_rules'][key] = []

    ap = {**_AI_PLATFORM_DEFAULTS, **(s.get('ai_platform') or {})}

    return {
        'settings_version': 2,
        'org_profile': op,
        'general_agent': ga,
        'sales_agent': sa,
        'ai_platform': ap,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _coerce_str_list(value: Any) -> list[str]:
    """Return a list of non-empty strings from any iterable, ignoring non-strings."""
    if not isinstance(value, (list, tuple)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
