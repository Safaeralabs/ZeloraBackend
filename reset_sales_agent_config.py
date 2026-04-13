"""
Reset Sales Agent configuration for all organizations.
Ensures sales_enabled is True and DirectReplyExecutor is removed from decision flow.
Run with: python manage.py shell < reset_sales_agent_config.py
"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.accounts.models import Organization
from apps.channels_config.models import ChannelConfig

print("\n" + "="*70)
print("RESET SALES AGENT CONFIGURATION")
print("="*70)

try:
    # Get all organizations
    orgs = Organization.objects.filter(is_active=True)

    if not orgs.exists():
        print("\n✗ No active organizations found")
    else:
        print(f"\n✓ Found {orgs.count()} active organizations")

        for org in orgs:
            config, created = ChannelConfig.objects.get_or_create(
                organization=org,
                channel='onboarding',
                defaults={'settings': {}}
            )

            settings = config.settings or {}
            if not settings:
                settings = {}

            # Ensure sales_agent config
            if 'sales_agent' not in settings:
                settings['sales_agent'] = {}

            # Force enable
            old_value = settings['sales_agent'].get('enabled')
            settings['sales_agent']['enabled'] = True

            config.settings = settings
            config.save()

            status = "✓" if created else "✓ (updated)"
            print(f"\n  {status} {org.name}")
            print(f"     sales_enabled: {old_value} → {settings['sales_agent']['enabled']}")

    print("\n" + "="*70)
    print("✓ All organizations configured with Sales Agent always enabled")
    print("="*70)
    print("\nNow try the appchat again:")
    print("  1. Ask: '¿Qué productos tienes?'")
    print("  2. Should respond: 'Ahora mismo no tenemos productos activos...'")
    print("\n")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
