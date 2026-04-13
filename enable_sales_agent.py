"""
Enable Sales Agent for an organization.
Run with: python manage.py shell < enable_sales_agent.py
"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.accounts.models import Organization
from apps.channels_config.models import ChannelConfig

ORG_ID = 'cdeccbe8-4c25-44da-86ba-efbe63bd570a'

try:
    org = Organization.objects.get(id=ORG_ID)
    print(f"\n✓ Organización encontrada: {org.name}")

    # Get or create the onboarding channel config
    config, created = ChannelConfig.objects.get_or_create(
        organization=org,
        channel='onboarding',
        defaults={'settings': {}}
    )

    # Normalize settings
    settings = config.settings or {}
    if not settings:
        settings = {}

    # Ensure sales_agent config exists
    if 'sales_agent' not in settings:
        settings['sales_agent'] = {}

    # Enable the sales agent
    current_value = settings['sales_agent'].get('enabled', True)
    settings['sales_agent']['enabled'] = True

    config.settings = settings
    config.save()

    print(f"\n✓ Sales Agent habilitado para {org.name}")
    print(f"  Valor anterior: {current_value}")
    print(f"  Valor nuevo: {settings['sales_agent']['enabled']}")
    print(f"\nAhora intenta nuevamente en el appchat:")
    print(f"  1. Pregunta: '¿Qué productos tienes?'")
    print(f"  2. El bot debería responder con el mensaje de catálogo vacío")

except Organization.DoesNotExist:
    print(f"✗ Organización con ID {ORG_ID} no encontrada")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
