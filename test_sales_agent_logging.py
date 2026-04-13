#!/usr/bin/env python
"""
Test script to exercise the sales agent and observe logging output.
Usage:
    cd backendv2
    python test_sales_agent_logging.py
"""
import django
import os
import sys
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()

from apps.ai_engine.sales_agent import SalesAgent
from apps.organizations.models import Organization

def print_logs_header():
    print("\n" + "="*80)
    print("SALES AGENT LOGGING TEST")
    print("="*80)
    print("\nWatching logs in: backendv2/logs/vendly.json.log")
    print("Tip: In another terminal, run:")
    print("  tail -f backendv2/logs/vendly.json.log | jq .")
    print("\n" + "="*80 + "\n")

def get_first_org():
    """Get first organization or return None."""
    return Organization.objects.first()

def run_test(message, description):
    """Run a test message through the agent."""
    org = get_first_org()
    if not org:
        print("❌ No organizations found. Create one first.")
        return False

    print(f"\n{'─'*60}")
    print(f"📝 Test: {description}")
    print(f"💬 Message: {message}")
    print(f"{'─'*60}\n")

    agent = SalesAgent()
    result = agent.run(
        message_text=message,
        conversation=None,
        organization=org,
    )

    print(f"✅ Result:")
    print(f"   Stage: {result.stage}")
    print(f"   Archetype: {result.buyer_profile.archetype}")
    print(f"   Objection: {result.buyer_profile.objection}")
    print(f"   Decision: {result.decision}")
    print(f"   Reply: {result.reply_text[:100]}...")
    print()

    return True

def main():
    print_logs_header()

    # Test 1: Gift buyer with budget
    run_test(
        "Quiero un regalo para mi novia, tengo presupuesto hasta $80.000",
        "Gift buyer with budget extraction (P.1, P.5)"
    )

    # Test 2: Deal hunter (comparative shopper)
    run_test(
        "Quiero comparar opciones, ¿cuál es la más barata?",
        "Deal hunter buyer archetype (P.5)"
    )

    # Test 3: Impulse buyer
    run_test(
        "Quiero comprar algo ahora mismo, lo necesito hoy",
        "Impulse buyer (immediate + direct style)"
    )

    # Test 4: High intent to buy
    run_test(
        "¿Cuál es el precio de eso? ¿Tienen disponibilidad? ¿Cómo pago?",
        "Intent to buy stage with close signals"
    )

    # Test 5: Price objection
    run_test(
        "Me interesa pero es muy caro, ¿hay descuento?",
        "Price objection handling (P.4 negotiation logic)"
    )

    # Test 6: Following up
    run_test(
        "Lo veo, lo pienso y te aviso",
        "Follow-up needed stage"
    )

    # Test 7: Researcher buyer
    run_test(
        "¿Cuál es la diferencia entre estas opciones? ¿Cuál me recomendas?",
        "Researcher buyer (comparative + quality focused)"
    )

    print("\n" + "="*80)
    print("✅ All tests completed!")
    print("="*80)
    print("\nCheck the logs file for detailed event tracing:")
    print("  cat backendv2/logs/vendly.json.log | jq .")
    print("\nFilter by event type:")
    print("  cat backendv2/logs/vendly.json.log | jq 'select(.event==\"openai_api_response\")'")
    print("\nSee SALES_AGENT_LOGGING_GUIDE.md for more info.")
    print()

if __name__ == '__main__':
    main()
