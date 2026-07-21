from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Organization
from apps.billing.models import Plan, Subscription


class PlanUsageTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Billing Test', slug='billing-test')
        self.plan = Plan.objects.create(
            slug='p-crece', name='Crece', price_cop=169900,
            max_conversations_month=1000, extra_conversation_price_cop=150,
        )

    def _sub(self, **kw):
        return Subscription.objects.create(organization=self.org, plan=self.plan, **kw)

    def test_within_cap_no_overage(self):
        s = self._sub()
        s.register_conversation(count=50)
        self.assertEqual(s.conversations_used, 50)
        self.assertEqual(s.overage_conversations, 0)
        self.assertEqual(s.overage_amount_cop, Decimal('0'))
        self.assertFalse(s.in_payg)
        self.assertEqual(s.conversations_remaining, 950)

    def test_crossing_cap_charges_only_excess(self):
        s = self._sub()
        s.conversations_used = 995
        s.register_conversation(count=10)  # 995 -> 1005, solo 5 por encima del cupo
        self.assertEqual(s.conversations_used, 1005)
        self.assertEqual(s.overage_conversations, 5)
        self.assertEqual(s.overage_amount_cop, Decimal('750'))  # 5 * 150
        self.assertTrue(s.in_payg)
        self.assertEqual(s.conversations_remaining, 0)

    def test_fully_in_payg_each_counts(self):
        s = self._sub()
        s.conversations_used = 1200
        s.overage_conversations = 200
        s.overage_amount_cop = Decimal('30000')
        s.register_conversation(count=3)
        self.assertEqual(s.overage_conversations, 203)
        self.assertEqual(s.overage_amount_cop, Decimal('30450'))  # +3 * 150

    def test_trial_never_accrues_overage(self):
        s = self._sub(is_trial=True, trial_ends_at=timezone.now() + timedelta(days=7))
        s.conversations_used = 1000
        s.register_conversation(count=50)
        self.assertEqual(s.overage_amount_cop, Decimal('0'))
        self.assertEqual(s.overage_conversations, 0)
        self.assertTrue(s.is_trial_active)

    def test_expired_trial_not_active(self):
        s = self._sub(is_trial=True, trial_ends_at=timezone.now() - timedelta(days=1))
        self.assertFalse(s.is_trial_active)

    def test_spend_ceiling(self):
        s = self._sub(spend_ceiling_cop=1000)
        s.overage_amount_cop = Decimal('900')
        self.assertFalse(s.spend_ceiling_reached)
        s.overage_amount_cop = Decimal('1000')
        self.assertTrue(s.spend_ceiling_reached)

    def test_reset_cycle(self):
        s = self._sub()
        s.conversations_used = 500
        s.overage_conversations = 5
        s.overage_amount_cop = Decimal('1000')
        s.reset_cycle()
        self.assertEqual(s.conversations_used, 0)
        self.assertEqual(s.overage_conversations, 0)
        self.assertEqual(s.overage_amount_cop, Decimal('0'))

    def test_org_bridge_resolves_active_subscription(self):
        s = self._sub(status='active')
        self.assertEqual(self.org.active_subscription, s)
        self.assertEqual(self.org.current_plan, self.plan)

    def test_org_bridge_ignores_cancelled(self):
        self._sub(status='cancelled')
        self.assertIsNone(self.org.active_subscription)
        self.assertIsNone(self.org.current_plan)


class SeedPlansCommandTests(TestCase):
    def test_seed_is_idempotent(self):
        from django.core.management import call_command
        call_command('seed_plans', verbosity=0)
        call_command('seed_plans', verbosity=0)  # segunda corrida no duplica
        self.assertEqual(Plan.objects.filter(slug__in=['emprende', 'crece', 'negocio']).count(), 3)
        crece = Plan.objects.get(slug='crece')
        self.assertTrue(crece.highlight)
        self.assertEqual(crece.max_conversations_month, 1000)
        self.assertEqual(crece.extra_conversation_price_cop, 150)


class SubscriptionServiceTests(TestCase):
    """Los planes ya existen en la BD de test (migración de datos 0003)."""

    def setUp(self):
        self.org = Organization.objects.create(name='Svc Org', slug='svc-org', plan='pilot')

    def test_start_trial_creates_trialing_subscription(self):
        from apps.billing.services import start_trial
        sub = start_trial(self.org)
        self.assertIsNotNone(sub)
        self.assertTrue(sub.is_trial)
        self.assertEqual(sub.status, 'trialing')
        self.assertEqual(sub.plan.slug, 'crece')
        self.assertIsNotNone(sub.trial_ends_at)
        self.assertTrue(sub.is_trial_active)

    def test_start_trial_is_idempotent(self):
        from apps.billing.services import start_trial
        s1 = start_trial(self.org)
        s2 = start_trial(self.org)
        self.assertEqual(s1.id, s2.id)
        self.assertEqual(self.org.subscriptions.count(), 1)

    def test_ensure_subscription_maps_legacy_plan(self):
        from apps.billing.services import ensure_subscription
        self.org.plan = 'enterprise'
        self.org.save()
        sub = ensure_subscription(self.org)
        self.assertEqual(sub.plan.slug, 'negocio')
        self.assertEqual(sub.status, 'active')
        self.assertFalse(sub.is_trial)

    def test_backfill_command_is_idempotent(self):
        from django.core.management import call_command
        Organization.objects.create(name='Other Org', slug='other-org', plan='pro')
        call_command('backfill_subscriptions', verbosity=0)
        call_command('backfill_subscriptions', verbosity=0)
        for o in Organization.objects.all():
            self.assertEqual(o.subscriptions.count(), 1)
        self.assertIsNotNone(self.org.current_plan)

    def test_org_limit_properties_use_plan(self):
        from apps.billing.services import ensure_subscription
        org = Organization.objects.create(name='Lim Org', slug='lim-org', plan='pro')
        ensure_subscription(org)  # legacy 'pro' -> Crece
        self.assertEqual(org.agent_limit, 3)
        self.assertEqual(org.product_limit, 500)
        self.assertEqual(org.channel_limit, 4)

    def test_org_limits_fallback_without_subscription(self):
        org = Organization.objects.create(name='No Sub', slug='no-sub', plan='pilot', max_agents=3)
        self.assertEqual(org.agent_limit, 3)      # campo legacy
        self.assertEqual(org.product_limit, 0)    # ilimitado por defecto
        self.assertEqual(org.channel_limit, 1)


class MeteringTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Meter Org', slug='meter-org', plan='pilot')
        self.plan = Plan.objects.create(
            slug='p-meter', name='Meter', price_cop=1000,
            max_conversations_month=2, extra_conversation_price_cop=100,
        )
        self.sub = Subscription.objects.create(
            organization=self.org, plan=self.plan, status='active', is_trial=False,
            period_start=timezone.now(), period_end=timezone.now() + timedelta(days=30),
        )

    def _conv(self, ext):
        from apps.accounts.models import Contact
        from apps.conversations.models import Conversation
        contact = Contact.objects.create(organization=self.org, nombre='X', canal='app', tipo='cliente')
        return Conversation.objects.create(
            organization=self.org, canal='app', external_id=ext, contact=contact, metadata={},
        )

    def test_meter_counts_once_per_cycle(self):
        from apps.billing.services import record_conversation_usage
        c = self._conv('c1')
        record_conversation_usage(self.org, c)
        record_conversation_usage(self.org, c)  # dedup: misma conversación, mismo ciclo
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.conversations_used, 1)

    def test_meter_accrues_payg_over_cap(self):
        from apps.billing.services import record_conversation_usage
        for i in range(3):  # cupo=2 -> la 3ra es excedente
            record_conversation_usage(self.org, self._conv(f'c{i}'))
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.conversations_used, 3)
        self.assertEqual(self.sub.overage_conversations, 1)
        self.assertEqual(self.sub.overage_amount_cop, Decimal('100'))
        self.assertTrue(self.sub.in_payg)

    def test_reset_task_rolls_cycle(self):
        from apps.billing.tasks import reset_billing_cycles_task
        self.sub.period_end = timezone.now() - timedelta(days=1)
        self.sub.conversations_used = 5
        self.sub.overage_conversations = 3
        self.sub.overage_amount_cop = Decimal('500')
        self.sub.save()
        reset_billing_cycles_task()
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.conversations_used, 0)
        self.assertEqual(self.sub.overage_conversations, 0)
        self.assertEqual(self.sub.overage_amount_cop, Decimal('0'))
        self.assertGreater(self.sub.period_end, timezone.now())
