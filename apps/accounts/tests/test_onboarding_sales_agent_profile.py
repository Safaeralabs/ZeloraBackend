from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, User


class OnboardingSalesAgentProfileTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name='Onboarding Org',
            slug='onboarding-org',
            plan='pilot',
            country='Colombia',
        )
        self.user = User.objects.create_user(
            email='owner@example.com',
            password='secret123',
            nombre='Owner',
            rol='admin',
            organization=self.org,
        )
        self.client.force_authenticate(user=self.user)

    def test_patch_persists_sales_agent_runtime_and_legacy_fields(self):
        response = self.client.patch(
            '/api/auth/onboarding-profile/',
            {
                'org_profile': {
                    'brand': {
                        'tone_of_voice': 'cercano y directo',
                        'value_proposition': 'asesoria clara y cierre rapido',
                        'avoid_phrases': ['te aviso despues'],
                    },
                },
                'sales_agent': {
                    'enabled': False,
                    'name': 'Lia',
                    'persona': 'consultiva y agil',
                    'mission_statement': 'entender la necesidad y llevar a cierre',
                    'greeting_message': 'Hola, soy Lia.',
                    'response_language': 'es',
                    'max_response_length': 'brief',
                    'handoff_mode': 'balanceado',
                    'competitor_response': 'vuelve a diferenciales reales',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['sales_agent']['name'], 'Lia')
        self.assertFalse(response.data['sales_agent']['enabled'])
        self.assertEqual(response.data['sales_agent_profile']['greeting_message'], 'Hola, soy Lia.')
        self.assertEqual(response.data['sales_agent_name'], 'Lia')
        self.assertEqual(response.data['org_profile']['brand']['tone_of_voice'], 'cercano y directo')
        self.assertEqual(response.data['brand_profile']['value_proposition'], 'asesoria clara y cierre rapido')

        fresh = self.client.get('/api/auth/onboarding-profile/')
        self.assertEqual(fresh.status_code, status.HTTP_200_OK)
        self.assertEqual(fresh.data['sales_agent']['name'], 'Lia')
        self.assertEqual(fresh.data['sales_agent']['max_response_length'], 'brief')
        self.assertEqual(fresh.data['sales_agent_profile']['competitor_response'], 'vuelve a diferenciales reales')
