from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Organization
from apps.ecommerce.models import Product, ProductVariant, Promotion
from apps.ecommerce.promotion_engine import PromotionEngine


class PromotionEngineTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Promo Org', slug='promo-org')
        self.product = Product.objects.create(
            organization=self.org,
            title='Camiseta Negra',
            category='Ropa',
            status='active',
            is_active=True,
        )
        ProductVariant.objects.create(product=self.product, sku='cam-1', name='Default', price=100000, stock=10)

    def test_product_scope_percentage_discount(self):
        Promotion.objects.create(
            organization=self.org,
            title='10% off camiseta',
            scope='product',
            discount_type='percentage',
            discount_value=10,
            applies_to='specific_products',
            is_active=True,
        ).products.set([self.product])

        result = PromotionEngine.evaluate_cart(
            organization=self.org,
            lines=[{'product_id': str(self.product.id), 'qty': 1, 'unit_price': 100000, 'category': 'Ropa'}],
        )

        self.assertEqual(result['subtotal'], 100000.0)
        self.assertEqual(result['discount_total'], 10000.0)
        self.assertEqual(result['total'], 90000.0)
        self.assertEqual(len(result['applied_promotions']), 1)

    def test_order_scope_percentage_discount(self):
        Promotion.objects.create(
            organization=self.org,
            title='5% en pedido',
            scope='order',
            discount_type='percentage',
            discount_value=5,
            applies_to='all_products',
            is_active=True,
            min_subtotal=Decimal('50000'),
        )

        result = PromotionEngine.evaluate_cart(
            organization=self.org,
            lines=[{'product_id': str(self.product.id), 'qty': 1, 'unit_price': 100000, 'category': 'Ropa'}],
        )

        self.assertEqual(result['discount_total'], 5000.0)
        self.assertEqual(result['total'], 95000.0)
        self.assertTrue(any(item['scope'] == 'order' for item in result['applied_promotions']))

    def test_shipping_scope_free_shipping(self):
        Promotion.objects.create(
            organization=self.org,
            title='Envio gratis desde 80k',
            scope='shipping',
            discount_type='free_shipping',
            discount_value=0,
            applies_to='all_products',
            is_active=True,
            min_subtotal=Decimal('80000'),
        )

        result = PromotionEngine.evaluate_cart(
            organization=self.org,
            lines=[{'product_id': str(self.product.id), 'qty': 1, 'unit_price': 100000, 'category': 'Ropa'}],
            shipping_amount=12000,
        )

        self.assertEqual(result['shipping_discount_total'], 12000.0)
        self.assertTrue(result['free_shipping'])
        self.assertEqual(result['total_with_shipping'], 100000.0)
