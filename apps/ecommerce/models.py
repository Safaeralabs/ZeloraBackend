import uuid
from django.db import models


class Product(models.Model):
    OFFER_TYPE_CHOICES = [
        ('physical', 'Physical'),
        ('service', 'Service'),
        ('hybrid', 'Hybrid'),
    ]
    PRICE_TYPE_CHOICES = [
        ('fixed', 'Fixed'),
        ('variable', 'Variable'),
        ('quote_required', 'Quote required'),
    ]
    SERVICE_MODE_CHOICES = [
        ('onsite', 'Onsite'),
        ('remote', 'Remote'),
        ('hybrid', 'Hybrid'),
        ('not_applicable', 'Not applicable'),
    ]
    STATUS_CHOICES = [('active', 'Active'), ('draft', 'Draft'), ('archived', 'Archived')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='products'
    )
    title = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    offer_type = models.CharField(max_length=20, choices=OFFER_TYPE_CHOICES, default='physical')
    price_type = models.CharField(max_length=20, choices=PRICE_TYPE_CHOICES, default='fixed')
    service_mode = models.CharField(max_length=20, choices=SERVICE_MODE_CHOICES, default='not_applicable')
    requires_booking = models.BooleanField(default=False)
    requires_shipping = models.BooleanField(default=True)
    service_duration_minutes = models.PositiveIntegerField(default=0)
    capacity = models.PositiveIntegerField(default=0)
    fulfillment_notes = models.TextField(blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    images = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    # P1.1: Enriched product attributes for recommendation engine & storytelling
    subcategory = models.CharField(max_length=100, blank=True)
    occasion = models.JSONField(default=list, blank=True)  # e.g., ["wedding", "dinner", "business"]
    style = models.CharField(max_length=100, blank=True)  # e.g., "casual", "formal", "sporty"
    color = models.CharField(max_length=100, blank=True)  # e.g., "navy blue", "beige"
    material = models.CharField(max_length=100, blank=True)  # e.g., "cotton", "polyester"
    fit = models.CharField(max_length=50, blank=True)  # e.g., "slim", "regular", "oversize"
    formality = models.CharField(max_length=50, blank=True)  # e.g., "formal", "semiformal", "casual"
    target_audience = models.CharField(max_length=100, blank=True)  # e.g., "adult men", "young women"
    is_bestseller = models.BooleanField(default=False)
    popularity_score = models.FloatField(default=0.0)  # 0–100, manual or auto-computed
    embedding_vector = models.JSONField(default=list, blank=True)  # text-embedding-3-small, list of floats

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        ordering = ['title']
        indexes = [
            models.Index(fields=['organization', 'is_bestseller']),
            models.Index(fields=['organization', 'formality']),
            models.Index(fields=['organization', 'is_active']),
        ]


class ProductVariant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    sku = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock = models.IntegerField(default=0)
    reserved = models.IntegerField(default=0)
    duration_minutes = models.PositiveIntegerField(default=0)
    capacity = models.PositiveIntegerField(default=0)
    delivery_mode = models.CharField(max_length=20, default='not_applicable')
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'product_variants'


class InventoryMovement(models.Model):
    TYPE_CHOICES = [
        ('in', 'In'),
        ('out', 'Out'),
        ('adjustment', 'Adjustment'),
        ('reservation', 'Reservation'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='inventory_movements'
    )
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name='movements'
    )
    sku = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    quantity = models.IntegerField()
    reason = models.CharField(max_length=300, blank=True)
    actor = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_movements'
        ordering = ['-created_at']


class Order(models.Model):
    ORDER_KIND_CHOICES = [
        ('purchase', 'Purchase'),
        ('booking', 'Booking'),
        ('quote_request', 'Quote request'),
    ]
    STATUS_CHOICES = [
        ('new', 'New'),
        ('paid', 'Paid'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    CHANNEL_CHOICES = [
        ('ecommerce', 'E-commerce'),
        ('whatsapp', 'WhatsApp'),
        ('instagram', 'Instagram'),
        ('web', 'Web'),
        ('app', 'App Chat'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='orders'
    )
    contact = models.ForeignKey(
        'accounts.Contact', on_delete=models.SET_NULL, null=True, blank=True
    )
    customer_name = models.CharField(max_length=200, blank=True)
    order_kind = models.CharField(max_length=20, choices=ORDER_KIND_CHOICES, default='purchase')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='ecommerce')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    items = models.JSONField(default=list)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='COP')
    scheduled_for = models.DateTimeField(null=True, blank=True)
    service_location = models.CharField(max_length=255, blank=True)
    fulfillment_summary = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']


class Promotion(models.Model):
    """
    P1.1: Promotion model — replaces ChannelConfig.settings['active_promotions'].
    Supports org-level, category-level, and product-specific promotions with time windows.
    """

    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage off'),
        ('fixed_amount', 'Fixed amount off'),
        ('free_shipping', 'Free shipping'),
        ('bundle', 'Bundle deal'),
    ]
    APPLIES_TO_CHOICES = [
        ('all_products', 'All products'),
        ('category', 'Category'),
        ('specific_products', 'Specific products'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='promotions'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Scope: which products this applies to
    applies_to = models.CharField(max_length=30, choices=APPLIES_TO_CHOICES, default='all_products')
    category = models.CharField(max_length=100, blank=True)  # if applies_to='category'
    products = models.ManyToManyField(Product, blank=True, related_name='promotions')  # if applies_to='specific_products'

    # Time window
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'promotions'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['organization', 'is_active']),
        ]


class ProductRelation(models.Model):
    """
    P1.1: Product graph — models relationships between products.
    Supports: combines_with, avoids_with, bundle_with, cheaper_alternative, premium_alternative, similar_to.
    """

    RELATION_TYPE_CHOICES = [
        ('combina_con', 'Combina con'),
        ('evita_con', 'Evita con'),
        ('bundle_con', 'Bundle con'),
        ('alternativa_barata', 'Alternativa barata'),
        ('alternativa_premium', 'Alternativa premium'),
        ('similar_a', 'Similar a'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='product_relations'
    )
    source_product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='relations_as_source'
    )
    target_product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='relations_as_target'
    )
    relation_type = models.CharField(max_length=30, choices=RELATION_TYPE_CHOICES)
    weight = models.FloatField(default=1.0)  # relevance 0–1
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_relations'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['source_product', 'target_product', 'relation_type'],
                name='uniq_product_relation',
            )
        ]
        indexes = [
            models.Index(fields=['organization', 'source_product']),
        ]
