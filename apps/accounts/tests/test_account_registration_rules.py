from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Organization


User = get_user_model()


class AccountRegistrationRulesTests(APITestCase):
    def test_signup_availability_reports_company_slug_without_leaking_details(self):
        Organization.objects.create(
            name='Valdiri Move',
            slug='valdiri-move',
            plan='pilot',
            country='Colombia',
        )

        response = self.client.post(
            '/api/auth/signup-availability/',
            {'company': 'Valdiri Move'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['company_slug'], 'valdiri-move')
        self.assertFalse(response.data['company_available'])

    def test_public_signup_rejects_taken_company_name(self):
        Organization.objects.create(
            name='Valdiri Move',
            slug='valdiri-move',
            plan='pilot',
            country='Colombia',
        )

        response = self.client.post(
            '/api/auth/signup/',
            {
                'name': 'Laura',
                'company': 'Valdiri Move',
                'email': 'laura@example.com',
                'password': 'Admin1234!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('brand name', response.data['error'])

    def test_public_signup_rejects_non_admin_role(self):
        response = self.client.post(
            '/api/auth/signup/',
            {
                'name': 'Laura',
                'company': 'Nueva Empresa',
                'email': 'laura@example.com',
                'password': 'Admin1234!',
                'role': 'asesor',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Public signup only creates the initial admin account', response.data['error'])

    def test_supervisor_cannot_create_agent_accounts(self):
        organization = Organization.objects.create(
            name='Comfaguajira',
            slug='comfaguajira-authz',
            plan='pilot',
            country='Colombia',
        )
        admin = User.objects.create_user(
            email='admin@test.com',
            password='Admin1234!',
            nombre='Admin',
            rol='admin',
            organization=organization,
            is_staff=True,
        )
        supervisor = User.objects.create_user(
            email='supervisor@test.com',
            password='Admin1234!',
            nombre='Supervisor',
            rol='supervisor',
            organization=organization,
        )

        login = self.client.post(
            '/api/auth/login/',
            {'email': supervisor.email, 'password': 'Admin1234!'},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = self.client.post(
            '/api/auth/agents/',
            {
                'email': 'asesor@test.com',
                'nombre': 'Nuevo Asesor',
                'password': 'Admin1234!',
                'rol': 'asesor',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(email='asesor@test.com').exists())
        self.assertTrue(User.objects.filter(id=admin.id).exists())
