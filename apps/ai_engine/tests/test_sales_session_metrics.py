from rest_framework.test import APITestCase

from apps.accounts.models import Organization, User
from apps.ai_engine.models import SalesSession
from apps.conversations.models import Conversation


class SalesSessionMetricsViewTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Metrics Org', slug='metrics-org')
        self.other_org = Organization.objects.create(name='Other Org', slug='other-org')
        self.user = User.objects.create_user(
            email='metrics@example.com',
            password='secret123',
            nombre='Metrics',
            organization=self.org,
            rol='admin',
        )
        self.client.force_authenticate(user=self.user)

    def _create_session(self, *, organization: Organization, stage: str, situation: str, message_count: int, checkout_step: int = 0):
        conversation = Conversation.objects.create(
            organization=organization,
            canal='web',
            estado='nuevo',
        )
        return SalesSession.objects.create(
            conversation=conversation,
            organization=organization,
            stage=stage,
            situation=situation,
            message_count=message_count,
            checkout_step=checkout_step,
        )

    def test_returns_org_scoped_sales_session_metrics(self):
        self._create_session(
            organization=self.org,
            stage='discovery',
            situation='gift_customer',
            message_count=3,
        )
        self._create_session(
            organization=self.org,
            stage='checkout',
            situation='ready_to_buy_customer',
            message_count=7,
            checkout_step=2,
        )
        self._create_session(
            organization=self.org,
            stage='closed',
            situation='gift_customer',
            message_count=5,
        )
        self._create_session(
            organization=self.other_org,
            stage='handoff',
            situation='administrative_customer',
            message_count=99,
            checkout_step=1,
        )

        response = self.client.get('/api/ai/sales-sessions/metrics/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_sessions'], 3)
        self.assertEqual(response.data['active_sessions'], 2)
        self.assertEqual(response.data['checkout_sessions'], 1)
        self.assertEqual(response.data['checkout_rate_pct'], 33.3)
        self.assertEqual(response.data['opportunities'], 1)
        self.assertEqual(response.data['closed_sessions'], 1)
        self.assertEqual(response.data['stage_counts']['discovery'], 1)
        self.assertEqual(response.data['stage_counts']['checkout'], 1)
        self.assertEqual(response.data['stage_counts']['closed'], 1)
        self.assertEqual(response.data['top_situations'][0]['situation'], 'gift_customer')
        self.assertEqual(response.data['top_situations'][0]['count'], 2)

    def test_aggregates_contract_metrics(self):
        session = self._create_session(
            organization=self.org,
            stage='considering',
            situation='specific_product_customer',
            message_count=4,
        )
        session.checkout_data = {
            'contract_metrics': {
                'similar_contract_enforced': 2,
                'transfer_details_enforced': 1,
            }
        }
        session.save(update_fields=['checkout_data'])

        other = self._create_session(
            organization=self.org,
            stage='checkout',
            situation='ready_to_buy_customer',
            message_count=5,
        )
        other.checkout_data = {
            'contract_metrics': {
                'similar_contract_enforced': 1,
            }
        }
        other.save(update_fields=['checkout_data'])

        # Different org must not leak into this user's metrics.
        foreign = self._create_session(
            organization=self.other_org,
            stage='considering',
            situation='specific_product_customer',
            message_count=3,
        )
        foreign.checkout_data = {'contract_metrics': {'similar_contract_enforced': 99}}
        foreign.save(update_fields=['checkout_data'])

        response = self.client.get('/api/ai/sales-sessions/metrics/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['sessions_with_contract_metrics'], 2)
        self.assertEqual(response.data['contract_metrics']['similar_contract_enforced'], 3)
        self.assertEqual(response.data['contract_metrics']['transfer_details_enforced'], 1)
