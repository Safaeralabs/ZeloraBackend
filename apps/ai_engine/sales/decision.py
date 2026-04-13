"""
Decision Engine — Business logic for what action to take.
Pure Python, no LLM.
"""
from typing import TypedDict, Optional
from dataclasses import dataclass, field


class AgentAction(TypedDict, total=False):
    """Action to execute (not all fields required)."""
    fetch_products: bool
    fetch_kb: list[str]  # purposes: faq | business | sales_scripts | policy
    fetch_promotions: bool
    requires_handoff: bool
    checkout_step: Optional[int]
    response_strategy: str  # discover | recommend | close | inform | clarify | redirect
    intent: Optional[str]


class DecisionEngine:
    """
    Pure decision logic: situation → action.
    Decides what context to fetch and what strategy to use.
    """

    # Decision table: (situation, stage) → action
    DECISION_TABLE = {
        ('discovery', 'discovery'): {
            'fetch_products': True,
            'fetch_kb': ['business'],
            'fetch_promotions': False,
            'response_strategy': 'discover',
        },
        ('confused_customer', 'discovery'): {
            'fetch_products': True,  # search with accumulated attributes
            'fetch_kb': ['faq'],
            'fetch_promotions': False,
            'response_strategy': 'clarify',
        },
        ('indecisive_customer', 'discovery'): {
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': False,
            'response_strategy': 'recommend',
        },
        ('comparing_customer', 'discovery'): {
            'fetch_products': True,  # with alternatives via ProductRelation
            'fetch_kb': [],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('price_sensitive_customer', 'discovery'): {
            'fetch_products': False,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('specific_product_customer', 'discovery'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': True,
            'response_strategy': 'inform',
        },
        ('ready_to_buy_customer', 'discovery'): {
            'fetch_products': False,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': False,
            'checkout_step': 1,
            'response_strategy': 'close',
        },
        ('ready_to_buy_customer', 'considering'): {
            'fetch_products': False,
            'fetch_kb': [],
            'fetch_promotions': False,
            'checkout_step': 1,
            'response_strategy': 'close',
        },
        ('urgent_customer', 'discovery'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': True,
            'response_strategy': 'close',
        },
        ('expansion_opportunity', 'considering'): {
            'fetch_products': True,  # look for upsell/bundle relations
            'fetch_kb': [],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('gift_customer', 'discovery'): {
            'fetch_products': True,  # filter by occasion=gift
            'fetch_kb': ['business'],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('objection_customer', 'considering'): {
            'fetch_products': False,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': False,
            'response_strategy': 'clarify',
        },
        ('objection_customer', 'checkout'): {
            'fetch_products': False,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'close',
        },
        ('post_sale', 'considering'): {
            'fetch_products': False,
            'fetch_kb': ['policy', 'faq'],
            'fetch_promotions': False,
            'response_strategy': 'inform',
        },
        ('logistics_customer', 'considering'): {
            'fetch_products': False,
            'fetch_kb': ['policy'],
            'fetch_promotions': False,
            'response_strategy': 'inform',
        },
        ('administrative_customer', 'discovery'): {
            'fetch_products': False,
            'fetch_kb': ['policy', 'faq'],
            'fetch_promotions': False,
            'response_strategy': 'inform',
        },
        ('changing_mind_customer', 'considering'): {
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('inactive_customer', 'discovery'): {
            'fetch_products': True,
            'fetch_kb': ['business'],
            'fetch_promotions': True,
            'response_strategy': 'discover',
        },
        ('out_of_catalog', 'discovery'): {
            'fetch_products': True,  # search alternatives
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'redirect',
        },
        ('off_topic', 'discovery'): {
            'fetch_products': False,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'redirect',
        },
        ('prompt_injection', 'discovery'): {
            'fetch_products': False,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'ignore',  # flujo normal, no comment
        },
        ('checkout', 'checkout'): {
            'fetch_products': False,
            'fetch_kb': ['policy'],
            'fetch_promotions': False,
            'checkout_step': 2,  # advance step
            'response_strategy': 'close',
        },
    }

    @staticmethod
    def decide(situation: str, stage: str, conversation_intent: Optional[str] = None) -> AgentAction:
        """
        Decide what to do based on situation and stage.

        Args:
            situation: Customer situation (one of the 20 defined)
            stage: Current session stage
            conversation_intent: Optional intent from router

        Returns:
            AgentAction dict with flags and strategy
        """
        # Look up in decision table
        key = (situation, stage)
        action = DecisionEngine.DECISION_TABLE.get(key)

        if not action:
            # Default: safe fallback
            action = {
                'fetch_products': False,
                'fetch_kb': ['faq'],
                'fetch_promotions': False,
                'response_strategy': 'clarify',
            }

        # Copy to allow mutation
        action = dict(action)

        # Add intent if provided
        if conversation_intent:
            action['intent'] = conversation_intent

        # Handoff logic: some situations may escalate
        if situation in ('prompt_injection', 'off_topic'):
            # Don't escalate these, just handle locally
            action['requires_handoff'] = False
        # (add more escalation logic as needed)

        return action
