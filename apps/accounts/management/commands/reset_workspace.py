from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import Contact, Organization
from apps.analytics.models import MetricsSnapshot
from apps.campaigns.models import Campaign, Template
from apps.channels_config.models import ChannelConfig
from apps.conversations.models import Conversation, Message, QAScore, TimelineEvent
from apps.flows.models import Flow
from apps.knowledge_base.models import KBArticle, KBDocument


User = get_user_model()


class Command(BaseCommand):
    help = 'Reset a local organization workspace to a fresh post-signup state.'

    def add_arguments(self, parser):
        parser.add_argument('--org-slug', default='comfaguajira')

    def handle(self, *args, **options):
        org_slug = options['org_slug']
        organization = Organization.objects.filter(slug=org_slug).first()
        if organization is None:
            self.stdout.write(self.style.WARNING(f'Organization not found: {org_slug}'))
            return

        Message.objects.filter(conversation__organization=organization).delete()
        TimelineEvent.objects.filter(conversation__organization=organization).delete()
        QAScore.objects.filter(conversation__organization=organization).delete()
        Conversation.objects.filter(organization=organization).delete()
        Contact.objects.filter(organization=organization).delete()

        Campaign.objects.filter(organization=organization).delete()
        Template.objects.filter(organization=organization).delete()
        Flow.objects.filter(organization=organization).delete()
        KBArticle.objects.filter(organization=organization).delete()
        KBDocument.objects.filter(organization=organization).delete()
        MetricsSnapshot.objects.filter(organization=organization).delete()

        User.objects.filter(organization=organization).exclude(email='admin@comfaguajira.com').delete()

        for config in ChannelConfig.objects.filter(organization=organization):
            if config.channel == 'web':
                config.is_active = False
                config.credentials = {}
                config.settings = {'widget_enabled': False}
            elif config.channel == 'whatsapp':
                config.is_active = False
                config.webhook_url = ''
                config.credentials = {}
                config.settings = {
                    'display_phone_number': '',
                    'verified_name': organization.name,
                    'onboarding_status': 'not_started',
                    'webhook_status': 'pending',
                    'template_sync_status': 'never',
                    'quality_status': 'unknown',
                    'messaging_limit_status': 'unknown',
                    'capabilities': [],
                    'default_send_behavior': 'assistant_first',
                    'fallback_handling': 'router_decides',
                    'auto_sync_templates': True,
                    'alert_on_webhook_failure': True,
                    'internal_label': '',
                    'internal_notes': '',
                    'last_sync_at': None,
                    'last_webhook_received_at': None,
                }
            else:
                config.is_active = False
                config.credentials = {}
                config.settings = {}
            config.save()

        self.stdout.write(self.style.SUCCESS(f'Workspace reset: {organization.slug}'))
