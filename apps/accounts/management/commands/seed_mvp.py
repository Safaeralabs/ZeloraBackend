from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import Organization
from apps.campaigns.models import Template
from apps.channels_config.models import ChannelConfig


User = get_user_model()


class Command(BaseCommand):
    help = 'Seed the local MVP workspace with an organization, admin user, channel configs, and base template.'

    def add_arguments(self, parser):
        parser.add_argument('--org-name', default='Comfaguajira')
        parser.add_argument('--org-slug', default='comfaguajira')
        parser.add_argument('--admin-email', default='admin@comfaguajira.com')
        parser.add_argument('--admin-password', default='Admin1234!')
        parser.add_argument('--admin-first-name', default='Admin')
        parser.add_argument('--admin-last-name', default='Vendly')

    def handle(self, *args, **options):
        org_name = options['org_name']
        org_slug = options['org_slug']
        admin_email = options['admin_email']
        admin_password = options['admin_password']
        admin_first_name = options['admin_first_name']
        admin_last_name = options['admin_last_name']

        organization, org_created = Organization.objects.get_or_create(
            slug=org_slug,
            defaults={
                'name': org_name,
                'plan': 'pilot',
                'country': 'Colombia',
                'is_active': True,
            },
        )

        user, user_created = User.objects.get_or_create(
            email=admin_email,
            defaults={
                'nombre': admin_first_name,
                'apellido': admin_last_name,
                'rol': 'admin',
                'organization': organization,
                'is_staff': True,
                'is_active': True,
            },
        )
        user.organization = organization
        user.rol = 'admin'
        user.is_staff = True
        user.is_active = True
        user.nombre = user.nombre or admin_first_name
        user.apellido = user.apellido or admin_last_name
        user.set_password(admin_password)
        user.save()

        web_config, web_created = ChannelConfig.objects.get_or_create(
            organization=organization,
            channel='web',
            defaults={
                'is_active': True,
                'settings': {'widget_enabled': True},
                'credentials': {},
            },
        )
        if not web_config.is_active:
            web_config.is_active = True
            web_config.save(update_fields=['is_active', 'updated_at'])

        whatsapp_defaults = {
            'display_phone_number': '',
            'verified_name': organization.name,
            'onboarding_status': 'not_started',
            'webhook_status': 'pending',
            'template_sync_status': 'never',
            'quality_status': 'unknown',
            'messaging_limit_status': 'unknown',
            'capabilities': ['messages', 'templates', 'status_updates'],
            'default_send_behavior': 'assistant_first',
            'fallback_handling': 'router_decides',
            'auto_sync_templates': True,
            'alert_on_webhook_failure': True,
            'internal_label': 'MVP WhatsApp',
            'internal_notes': 'Configuracion base generada por seed_mvp',
        }
        whatsapp_config, whatsapp_created = ChannelConfig.objects.get_or_create(
            organization=organization,
            channel='whatsapp',
            defaults={
                'is_active': False,
                'settings': whatsapp_defaults,
                'credentials': {},
            },
        )
        if not whatsapp_config.settings:
            whatsapp_config.settings = whatsapp_defaults
            whatsapp_config.save(update_fields=['settings', 'updated_at'])

        template, template_created = Template.objects.get_or_create(
            organization=organization,
            name='promo_bienvenida',
            defaults={
                'tipo': 'marketing',
                'content': 'Hola {{nombre}}, esta es una campana de prueba de Vendly.',
                'variables': ['nombre'],
                'channel': 'whatsapp',
                'status': 'approved',
            },
        )

        self.stdout.write(self.style.SUCCESS('MVP seed ready'))
        self.stdout.write(f'organization: {organization.name} ({organization.slug})')
        self.stdout.write(f'admin_email: {user.email}')
        self.stdout.write(f'admin_created: {user_created}')
        self.stdout.write(f'org_created: {org_created}')
        self.stdout.write(f'web_channel_created: {web_created}')
        self.stdout.write(f'whatsapp_channel_created: {whatsapp_created}')
        self.stdout.write(f'template_created: {template_created}')
