from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Contact, Organization
from apps.campaigns.models import Campaign, Template
from apps.channels_config.models import ChannelConfig
from apps.conversations.models import Conversation, Message


User = get_user_model()


@override_settings(
    ENABLE_REAL_WHATSAPP=False,
    USE_INMEMORY_CHANNEL_LAYER=True,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class MvpSmokeTests(APITestCase):
    def setUp(self):
        self.password = 'Admin1234!'
        self.organization = Organization.objects.create(
            name='Comfaguajira',
            slug='comfaguajira-test',
            plan='pilot',
            country='Colombia',
        )
        self.user = User.objects.create_user(
            email='admin@comfaguajira.test',
            password=self.password,
            nombre='Admin',
            apellido='QA',
            rol='admin',
            organization=self.organization,
            is_staff=True,
        )
        self.whatsapp_config = ChannelConfig.objects.create(
            organization=self.organization,
            channel='whatsapp',
            is_active=True,
            credentials={
                'access_token': 'test-token',
                'phone_number_id': '155512345678901',
                'waba_id': '998877665544332',
            },
            settings={},
        )
        self.web_config = ChannelConfig.objects.create(
            organization=self.organization,
            channel='web',
            is_active=True,
            credentials={},
            settings={'widget_enabled': True},
        )
        self.template = Template.objects.create(
            organization=self.organization,
            name='promo_bienvenida',
            tipo='marketing',
            content='Hola {{nombre}}, esta es una campana de prueba.',
            variables=['nombre'],
            channel='whatsapp',
            status='approved',
        )

    def authenticate(self):
        response = self.client.post(
            '/api/auth/login/',
            {'email': self.user.email, 'password': self.password},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token = response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return response

    def test_login_returns_jwt_and_user_payload(self):
        response = self.client.post(
            '/api/auth/login/',
            {'email': self.user.email, 'password': self.password},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['email'], self.user.email)
        self.assertEqual(response.data['user']['rol'], 'admin')

    def test_webchat_message_creates_contact_conversation_and_bot_reply(self):
        response = self.client.post(
            '/api/channels/webchat/messages/',
            {
                'organization_slug': self.organization.slug,
                'session_id': 'web-mvp-smoke-001',
                'message': 'Hola, necesito mi certificado',
                'nombre': 'Prueba',
                'apellido': 'Web',
                'email': 'web.test@example.com',
                'telefono': '+573009998877',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['intent'], 'request_certificate')

        conversation = Conversation.objects.get(id=response.data['conversation_id'])
        self.assertEqual(conversation.canal, 'web')
        self.assertEqual(conversation.contact.telefono, '+573009998877')
        self.assertEqual(conversation.messages.count(), 2)
        self.assertEqual(conversation.messages.order_by('timestamp').first().role, 'user')
        self.assertEqual(conversation.messages.order_by('timestamp').last().role, 'bot')

    def test_simulated_whatsapp_inbound_creates_whatsapp_conversation(self):
        self.authenticate()

        response = self.client.post(
            '/api/channels/whatsapp/simulate-inbound/',
            {
                'phone': '+573001234567',
                'message': 'Hola, necesito informacion del subsidio',
                'message_type': 'text',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'processed')

        conversation = Conversation.objects.get(canal='whatsapp', organization=self.organization)
        self.assertEqual(conversation.contact.telefono, '573001234567')
        self.assertTrue(
            Message.objects.filter(
                conversation=conversation,
                role='user',
                content__icontains='subsidio',
            ).exists()
        )

    def test_inbox_reply_to_whatsapp_conversation_updates_outbound_metadata(self):
        self.authenticate()
        contact = Contact.objects.create(
            organization=self.organization,
            nombre='Prueba',
            apellido='WhatsApp',
            telefono='573001234567',
            canal='whatsapp',
        )
        conversation = Conversation.objects.create(
            organization=self.organization,
            contact=contact,
            canal='whatsapp',
            estado='nuevo',
            intent='Consulta entrante',
            sentimiento='neutro',
        )

        response = self.client.post(
            f'/api/conversations/{conversation.id}/messages/',
            {'content': 'Te ayudo con tu solicitud.', 'role': 'agent'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        outbound = Message.objects.get(id=response.data['id'])
        self.assertEqual(outbound.role, 'agent')
        self.assertTrue(outbound.external_id.startswith('sim-'))
        self.assertEqual(outbound.metadata['channel'], 'whatsapp')
        self.assertEqual(outbound.metadata['direction'], 'outbound')
        self.assertEqual(outbound.metadata['delivery_status'], 'simulated')

    def test_campaign_send_marks_campaign_sent_and_delivered(self):
        self.authenticate()
        Contact.objects.create(
            organization=self.organization,
            nombre='Cliente',
            apellido='Campana',
            telefono='573001111111',
            canal='whatsapp',
            is_active=True,
        )
        campaign = Campaign.objects.create(
            organization=self.organization,
            template=self.template,
            name='Campana MVP',
            channel='whatsapp',
            status='draft',
            target_filter={},
        )

        response = self.client.post(f'/api/campaigns/campaigns/{campaign.id}/send/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'sent')
        self.assertEqual(campaign.delivered, 1)
        self.assertEqual(campaign.failed, 0)
