"""
Flow trigger matching — finds the right DB Flow for an incoming message.

Priority order (highest to lowest):
  1. keyword  — any configured keyword found in message text
  2. channel  — flow configured to activate on a specific channel entry

Intent-based triggers are matched externally by the AI router and passed in
via the router_decision parameter in SalesAgent.run(). This module handles
passive matching that doesn't require an AI call.
"""
from __future__ import annotations


def find_matching_flow(*, organization, message_text: str, channel: str) -> 'Flow | None':
    """
    Returns the highest-priority matching active Flow for this message/channel.
    Returns None if no flow matches.
    """
    from .models import Flow
    from .serializers import split_flow_nodes

    active_flows = list(
        Flow.objects.filter(organization=organization, is_active=True).order_by('-updated_at')
    )
    if not active_flows:
        return None

    text = (message_text or '').lower().strip()

    keyword_matches: list[Flow] = []
    channel_matches: list[Flow] = []

    for flow in active_flows:
        _, router_config, canales = split_flow_nodes(flow.nodes, flow.channel)
        trigger_type = router_config.get('triggerType', 'keyword')

        # Channel filter: skip if this flow doesn't apply to the current channel
        if canales and channel and channel not in canales:
            continue

        if trigger_type == 'keyword':
            keywords = [kw.strip().lower() for kw in (router_config.get('keywords') or []) if kw.strip()]
            if any(kw in text for kw in keywords):
                keyword_matches.append(flow)

        elif trigger_type == 'channel':
            # Activates on any first message in the specified channel(s)
            channel_matches.append(flow)

    if keyword_matches:
        return keyword_matches[0]
    if channel_matches:
        return channel_matches[0]
    return None


def find_flow_by_intent(*, organization, intent: str, channel: str) -> 'Flow | None':
    """
    Find a flow configured for a specific intent (used by the AI router).
    """
    from .models import Flow
    from .serializers import split_flow_nodes

    active_flows = list(
        Flow.objects.filter(organization=organization, is_active=True, trigger=intent)
    )
    for flow in active_flows:
        _, router_config, canales = split_flow_nodes(flow.nodes, flow.channel)
        if canales and channel and channel not in canales:
            continue
        if router_config.get('triggerType') == 'intent' and router_config.get('intent') == intent:
            return flow
    return None
