from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.email_utils import send_password_reset_email
from apps.accounts.models import Organization, PasswordResetToken

User = get_user_model()


class PasswordResetFlowTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name='FitZone',
            slug='fitzone',
            plan='pilot',
            country='Colombia',
        )
        self.user = User.objects.create_user(
            email='owner@fitzone.com',
            password='OldPass1234',
            nombre='Laura',
            rol='admin',
            organization=self.org,
        )
        self.user.email_verified = True
        self.user.save(update_fields=['email_verified'])

    def test_send_password_reset_email_creates_token_and_sends_mail(self):
        """Unit-level: exercises the email utility directly (not through a view),
        so it isn't affected by Django's request/response template rendering."""
        token_obj = send_password_reset_email(self.user)

        self.assertEqual(PasswordResetToken.objects.filter(user=self.user).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(f'reset-password?token={token_obj.token}', mail.outbox[0].alternatives[0][0])

    def test_request_endpoint_returns_generic_ok_for_existing_user(self):
        response = self.client.post(
            '/api/auth/password-reset/request/',
            {'email': 'owner@fitzone.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(PasswordResetToken.objects.filter(user=self.user).count(), 1)

    def test_request_endpoint_returns_generic_ok_for_unknown_email_without_creating_token(self):
        response = self.client.post(
            '/api/auth/password-reset/request/',
            {'email': 'nobody@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(PasswordResetToken.objects.count(), 0)

    def test_request_endpoint_is_rate_limited_to_one_per_minute(self):
        PasswordResetToken.objects.create(
            user=self.user,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        self.client.post(
            '/api/auth/password-reset/request/',
            {'email': 'owner@fitzone.com'},
            format='json',
        )

        self.assertEqual(PasswordResetToken.objects.filter(user=self.user).count(), 1)

    def test_confirm_with_valid_token_sets_new_password_and_allows_login(self):
        token_obj = PasswordResetToken.objects.create(
            user=self.user,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            '/api/auth/password-reset/confirm/',
            {'token': str(token_obj.token), 'new_password': 'BrandNewPass1234'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        login_response = self.client.post(
            '/api/auth/login/',
            {'email': 'owner@fitzone.com', 'password': 'BrandNewPass1234'},
            format='json',
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

    def test_confirm_rejects_reused_token(self):
        token_obj = PasswordResetToken.objects.create(
            user=self.user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.post(
            '/api/auth/password-reset/confirm/',
            {'token': str(token_obj.token), 'new_password': 'FirstNewPass1234'},
            format='json',
        )

        second_response = self.client.post(
            '/api/auth/password-reset/confirm/',
            {'token': str(token_obj.token), 'new_password': 'SecondNewPass1234'},
            format='json',
        )

        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_rejects_expired_token(self):
        token_obj = PasswordResetToken.objects.create(
            user=self.user,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.post(
            '/api/auth/password-reset/confirm/',
            {'token': str(token_obj.token), 'new_password': 'BrandNewPass1234'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_rejects_unknown_token(self):
        response = self.client.post(
            '/api/auth/password-reset/confirm/',
            {'token': '00000000-0000-0000-0000-000000000000', 'new_password': 'BrandNewPass1234'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_rejects_password_below_minimum_length(self):
        token_obj = PasswordResetToken.objects.create(
            user=self.user,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            '/api/auth/password-reset/confirm/',
            {'token': str(token_obj.token), 'new_password': 'short'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        token_obj.refresh_from_db()
        self.assertFalse(token_obj.used)
