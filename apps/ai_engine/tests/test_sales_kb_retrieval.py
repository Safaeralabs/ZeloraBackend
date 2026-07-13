"""
Tests for KBService retrieval (semantic + keyword fallback) and for the
learning-approval → sales-agent wiring (canonical purposes).
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import Organization
from apps.ai_engine.sales.kb import KBService
from apps.analytics.learning import approve_learning_candidate
from apps.analytics.models import LearningCandidate
from apps.knowledge_base.models import KBArticle


class KBServiceKeywordTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='KB Org', slug='kb-org')

    def _article(self, title, content, purpose='policy', **extra):
        extra.setdefault('status', 'published')
        return KBArticle.objects.create(
            organization=self.org,
            title=title,
            content=content,
            purpose=purpose,
            **extra,
        )

    def test_keyword_match_returns_article(self):
        self._article('Politica de envios', 'Enviamos a todo el pais en 3 dias habiles.')
        result = KBService.fetch(purposes=['policy'], organization=self.org, query='envios rapidos')
        self.assertIn('Politica de envios', result)

    def test_keyword_without_match_returns_empty(self):
        self._article('Politica de entregas', 'Despachamos a todo el pais.')
        result = KBService.fetch(purposes=['policy'], organization=self.org, query='garantia extendida')
        self.assertEqual(result, '')

    def test_no_query_returns_top_by_visits(self):
        self._article('Menos visitado', 'contenido a', visits=1)
        self._article('Mas visitado', 'contenido b', visits=9)
        result = KBService.fetch(purposes=['policy'], organization=self.org, max_articles=1)
        self.assertIn('Mas visitado', result)
        self.assertNotIn('Menos visitado', result)

    def test_unpublished_and_other_org_articles_are_excluded(self):
        self._article('Borrador', 'no publicado', status='draft')
        other_org = Organization.objects.create(name='Otra', slug='otra-kb')
        KBArticle.objects.create(
            organization=other_org, title='Ajena', content='de otra org',
            purpose='policy', status='published',
        )
        result = KBService.fetch(purposes=['policy'], organization=self.org)
        self.assertEqual(result, '')


@override_settings(OPENAI_API_KEY='test-key', ENABLE_REAL_AI=True)
class KBServiceSemanticTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='KB Sem Org', slug='kb-sem-org')
        # "Politica de entregas" shares NO keywords with the query
        # "hacen envios a cartagena?" — only semantics can find it.
        self.delivery = KBArticle.objects.create(
            organization=self.org,
            title='Politica de entregas',
            content='Despachamos a todas las ciudades principales en 2-4 dias.',
            purpose='policy',
            status='published',
            embedding_vector=[1.0, 0.0, 0.0],
        )
        self.returns = KBArticle.objects.create(
            organization=self.org,
            title='Politica de devoluciones',
            content='Cambios dentro de 15 dias con etiqueta original.',
            purpose='policy',
            status='published',
            embedding_vector=[0.0, 1.0, 0.0],
        )

    def test_semantic_match_beats_missing_keywords(self):
        with patch('apps.ai_engine.sales_kb._embed_query', return_value=[0.9, 0.1, 0.0]):
            result = KBService.fetch(
                purposes=['policy'], organization=self.org,
                query='hacen envios a cartagena?', max_articles=1,
            )
        self.assertIn('Politica de entregas', result)
        self.assertNotIn('devoluciones', result)

    def test_low_similarity_falls_back_to_keyword(self):
        # Orthogonal query vector → no semantic hit → keyword path.
        with patch('apps.ai_engine.sales_kb._embed_query', return_value=[0.0, 0.0, 1.0]):
            result = KBService.fetch(
                purposes=['policy'], organization=self.org,
                query='devoluciones', max_articles=1,
            )
        self.assertIn('devoluciones', result)

    def test_embed_failure_falls_back_to_keyword(self):
        with patch('apps.ai_engine.sales_kb._embed_query', return_value=[]):
            result = KBService.fetch(
                purposes=['policy'], organization=self.org,
                query='entregas', max_articles=1,
            )
        self.assertIn('Politica de entregas', result)


class LearningApprovalWiringTests(TestCase):
    """Approved learnings must use canonical purposes the agent retrieves."""

    def setUp(self):
        self.org = Organization.objects.create(name='Learn Org', slug='learn-org')

    def test_approved_objection_lands_in_sales_scripts(self):
        candidate = LearningCandidate.objects.create(
            organization=self.org,
            kind='objection',
            title='Cliente dice que es muy caro',
            source_question='Es muy caro comparado con otras tiendas',
            proposed_answer='Resalta la calidad del material y la garantia de 30 dias.',
            fingerprint='fp-objection-1',
        )
        article = approve_learning_candidate(candidate=candidate)
        self.assertEqual(article.purpose, 'sales_scripts')
        result = KBService.fetch(purposes=['sales_scripts'], organization=self.org, query='caro')
        self.assertIn('Cliente dice que es muy caro', result)

    def test_approved_style_lands_in_business(self):
        candidate = LearningCandidate.objects.create(
            organization=self.org,
            kind='estilo_comunicacion',
            title='Clientes escriben informal',
            source_question='Los clientes tutean y usan emojis',
            proposed_answer='Responder cercano, tuteo natural.',
            fingerprint='fp-style-1',
        )
        article = approve_learning_candidate(candidate=candidate)
        self.assertEqual(article.purpose, 'business')

    def test_approved_faq_stays_retrievable(self):
        candidate = LearningCandidate.objects.create(
            organization=self.org,
            kind='faq',
            title='Tienen tienda fisica',
            source_question='Tienen tienda fisica en Bogota?',
            proposed_answer='Solo vendemos online con envios a todo el pais.',
            fingerprint='fp-faq-1',
        )
        article = approve_learning_candidate(candidate=candidate)
        self.assertEqual(article.purpose, 'faq')
        result = KBService.fetch(purposes=['faq'], organization=self.org, query='tienda fisica')
        self.assertIn('Tienen tienda fisica', result)
