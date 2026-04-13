"""
Diagnostic script to check if an organization has products.
Run with: python manage.py shell < diagnose_products.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.accounts.models import Organization
from apps.ecommerce.models import Product

# UUID de la organización del usuario (del JSON que descargó)
ORG_ID = 'cdeccbe8-4c25-44da-86ba-efbe63bd570a'

try:
    org = Organization.objects.get(id=ORG_ID)
    print(f"\n✓ Organización encontrada: {org.name}")

    # Contar productos
    all_products = Product.objects.filter(organization=org)
    active_products = Product.objects.filter(
        organization=org,
        is_active=True,
        status='active'
    )

    print(f"\n  Total de productos: {all_products.count()}")
    print(f"  Productos activos (is_active=True, status='active'): {active_products.count()}")

    if active_products.exists():
        print(f"\n  Productos activos encontrados:")
        for p in active_products[:10]:
            print(f"    - {p.title} (ID: {p.id}, status: {p.status}, is_active: {p.is_active})")
            variants = p.variants.count()
            print(f"      Variantes: {variants}")
    else:
        print(f"\n  ✓ No hay productos activos (es lo esperado)")

        # Si no hay productos activos, verificar si hay inactivos
        if all_products.exists():
            print(f"\n  Hay {all_products.count()} productos inactivos/marcados como no activos")
            for p in all_products[:5]:
                print(f"    - {p.title} (status: {p.status}, is_active: {p.is_active})")

except Organization.DoesNotExist:
    print(f"✗ Organización con ID {ORG_ID} no encontrada")
except Exception as e:
    print(f"✗ Error: {e}")
