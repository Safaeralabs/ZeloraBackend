from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Organization, User


class OnboardingPaymentMethodsGatingTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name='Payments Org',
            slug='payments-org',
            plan='pilot',
            country='Colombia',
        )
        self.user = User.objects.create_user(
            email='payments-owner@example.com',
            password='secret123',
            nombre='Owner',
            rol='admin',
            organization=self.org,
        )
        self.client.force_authenticate(user=self.user)

    def test_activating_nequi_without_details_is_rejected(self):
        response = self.client.patch(
            '/api/auth/onboarding-profile/',
            {'payment_methods': ['nequi']},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('payment_methods', response.data['detail'])
        self.assertIn('nequi', str(response.data['detail']['payment_methods']))

        fresh = self.client.get('/api/auth/onboarding-profile/')
        self.assertEqual(fresh.data.get('payment_methods'), [])

    def test_activating_nequi_with_details_in_same_request_succeeds(self):
        response = self.client.patch(
            '/api/auth/onboarding-profile/',
            {
                'payment_methods': ['nequi'],
                'payment_settings': {
                    'nequi_number': '3001234567',
                    'nequi_holder': 'Payments Org SAS',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['payment_methods'], ['nequi'])
        self.assertEqual(response.data['activation_tasks']['payment_status'], 'completed')

    def test_activating_bank_transfer_reuses_previously_saved_details(self):
        # First request only saves the account details, without enabling the method.
        setup_response = self.client.patch(
            '/api/auth/onboarding-profile/',
            {
                'payment_settings': {
                    'bank_name': 'Bancolombia',
                    'account_number': '12345678901',
                    'account_holder': 'Payments Org SAS',
                },
            },
            format='json',
        )
        self.assertEqual(setup_response.status_code, status.HTTP_200_OK)

        # Second request activates the method without resending payment_settings.
        activate_response = self.client.patch(
            '/api/auth/onboarding-profile/',
            {'payment_methods': ['transferencia bancaria']},
            format='json',
        )

        self.assertEqual(activate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(activate_response.data['payment_methods'], ['transferencia bancaria'])

    def test_activating_cash_missing_instructions_is_rejected(self):
        response = self.client.patch(
            '/api/auth/onboarding-profile/',
            {
                'payment_methods': ['efectivo'],
                'payment_settings': {'cash_instructions': '   '},
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('efectivo', str(response.data['detail']['payment_methods']))

    def test_custom_payment_method_without_known_schema_passes_through(self):
        response = self.client.patch(
            '/api/auth/onboarding-profile/',
            {'payment_methods': ['pago contra entrega personalizado']},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['payment_methods'], ['pago contra entrega personalizado'])

    def test_no_payment_methods_leaves_activation_task_pending(self):
        response = self.client.get('/api/auth/onboarding-profile/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['activation_tasks']['payment_status'], 'pending')
