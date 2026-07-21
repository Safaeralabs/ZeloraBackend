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


#: Canonical situations (must match SituationDetector's 20) and active stages.
SITUATIONS = (
    'discovery',
    'confused_customer',
    'indecisive_customer',
    'comparing_customer',
    'price_sensitive_customer',
    'specific_product_customer',
    'ready_to_buy_customer',
    'urgent_customer',
    'expansion_opportunity',
    'gift_customer',
    'objection_customer',
    'post_sale',
    'logistics_customer',
    'administrative_customer',
    'changing_mind_customer',
    'inactive_customer',
    'out_of_catalog',
    'off_topic',
    'prompt_injection',
    'checkout',
)
ACTIVE_STAGES = ('discovery', 'considering', 'checkout')


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
        ('price_sensitive_customer', 'considering'): {
            # "Es que esta caro" with a product already on the table is a price
            # objection at the closing moment, not a browsing signal: rebut with
            # value/promo and push toward close (same reasoning as
            # objection_customer/considering below).
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'close',
        },
        ('price_sensitive_customer', 'checkout'): {
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'close',
        },
        ('specific_product_customer', 'discovery'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': True,
            'response_strategy': 'inform',
        },
        ('specific_product_customer', 'considering'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': True,
            'response_strategy': 'inform',
        },
        ('specific_product_customer', 'checkout'): {
            'fetch_products': True,
            'fetch_kb': ['policy'],
            'fetch_promotions': True,
            'response_strategy': 'close',
        },
        ('ready_to_buy_customer', 'discovery'): {
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': False,
            'checkout_step': 1,
            'response_strategy': 'close',
        },
        ('ready_to_buy_customer', 'considering'): {
            'fetch_products': True,
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
        ('gift_customer', 'considering'): {
            'fetch_products': True,
            'fetch_kb': ['business'],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('gift_customer', 'checkout'): {
            'fetch_products': True,
            'fetch_kb': ['policy'],
            'fetch_promotions': True,
            'response_strategy': 'close',
        },
        ('objection_customer', 'discovery'): {
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'clarify',
        },
        ('objection_customer', 'considering'): {
            # Critical closing moment: product chosen but customer doubts.
            # Rebut with concrete value + promo and push toward close,
            # never stall with a clarifying question.
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'close',
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
        ('comparing_customer', 'considering'): {
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
        # ── Missing-cell completion: every (situation, stage) is explicit so no
        # sales conversation ever falls into the generic clarify fallback. ──────
        ('discovery', 'considering'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'discover',
        },
        ('discovery', 'checkout'): {
            # Exploring again from checkout; policy guard moves stage back.
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'recommend',
        },
        ('confused_customer', 'considering'): {
            'fetch_products': True,
            'fetch_kb': ['faq'],
            'fetch_promotions': False,
            'response_strategy': 'clarify',
        },
        ('confused_customer', 'checkout'): {
            # Confusion about the process mid-checkout: explain, don't interrogate.
            'fetch_products': False,
            'fetch_kb': ['policy', 'faq'],
            'fetch_promotions': False,
            'response_strategy': 'inform',
        },
        ('indecisive_customer', 'considering'): {
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('indecisive_customer', 'checkout'): {
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'close',
        },
        ('comparing_customer', 'checkout'): {
            # Policy guard will step back to considering while keeping the cart.
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('ready_to_buy_customer', 'checkout'): {
            # Customer ready and already in checkout: advance, never stall.
            'fetch_products': True,
            'fetch_kb': ['policy'],
            'fetch_promotions': False,
            'checkout_step': 2,
            'response_strategy': 'close',
        },
        ('urgent_customer', 'considering'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': True,
            'checkout_step': 1,
            'response_strategy': 'close',
        },
        ('urgent_customer', 'checkout'): {
            'fetch_products': True,
            'fetch_kb': ['policy'],
            'fetch_promotions': False,
            'checkout_step': 2,
            'response_strategy': 'close',
        },
        ('expansion_opportunity', 'discovery'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('expansion_opportunity', 'checkout'): {
            # Upsell mention is fine, but the priority is finishing the order.
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': True,
            'response_strategy': 'close',
        },
        ('post_sale', 'discovery'): {
            'fetch_products': False,
            'fetch_kb': ['policy', 'faq'],
            'fetch_promotions': False,
            'response_strategy': 'inform',
        },
        ('post_sale', 'checkout'): {
            # decide() adds requires_handoff for this combination.
            'fetch_products': False,
            'fetch_kb': ['policy'],
            'fetch_promotions': False,
            'response_strategy': 'inform',
        },
        ('logistics_customer', 'discovery'): {
            'fetch_products': False,
            'fetch_kb': ['policy'],
            'fetch_promotions': False,
            'response_strategy': 'inform',
        },
        ('logistics_customer', 'checkout'): {
            # Answer the shipping question and keep the checkout moving.
            'fetch_products': False,
            'fetch_kb': ['policy'],
            'fetch_promotions': False,
            'response_strategy': 'close',
        },
        ('administrative_customer', 'considering'): {
            'fetch_products': False,
            'fetch_kb': ['policy', 'faq'],
            'fetch_promotions': False,
            'response_strategy': 'inform',
        },
        ('administrative_customer', 'checkout'): {
            # decide() adds requires_handoff (payment) for this combination.
            'fetch_products': False,
            'fetch_kb': ['policy'],
            'fetch_promotions': False,
            'response_strategy': 'inform',
        },
        ('changing_mind_customer', 'discovery'): {
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('changing_mind_customer', 'checkout'): {
            # Hesitation mid-checkout: rescue the sale with value, no pressure.
            'fetch_products': True,
            'fetch_kb': ['sales_scripts'],
            'fetch_promotions': True,
            'response_strategy': 'close',
        },
        ('inactive_customer', 'considering'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': True,
            'response_strategy': 'recommend',
        },
        ('inactive_customer', 'checkout'): {
            'fetch_products': True,
            'fetch_kb': ['policy'],
            'fetch_promotions': True,
            'response_strategy': 'close',
        },
        ('out_of_catalog', 'considering'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'redirect',
        },
        ('out_of_catalog', 'checkout'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'redirect',
        },
        ('off_topic', 'considering'): {
            'fetch_products': False,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'redirect',
        },
        ('off_topic', 'checkout'): {
            'fetch_products': False,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'redirect',
        },
        ('prompt_injection', 'considering'): {
            'fetch_products': False,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'ignore',
        },
        ('prompt_injection', 'checkout'): {
            'fetch_products': False,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'ignore',
        },
        ('checkout', 'discovery'): {
            # Payment/confirmation language before choosing a product: there is
            # nothing to close yet, so help them pick one. No checkout_step here —
            # ResponseContractEnforcer treats checkout_step as "in checkout" and
            # would override the empty-cart guidance with payment contracts.
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': False,
            'response_strategy': 'clarify',
        },
        ('checkout', 'considering'): {
            'fetch_products': True,
            'fetch_kb': [],
            'fetch_promotions': False,
            'checkout_step': 1,
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
            if stage == 'checkout':
                # Never stall an active checkout with a clarifying question:
                # keep pushing toward the close (cart safety is enforced later
                # by SalesPolicyEngine, which strips checkout_step without cart).
                action = {
                    'fetch_products': True,
                    'fetch_kb': ['policy'],
                    'fetch_promotions': False,
                    'response_strategy': 'close',
                }
            else:
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
        if situation == 'administrative_customer' and stage == 'checkout':
            action['requires_handoff'] = True
            action['handoff_reason'] = 'payment'
        elif situation == 'post_sale' and stage in ('considering', 'checkout'):
            action['requires_handoff'] = True
            action['handoff_reason'] = 'complexity'
        if situation in ('prompt_injection', 'off_topic'):
            # Don't escalate these, just handle locally
            action['requires_handoff'] = False
        # (add more escalation logic as needed)

        return action
