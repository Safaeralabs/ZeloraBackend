"""
Test para verificar que el guardia de catálogo vacío funciona correctamente.
Este test verifica que cuando una organización no tiene productos,
el sistema muestre el mensaje apropiado en lugar de inventar productos.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.ai_engine.sales_agent import SalesAgent
from apps.accounts.models import Organization, Contact
from apps.conversations.models import Conversation
from django.utils import timezone


def test_empty_catalog_guard():
    """
    Test: una organización nueva sin productos debe retornar el mensaje de catálogo vacío.
    """
    # Crear una organización de prueba sin productos
    org, _ = Organization.objects.get_or_create(
        slug='test-empty-catalog',
        defaults={
            'name': 'Test Empty Catalog',
            'is_active': True,
            'industry': 'Testing',
            'country': 'Colombia',
        }
    )

    # Crear un contacto de prueba
    contact, _ = Contact.objects.get_or_create(
        organization=org,
        email='test@example.com',
        defaults={
            'nombre': 'Test User',
            'tipo': 'cliente',
        }
    )

    # Crear una conversación de prueba
    conversation, _ = Conversation.objects.get_or_create(
        organization=org,
        external_id='test-session-123',
        defaults={
            'contact': contact,
            'canal': 'app',
            'estado': 'nuevo',
            'metadata': {},
        }
    )

    # Ejecutar el sales agent con una pregunta sobre productos
    agent = SalesAgent()
    result = agent.run(
        message_text='¿Qué productos tienes?',
        conversation=conversation,
        organization=org,
    )

    # Verificar que retorna el mensaje de catálogo vacío
    print(f"\n✓ Test: Empty Catalog Guard")
    print(f"  Message: '¿Qué productos tienes?'")
    print(f"  Organization: {org.name} (no products)")
    print(f"  Response: {result.reply_text}")

    # Verificar que el mensaje contiene el texto esperado
    expected_phrases = [
        'no tenemos productos',
        'activos cargados',
        'no puedo recomendarte opciones reales',
    ]

    has_expected = any(phrase.lower() in result.reply_text.lower() for phrase in expected_phrases)

    if has_expected:
        print(f"  ✓ Correct: Message indicates no products available")
        return True
    else:
        print(f"  ✗ Error: Message should indicate no products")
        print(f"    Expected phrases: {expected_phrases}")
        return False


if __name__ == '__main__':
    success = test_empty_catalog_guard()
    exit(0 if success else 1)
