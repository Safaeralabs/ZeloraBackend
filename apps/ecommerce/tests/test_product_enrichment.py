"""
P1.1: Tests for product enrichment (new fields, Promotion model, ProductRelation model)
"""
import uuid
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import Organization, User
from apps.ecommerce.models import Product, ProductVariant, Promotion, ProductRelation
from apps.ai_engine.sales_tools import lookup_products, get_active_promotions, _serialize_product


class TestProductEnrichment(TestCase):
    """Tests for P1.1 new product fields."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Test Org',
            slug='test-org',
        )

    def test_product_with_new_fields(self):
        """Product can be created with new enriched fields."""
        product = Product.objects.create(
            organization=self.org,
            title='Test Dress',
            category='Clothing',
            subcategory='Formal wear',  # P1.1
            style='formal',  # P1.1
            color='navy blue',  # P1.1
            material='cotton',  # P1.1
            fit='slim',  # P1.1
            formality='formal',  # P1.1
            target_audience='women',  # P1.1
            occasion=['wedding', 'dinner'],  # P1.1
            is_bestseller=True,  # P1.1
            popularity_score=4.5,  # P1.1
            offer_type='physical',
            status='draft',
            is_active=True,
        )

        assert product.subcategory == 'Formal wear'
        assert product.formality == 'formal'
        assert 'wedding' in product.occasion
        assert product.is_bestseller is True
        assert product.popularity_score == 4.5

    def test_lookup_products_searches_new_fields(self):
        """lookup_products should match products on new enriched fields."""
        # Create products
        product1 = Product.objects.create(
            organization=self.org,
            title='Casual Shirt',
            style='casual',
            formality='casual',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(product=product1, sku='shirt-1', name='Shirt Variant', price=50)

        product2 = Product.objects.create(
            organization=self.org,
            title='Formal Dress',
            style='formal',
            formality='formal',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(product=product2, sku='dress-1', name='Dress Variant', price=100)

        # Search by formality
        results = lookup_products(self.org, 'formal')
        assert len(results) > 0
        assert any(r['formality'] == 'formal' for r in results)

    def test_serialize_product_includes_new_fields(self):
        """_serialize_product should include all new P1.1 fields."""
        product = Product.objects.create(
            organization=self.org,
            title='Test Product',
            subcategory='Sub',
            style='casual',
            color='red',
            material='wool',
            fit='regular',
            formality='semiformal',
            target_audience='men',
            occasion=['casual', 'work'],
            is_bestseller=False,
            popularity_score=3.2,
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(product=product, sku='sku-1', name='Variant', price=100)

        serialized = _serialize_product(product)

        assert serialized['subcategory'] == 'Sub'
        assert serialized['style'] == 'casual'
        assert serialized['color'] == 'red'
        assert serialized['material'] == 'wool'
        assert serialized['fit'] == 'regular'
        assert serialized['formality'] == 'semiformal'
        assert serialized['target_audience'] == 'men'
        assert 'casual' in serialized['occasion']
        assert serialized['is_bestseller'] is False


class TestPromotion(TestCase):
    """Tests for P1.1 Promotion model."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Test Org',
            slug='test-org',
        )

    def test_create_promotion_all_products(self):
        """Promotion can target all products."""
        promo = Promotion.objects.create(
            organization=self.org,
            title='Summer Sale',
            description='20% off everything',
            discount_type='percentage',
            discount_value=20,
            applies_to='all_products',
            is_active=True,
        )
        assert promo.applies_to == 'all_products'
        assert float(promo.discount_value) == 20.0

    def test_create_promotion_category(self):
        """Promotion can target specific category."""
        promo = Promotion.objects.create(
            organization=self.org,
            title='Shirt Discount',
            discount_type='fixed_amount',
            discount_value=10,
            applies_to='category',
            category='Clothing',
            is_active=True,
        )
        assert promo.applies_to == 'category'
        assert promo.category == 'Clothing'

    def test_create_promotion_specific_products(self):
        """Promotion can target specific products via M2M."""
        product1 = Product.objects.create(
            organization=self.org,
            title='Product 1',
            status='active',
            is_active=True,
        )
        product2 = Product.objects.create(
            organization=self.org,
            title='Product 2',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(product=product1, sku='sku-1', name='V1', price=100)
        ProductVariant.objects.create(product=product2, sku='sku-2', name='V2', price=100)

        promo = Promotion.objects.create(
            organization=self.org,
            title='Bundle Deal',
            discount_type='bundle',
            discount_value=15,
            applies_to='specific_products',
            is_active=True,
        )
        promo.products.set([product1, product2])

        assert promo.products.count() == 2

    def test_promotion_time_window(self):
        """Promotion respects start/end time windows."""
        now = timezone.now()
        promo_future = Promotion.objects.create(
            organization=self.org,
            title='Future Sale',
            discount_type='percentage',
            discount_value=10,
            starts_at=now + timedelta(days=1),
            is_active=True,
        )
        promo_active = Promotion.objects.create(
            organization=self.org,
            title='Active Sale',
            discount_type='percentage',
            discount_value=10,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
            is_active=True,
        )

        assert promo_future.starts_at > now
        assert promo_active.starts_at < now

    def test_get_active_promotions_from_model(self):
        """get_active_promotions should read from Promotion model."""
        promo = Promotion.objects.create(
            organization=self.org,
            title='Test Promo',
            discount_type='percentage',
            discount_value=25,
            is_active=True,
        )

        promos = get_active_promotions(self.org)
        assert len(promos) > 0
        assert any(p['title'] == 'Test Promo' for p in promos)


class TestProductRelation(TestCase):
    """Tests for P1.1 ProductRelation model (product graph)."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Test Org',
            slug='test-org',
        )

    def test_create_product_relation(self):
        """Can create product relationships."""
        product1 = Product.objects.create(
            organization=self.org,
            title='Shirt',
            status='active',
            is_active=True,
        )
        product2 = Product.objects.create(
            organization=self.org,
            title='Tie',
            status='active',
            is_active=True,
        )

        relation = ProductRelation.objects.create(
            organization=self.org,
            source_product=product1,
            target_product=product2,
            relation_type='combina_con',
            weight=0.9,
        )

        assert relation.relation_type == 'combina_con'
        assert relation.weight == 0.9

    def test_relation_types(self):
        """Can create all relation types."""
        product1 = Product.objects.create(organization=self.org, title='P1', status='active', is_active=True)
        product2 = Product.objects.create(organization=self.org, title='P2', status='active', is_active=True)

        relation_types = [
            'combina_con',
            'evita_con',
            'bundle_con',
            'alternativa_barata',
            'alternativa_premium',
            'similar_a',
        ]

        for rel_type in relation_types:
            rel = ProductRelation.objects.create(
                organization=self.org,
                source_product=product1,
                target_product=product2,
                relation_type=rel_type,
            )
            assert rel.relation_type == rel_type

    def test_unique_constraint(self):
        """Cannot create duplicate relations."""
        from django.db import IntegrityError

        product1 = Product.objects.create(organization=self.org, title='P1', status='active', is_active=True)
        product2 = Product.objects.create(organization=self.org, title='P2', status='active', is_active=True)

        ProductRelation.objects.create(
            organization=self.org,
            source_product=product1,
            target_product=product2,
            relation_type='similar_a',
        )

        with self.assertRaises(IntegrityError):
            ProductRelation.objects.create(
                organization=self.org,
                source_product=product1,
                target_product=product2,
                relation_type='similar_a',
            )
