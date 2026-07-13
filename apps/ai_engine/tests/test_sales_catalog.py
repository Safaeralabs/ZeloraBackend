from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import Organization
from apps.ai_engine.models import SalesSession
from apps.ai_engine.sales.catalog import CatalogService
from apps.conversations.models import Conversation
from apps.ecommerce.models import Product, ProductVariant


class CatalogServiceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Test Org', slug='test-org')
        self.conversation = Conversation.objects.create(
            organization=self.org,
            canal='web',
            estado='nuevo',
        )
        self.session = SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            shown_products=[],
        )

    def test_specific_query_returns_exact_match_even_if_previously_shown(self):
        product = Product.objects.create(
            organization=self.org,
            title='Top Motion Support Arena',
            category='Tops',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(
            product=product,
            sku='top-motion-arena',
            name='Top Motion Support Arena',
            price=149900,
            stock=8,
        )

        fallback_product = Product.objects.create(
            organization=self.org,
            title='Top Basico Negro',
            category='Tops',
            status='active',
            is_active=True,
            is_bestseller=True,
        )
        ProductVariant.objects.create(
            product=fallback_product,
            sku='top-basico-negro',
            name='Top Basico Negro',
            price=89900,
            stock=10,
        )

        self.session.shown_products = [str(product.id)]
        self.session.save(update_fields=['shown_products'])

        results = CatalogService.search(
            query='Top Motion Support Arena',
            organization=self.org,
            session=self.session,
            limit=5,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Top Motion Support Arena')

    def test_specific_query_without_match_does_not_fallback_to_bestsellers(self):
        bestseller = Product.objects.create(
            organization=self.org,
            title='Legging Heat Control Negro',
            category='Leggings',
            status='active',
            is_active=True,
            is_bestseller=True,
        )
        ProductVariant.objects.create(
            product=bestseller,
            sku='legging-heat-control-negro',
            name='Legging Heat Control Negro',
            price=119900,
            stock=5,
        )

        results = CatalogService.search(
            query='Chaqueta Turbo X900 Azul',
            organization=self.org,
            session=self.session,
            limit=5,
        )

        self.assertEqual(results, [])

    def test_generic_catalog_browse_returns_available_products(self):
        product = Product.objects.create(
            organization=self.org,
            title='Camiseta Negra',
            category='Ropa',
            status='active',
            is_active=True,
            is_bestseller=True,
        )
        ProductVariant.objects.create(
            product=product,
            sku='cam-01',
            name='Talla L',
            price=40000,
            stock=6,
        )

        resolution = CatalogService.resolve_query(
            query='que productos tienes disponibles?',
            organization=self.org,
            session=self.session,
            limit=5,
        )

        self.assertEqual(resolution['resolution']['query_type'], 'catalog_browse')
        self.assertEqual(len(resolution['products']), 1)
        self.assertEqual(resolution['products'][0]['title'], 'Camiseta Negra')

    def test_generic_browse_repeats_products_when_all_were_already_shown(self):
        first = Product.objects.create(
            organization=self.org,
            title='Camiseta Negra',
            category='Ropa',
            status='active',
            is_active=True,
            is_bestseller=True,
        )
        second = Product.objects.create(
            organization=self.org,
            title='Camiseta Blanca',
            category='Ropa',
            status='active',
            is_active=True,
            is_bestseller=False,
        )
        ProductVariant.objects.create(product=first, sku='cam-n', name='N', price=40000, stock=6)
        ProductVariant.objects.create(product=second, sku='cam-b', name='B', price=42000, stock=7)

        self.session.shown_products = [str(first.id), str(second.id)]
        self.session.save(update_fields=['shown_products'])

        resolution = CatalogService.resolve_query(
            query='que otros productos tienes?',
            organization=self.org,
            session=self.session,
            limit=5,
        )

        self.assertEqual(resolution['resolution']['query_type'], 'catalog_browse')
        self.assertGreaterEqual(len(resolution['products']), 1)

    def test_ambiguous_lookup_marks_confirmation_needed(self):
        top = Product.objects.create(
            organization=self.org,
            title='Top Motion Support Arena',
            category='Tops',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(
            product=top,
            sku='top-arena',
            name='Arena',
            price=149900,
            stock=8,
        )
        top_alt = Product.objects.create(
            organization=self.org,
            title='Top Motion Support Negro',
            category='Tops',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(
            product=top_alt,
            sku='top-negro',
            name='Negro',
            price=149900,
            stock=7,
        )

        resolution = CatalogService.resolve_query(
            query='quiero un top motion',
            organization=self.org,
            session=self.session,
            limit=5,
        )

        self.assertTrue(resolution['resolution']['needs_confirmation'])
        self.assertGreaterEqual(len(resolution['products']), 2)


class CatalogServiceStockAndAvailabilityTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Stock Org', slug='stock-org')
        self.other_org = Organization.objects.create(name='Other Org', slug='other-org')
        self.conversation = Conversation.objects.create(
            organization=self.org,
            canal='web',
            estado='nuevo',
        )
        self.session = SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            shown_products=[],
        )

    def _create_product(self, *, org=None, title, stock, is_active=True, is_bestseller=True):
        org = org or self.org
        product = Product.objects.create(
            organization=org,
            title=title,
            category='Ropa',
            status='active',
            is_active=is_active,
            is_bestseller=is_bestseller,
        )
        ProductVariant.objects.create(
            product=product,
            sku=f'{title[:8]}-sku',
            name='Variante',
            price=80_000,
            stock=stock,
        )
        return product

    def test_product_with_zero_stock_is_excluded_from_results(self):
        self._create_product(title='Top Agotado', stock=0)
        results = CatalogService.search(
            query='Top Agotado',
            organization=self.org,
            session=self.session,
        )
        self.assertEqual(results, [])

    def test_inactive_product_is_excluded_from_results(self):
        self._create_product(title='Top Inactivo', stock=10, is_active=False)
        results = CatalogService.search(
            query='Top Inactivo',
            organization=self.org,
            session=self.session,
        )
        self.assertEqual(results, [])

    def test_product_from_other_org_is_not_returned(self):
        self._create_product(org=self.other_org, title='Top Otra Org', stock=5)
        results = CatalogService.search(
            query='Top Otra Org',
            organization=self.org,
            session=self.session,
        )
        self.assertEqual(results, [])

    def test_available_product_appears_in_results(self):
        self._create_product(title='Top Disponible', stock=3)
        results = CatalogService.search(
            query='Top Disponible',
            organization=self.org,
            session=self.session,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Top Disponible')
        self.assertTrue(results[0]['is_available'])

    def test_get_product_by_id_returns_none_when_out_of_stock(self):
        product = self._create_product(title='Top Sin Stock', stock=0)
        result = CatalogService.get_product_by_id(str(product.id), self.org)
        self.assertIsNone(result)

    def test_get_product_by_id_returns_none_for_other_org(self):
        product = self._create_product(org=self.other_org, title='Top Ajeno', stock=5)
        result = CatalogService.get_product_by_id(str(product.id), self.org)
        self.assertIsNone(result)

    def test_variant_snapshot_returns_available_and_unavailable_labels(self):
        product = Product.objects.create(
            organization=self.org,
            title='Enterizo Shape Black',
            category='Ropa',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(
            product=product,
            sku='ent-s',
            name='S',
            price=169900,
            stock=3,
            reserved=0,
        )
        ProductVariant.objects.create(
            product=product,
            sku='ent-m',
            name='M',
            price=169900,
            stock=0,
            reserved=0,
        )

        snapshot = CatalogService.get_variant_snapshot(str(product.id), self.org)

        self.assertEqual(snapshot['product_id'], str(product.id))
        self.assertIn('S', snapshot['labels_available'])
        self.assertIn('M', snapshot['labels_unavailable'])


class CatalogServiceOutOfStockSurfacingTests(TestCase):
    """
    Out-of-stock matches must never be indistinguishable from "doesn't exist" —
    they should surface separately so the agent can say "lo tenemos pero esta
    agotado" instead of a flat "no tengo ese producto".
    """

    def setUp(self):
        self.org = Organization.objects.create(name='Agotado Org', slug='agotado-org')
        self.conversation = Conversation.objects.create(
            organization=self.org,
            canal='web',
            estado='nuevo',
        )
        self.session = SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            shown_products=[],
        )

    def test_exact_title_match_out_of_stock_surfaces_as_unavailable(self):
        product = Product.objects.create(
            organization=self.org,
            title='Pantalon Beige Clasico',
            category='Pantalones',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(product=product, sku='pant-beige', name='Unico', price=99000, stock=0)

        resolution = CatalogService.resolve_query(
            query='Pantalon Beige Clasico',
            organization=self.org,
            session=self.session,
            limit=5,
        )

        self.assertEqual(resolution['products'], [])
        self.assertEqual(len(resolution['unavailable_products']), 1)
        self.assertEqual(resolution['unavailable_products'][0]['title'], 'Pantalon Beige Clasico')
        self.assertEqual(resolution['unavailable_products'][0]['availability_label'], 'Agotado')
        self.assertEqual(resolution['resolution']['match_type'], 'exact_out_of_stock')

    def test_keyword_match_out_of_stock_surfaces_as_unavailable(self):
        product = Product.objects.create(
            organization=self.org,
            title='Chaqueta Impermeable Azul',
            category='Chaquetas',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(product=product, sku='chaq-azul', name='Unico', price=159000, stock=0)

        resolution = CatalogService.resolve_query(
            query='tienen chaqueta azul?',
            organization=self.org,
            session=self.session,
            limit=5,
        )

        self.assertEqual(resolution['products'], [])
        self.assertEqual(len(resolution['unavailable_products']), 1)
        self.assertEqual(resolution['unavailable_products'][0]['title'], 'Chaqueta Impermeable Azul')
        self.assertEqual(resolution['resolution']['match_type'], 'out_of_stock')

    def test_search_wrapper_still_excludes_out_of_stock_products(self):
        """CatalogService.search() (used for app-chat cards) must stay available-only."""
        product = Product.objects.create(
            organization=self.org,
            title='Sudadera Gris Oversize',
            category='Sudaderas',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(product=product, sku='sud-gris', name='Unico', price=129000, stock=0)

        results = CatalogService.search(
            query='Sudadera Gris Oversize',
            organization=self.org,
            session=self.session,
        )

        self.assertEqual(results, [])


@override_settings(OPENAI_API_KEY='test-key', ENABLE_REAL_AI=True)
class CatalogServiceSemanticFallbackTests(TestCase):
    """
    When literal keyword matching finds nothing, embedding similarity should
    still surface the closest thing the store actually sells — e.g. a
    customer asking for "camisa" should be offered "blusa" if that's the
    closest semantic match, without a hardcoded synonym dictionary.
    """

    def setUp(self):
        self.org = Organization.objects.create(name='Semantic Org', slug='semantic-org')
        self.conversation = Conversation.objects.create(
            organization=self.org,
            canal='web',
            estado='nuevo',
        )
        self.session = SalesSession.objects.create(
            conversation=self.conversation,
            organization=self.org,
            shown_products=[],
        )

    def test_no_keyword_match_falls_back_to_semantic_similarity(self):
        blusa = Product.objects.create(
            organization=self.org,
            title='Blusa Elegante Turquesa',
            category='Blusas',
            status='active',
            is_active=True,
            embedding_vector=[1.0, 0.0, 0.0],
        )
        ProductVariant.objects.create(product=blusa, sku='blusa-turq', name='Unico', price=90000, stock=5)

        unrelated = Product.objects.create(
            organization=self.org,
            title='Guantes de Gimnasio',
            category='Accesorios',
            status='active',
            is_active=True,
            embedding_vector=[0.0, 0.0, 1.0],
        )
        ProductVariant.objects.create(product=unrelated, sku='guantes', name='Unico', price=30000, stock=5)

        with patch('apps.ai_engine.sales_kb._embed_query', return_value=[0.9, 0.1, 0.0]), \
             patch('openai.OpenAI', side_effect=RuntimeError('no llm in tests')):
            resolution = CatalogService.resolve_query(
                query='tienen camisa?',
                organization=self.org,
                session=self.session,
                limit=5,
            )

        self.assertEqual(resolution['resolution']['match_type'], 'semantic')
        self.assertEqual(len(resolution['products']), 1)
        self.assertEqual(resolution['products'][0]['title'], 'Blusa Elegante Turquesa')

    def test_semantic_fallback_below_threshold_returns_nothing(self):
        unrelated = Product.objects.create(
            organization=self.org,
            title='Guantes de Gimnasio',
            category='Accesorios',
            status='active',
            is_active=True,
            embedding_vector=[0.0, 1.0, 0.0],
        )
        ProductVariant.objects.create(product=unrelated, sku='guantes', name='Unico', price=30000, stock=5)

        with patch('apps.ai_engine.sales_kb._embed_query', return_value=[1.0, 0.0, 0.0]), \
             patch('openai.OpenAI', side_effect=RuntimeError('no llm in tests')):
            resolution = CatalogService.resolve_query(
                query='tienen camisa?',
                organization=self.org,
                session=self.session,
                limit=5,
            )

        self.assertEqual(resolution['products'], [])
        self.assertEqual(resolution['unavailable_products'], [])
        self.assertEqual(resolution['resolution']['match_type'], 'none')

    def test_semantic_fallback_surfaces_out_of_stock_match_as_unavailable(self):
        blusa = Product.objects.create(
            organization=self.org,
            title='Blusa Elegante Turquesa',
            category='Blusas',
            status='active',
            is_active=True,
            embedding_vector=[1.0, 0.0, 0.0],
        )
        ProductVariant.objects.create(product=blusa, sku='blusa-turq', name='Unico', price=90000, stock=0)

        with patch('apps.ai_engine.sales_kb._embed_query', return_value=[0.9, 0.1, 0.0]), \
             patch('openai.OpenAI', side_effect=RuntimeError('no llm in tests')):
            resolution = CatalogService.resolve_query(
                query='tienen camisa?',
                organization=self.org,
                session=self.session,
                limit=5,
            )

        self.assertEqual(resolution['products'], [])
        self.assertEqual(len(resolution['unavailable_products']), 1)
        self.assertEqual(resolution['unavailable_products'][0]['title'], 'Blusa Elegante Turquesa')

    def test_semantic_fallback_disabled_without_real_ai(self):
        blusa = Product.objects.create(
            organization=self.org,
            title='Blusa Elegante Turquesa',
            category='Blusas',
            status='active',
            is_active=True,
            embedding_vector=[1.0, 0.0, 0.0],
        )
        ProductVariant.objects.create(product=blusa, sku='blusa-turq', name='Unico', price=90000, stock=5)

        with override_settings(ENABLE_REAL_AI=False):
            resolution = CatalogService.resolve_query(
                query='tienen camisa?',
                organization=self.org,
                session=self.session,
                limit=5,
            )

        self.assertEqual(resolution['resolution']['match_type'], 'none')
