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
    requires_size = models.BooleanField(
        default=False,
        help_text='Needs a size/measurement from the customer before it can be confirmed (rings, clothing with fixed sizing, etc.)',
    )
    made_to_order = models.BooleanField(
        default=False,
        help_text='Custom/handmade per order rather than sold from fixed stock (e.g. personalized jewelry).',
    )
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
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('partially_paid', 'Partially paid'),
        ('refunded', 'Refunded'),
        ('voided', 'Voided'),
    ]
    FULFILLMENT_STATUS_CHOICES = [
        ('unfulfilled', 'Unfulfilled'),
        ('partial', 'Partial'),
        ('fulfilled', 'Fulfilled'),
        ('returned', 'Returned'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='orders'
    )
    order_number = models.PositiveIntegerField(default=0, db_index=True)
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

    # Financial breakdown
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Payment & fulfillment status
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    fulfillment_status = models.CharField(max_length=20, choices=FULFILLMENT_STATUS_CHOICES, default='unfulfilled')

    # Addresses
    shipping_address = models.JSONField(default=dict, blank=True)
    billing_address = models.JSONField(default=dict, blank=True)

    # Extra metadata
    payment_method = models.CharField(max_length=50, blank=True)
    tags = models.JSONField(default=list, blank=True)
    tracking_number = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_orders'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'order_number'],
                name='uniq_org_order_number',
                condition=models.Q(order_number__gt=0),
            )
        ]

    @classmethod
    def next_order_number(cls, organization_id):
        from django.db.models import Max
        max_num = (
            cls.objects.filter(organization_id=organization_id)
            .select_for_update()
            .aggregate(Max('order_number'))['order_number__max']
            or 0
        )
        return max_num + 1


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
    SCOPE_CHOICES = [
        ('product', 'Product discount'),
        ('order', 'Order discount'),
        ('shipping', 'Shipping discount'),
    ]
    TRIGGER_TYPE_CHOICES = [
        ('automatic', 'Automatic'),
        ('code', 'Discount code'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='promotions'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='product')
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_TYPE_CHOICES, default='automatic')
    code = models.CharField(max_length=80, blank=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    min_qty = models.PositiveIntegerField(default=0)
    buy_x_qty = models.PositiveIntegerField(default=0)
    get_y_qty = models.PositiveIntegerField(default=0)
    combinable = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)

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
            models.Index(fields=['organization', 'scope', 'is_active']),
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

    # Each relation implies a reverse relation on the target product. Symmetric
    # types map to themselves; the premium/budget pair maps to each other (if B
    # is a premium alternative of A, then A is a budget alternative of B). The
    # ViewSet keeps both rows in sync so the recommendation engine — which only
    # traverses source_product — resolves the graph in both directions and the
    # merchant never has to think about direction.
    INVERSE_RELATION_TYPE = {
        'combina_con': 'combina_con',
        'bundle_con': 'bundle_con',
        'similar_a': 'similar_a',
        'evita_con': 'evita_con',
        'alternativa_premium': 'alternativa_barata',
        'alternativa_barata': 'alternativa_premium',
    }

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


class OrderLineItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='line_items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=200)
    sku = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    offer_type = models.CharField(max_length=20, default='physical')
    properties = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'order_line_items'
        ordering = ['id']


class OrderEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ('created', 'Order created'),
        ('paid', 'Payment received'),
        ('partially_paid', 'Partial payment'),
        ('processing', 'Processing started'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('note_added', 'Note added'),
        ('tag_added', 'Tag added'),
        ('tag_removed', 'Tag removed'),
        ('edited', 'Order edited'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    message = models.TextField(blank=True)
    actor = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'order_events'
        ordering = ['created_at']
