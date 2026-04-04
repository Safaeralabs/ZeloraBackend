import sqlite3
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Organization
from apps.channels_config.models import ChannelConfig
from apps.knowledge_base.models import KBArticle, KBDocument


User = get_user_model()


@override_settings(
    ENABLE_REAL_WHATSAPP=False,
    USE_INMEMORY_CHANNEL_LAYER=True,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class MvpExtendedTests(APITestCase):
    def setUp(self):
        self.password = 'Admin1234!'
        self.organization = Organization.objects.create(
            name='Comfaguajira',
            slug='comfaguajira-ext',
            plan='pilot',
            country='Colombia',
        )
        self.user = User.objects.create_user(
            email='admin@comfaguajira.ext',
            password=self.password,
            nombre='Admin',
            apellido='Extended',
            rol='admin',
            organization=self.organization,
            is_staff=True,
        )

        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.sqlite_path = Path(temp_dir.name) / 'sisfamiliar_test.sqlite3'
        connection = sqlite3.connect(self.sqlite_path)
        try:
            cursor = connection.cursor()
            cursor.execute(
                'CREATE TABLE afiliados (cedula TEXT PRIMARY KEY, nombre_completo TEXT NOT NULL, telefono TEXT, email TEXT, tipo_afiliado TEXT)'
            )
            cursor.execute(
                'INSERT INTO afiliados (cedula, nombre_completo, telefono, email, tipo_afiliado) VALUES (?, ?, ?, ?, ?)',
                ('123456789', 'Laura Mendoza', '+573001112233', 'laura@example.com', 'trabajador'),
            )
            connection.commit()
        finally:
            connection.close()

    def authenticate(self):
        response = self.client.post(
            '/api/auth/login/',
            {'email': self.user.email, 'password': self.password},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_database_connection_lookup_and_kb_document_upload(self):
        self.authenticate()

        db_response = self.client.patch(
            '/api/channels/database/connection/',
            {
                'is_active': True,
                'engine': 'sqlite',
                'database_name': str(self.sqlite_path),
                'schema_name': '',
                'default_lookup_table': 'afiliados',
                'document_column': 'cedula',
                'full_name_column': 'nombre_completo',
                'phone_column': 'telefono',
                'email_column': 'email',
                'affiliate_type_column': 'tipo_afiliado',
                'capabilities': ['affiliate_lookup'],
            },
            format='json',
        )
        self.assertEqual(db_response.status_code, status.HTTP_200_OK)
        self.assertEqual(db_response.data['engine'], 'sqlite')
        self.assertTrue(db_response.data['is_active'])

        test_response = self.client.post('/api/channels/database/test-connection/', {}, format='json')
        self.assertEqual(test_response.status_code, status.HTTP_200_OK)
        self.assertEqual(test_response.data['connection_status'], 'connected')

        lookup_response = self.client.post(
            '/api/channels/database/lookup-affiliate/',
            {'document_number': '123456789'},
            format='json',
        )
        self.assertEqual(lookup_response.status_code, status.HTTP_200_OK)
        self.assertTrue(lookup_response.data['found'])
        self.assertEqual(lookup_response.data['record']['full_name'], 'Laura Mendoza')

        config = ChannelConfig.objects.get(organization=self.organization, channel='database')
        self.assertEqual(config.settings['connection_status'], 'connected')
        self.assertEqual(config.settings['default_lookup_table'], 'afiliados')

        article_response = self.client.post(
            '/api/kb/articles/',
            {
                'title': 'Requisitos de certificado',
                'content': 'Documento y validacion en sistema.',
                'category': 'Certificados',
                'tags': ['certificado', 'validacion'],
                'status': 'published',
            },
            format='json',
        )
        self.assertEqual(article_response.status_code, status.HTTP_201_CREATED)
        article = KBArticle.objects.get(id=article_response.data['id'])
        self.assertEqual(article.organization, self.organization)

        upload = SimpleUploadedFile(
            'certificado.txt',
            b'Documento KB para pruebas MVP',
            content_type='text/plain',
        )
        document_response = self.client.post(
            '/api/kb/documents/',
            {'article': str(article.id), 'file': upload},
            format='multipart',
        )
        self.assertEqual(document_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(document_response.data['article']), str(article.id))
        self.assertEqual(document_response.data['filename'], 'certificado.txt')

        document = KBDocument.objects.get(id=document_response.data['id'])
        self.assertEqual(document.organization, self.organization)
        self.assertEqual(document.article_id, article.id)
        self.assertEqual(document.filename, 'certificado.txt')
        self.assertGreater(document.file_size, 0)
