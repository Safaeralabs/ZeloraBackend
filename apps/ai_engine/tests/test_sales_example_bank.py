"""
ExampleBank — few-shot retrieval of approved conversation examples.

Covers: retrieval formatting, stage-first fallback ranking, approval keeping
examples out of the KBArticle table, and prompt wiring in the generator.
"""
from types import SimpleNamespace

from django.test import TestCase

from apps.accounts.models import Organization
from apps.ai_engine.sales.examples import ExampleBank
from apps.ai_engine.sales.generator import ResponseGenerator
from apps.analytics.learning import approve_learning_candidate
from apps.analytics.models import LearningCandidate
from apps.knowledge_base.models import KBArticle


def _example(org, *, kind='conversation_example', status='approved', stage='considering',
             question='Esta muy caro', answer='Te entiendo, mira la calidad del material.',
             confidence=0.9, fingerprint=''):
    return LearningCandidate.objects.create(
        organization=org,
        kind=kind,
        status=status,
        title=f'Ejemplo: {question[:40]}',
        source_question=question,
        proposed_answer=answer,
        confidence=confidence,
        fingerprint=fingerprint or f'fp-{question[:20]}-{confidence}',
        metadata={'stage': stage, 'commercial_outcome': 'purchased'},
    )


class ExampleBankFetchTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Bank Org', slug='bank-org')

    def test_empty_without_approved_examples(self):
        _example(self.org, status='pending', fingerprint='fp-pending')
        self.assertEqual(ExampleBank.fetch(self.org, query='caro'), '')

    def test_formats_approved_examples_as_dialog(self):
        _example(self.org)
        result = ExampleBank.fetch(self.org, query='esta caro', stage='considering')
        self.assertIn('Cliente: "Esta muy caro"', result)
        self.assertIn('Marca: "Te entiendo, mira la calidad del material."', result)

    def test_same_stage_examples_rank_first(self):
        _example(
            self.org, stage='discovering', confidence=0.95,
            question='Que productos tienen?', answer='Tenemos de todo, cuentame que buscas.',
            fingerprint='fp-disc',
        )
        _example(
            self.org, stage='checkout', confidence=0.80,
            question='Como pago?', answer='Puedes pagar con Nequi o contraentrega.',
            fingerprint='fp-checkout',
        )
        result = ExampleBank.fetch(self.org, stage='checkout', max_examples=1)
        self.assertIn('Como pago?', result)
        self.assertNotIn('Que productos tienen?', result)

    def test_ignores_other_kinds_and_orgs(self):
        _example(self.org, kind='faq', fingerprint='fp-faq-kind')
        other_org = Organization.objects.create(name='Other', slug='other-bank-org')
        _example(other_org, fingerprint='fp-other-org')
        self.assertEqual(ExampleBank.fetch(self.org), '')


class ExampleApprovalTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Approve Org', slug='approve-bank-org')

    def test_conversation_example_approval_creates_no_article(self):
        candidate = _example(self.org, status='pending', fingerprint='fp-approve-1')
        article = approve_learning_candidate(candidate=candidate)
        candidate.refresh_from_db()
        self.assertIsNone(article)
        self.assertEqual(candidate.status, 'approved')
        self.assertEqual(KBArticle.objects.filter(organization=self.org).count(), 0)
        # And it becomes retrievable by the bank right away.
        self.assertIn('Esta muy caro', ExampleBank.fetch(self.org))

    def test_winning_reply_approval_creates_no_article(self):
        candidate = _example(
            self.org, kind='winning_reply', status='pending', fingerprint='fp-approve-2',
        )
        article = approve_learning_candidate(candidate=candidate)
        self.assertIsNone(article)
        self.assertEqual(KBArticle.objects.filter(organization=self.org).count(), 0)


class GeneratorExampleSectionTests(TestCase):
    def _prompt(self, context):
        session = SimpleNamespace(
            organization=SimpleNamespace(name='Bank Org'),
            stage='considering',
            selected_products=[],
            budget_min=None,
            budget_max=None,
            objections=[],
            category_interest='',
        )
        return ResponseGenerator._build_system_prompt(
            session=session,
            situation='objection',
            action={'response_strategy': 'close'},
            context=context,
            runtime_config={},
        )

    def test_prompt_includes_examples_section(self):
        prompt = self._prompt({
            'recommended_products': [], 'product_resolution': {}, 'promotions': [],
            'kb_content': '',
            'sales_examples': 'Cliente: "Esta caro"\nMarca: "Mira la garantia."',
        })
        self.assertIn('Asi respondio la marca en casos reales similares', prompt)
        self.assertIn('NO copies precios', prompt)
        self.assertIn('Mira la garantia.', prompt)

    def test_prompt_omits_section_without_examples(self):
        prompt = self._prompt({
            'recommended_products': [], 'product_resolution': {}, 'promotions': [],
            'kb_content': '', 'sales_examples': '',
        })
        self.assertNotIn('Asi respondio la marca', prompt)
