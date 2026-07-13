from unittest.mock import patch

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, User


class TonePreviewViewTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name='Tone Preview Org',
            slug='tone-preview-org',
            plan='pilot',
            country='Colombia',
        )
        self.user = User.objects.create_user(
            email='tone-preview@example.com',
            password='secret123',
            nombre='Owner',
            rol='admin',
            organization=self.org,
        )
        self.client.force_authenticate(user=self.user)

    def test_returns_fallback_when_ai_disabled(self):
        response = self.client.post(
            '/api/ai/tone-preview/',
            {'formality': 'casual', 'what_you_sell': 'leggings', 'who_you_sell_to': 'mujeres jovenes'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['source'], 'fallback')
        self.assertIn('leggings', response.data['example'])

    def test_invalid_formality_falls_back_to_balanced(self):
        response = self.client.post(
            '/api/ai/tone-preview/',
            {'formality': 'not-a-real-level'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('asistente virtual', response.data['example'])

    @override_settings(OPENAI_API_KEY='test-key', ENABLE_REAL_AI=True)
    def test_uses_ai_response_when_available(self):
        with patch('openai.OpenAI') as mock_openai:
            mock_client = mock_openai.return_value
            mock_client.chat.completions.create.return_value.choices = [
                type('Choice', (), {'message': type('Msg', (), {'content': 'Hola, tenemos justo lo que buscas.'})()})()
            ]
            response = self.client.post(
                '/api/ai/tone-preview/',
                {'formality': 'formal', 'what_you_sell': 'ropa', 'who_you_sell_to': 'ejecutivos'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['source'], 'ai')
        self.assertEqual(response.data['example'], 'Hola, tenemos justo lo que buscas.')

    @override_settings(OPENAI_API_KEY='test-key', ENABLE_REAL_AI=True)
    def test_ai_failure_falls_back_gracefully(self):
        with patch('openai.OpenAI', side_effect=RuntimeError('boom')):
            response = self.client.post(
                '/api/ai/tone-preview/',
                {'formality': 'casual'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['source'], 'fallback')
