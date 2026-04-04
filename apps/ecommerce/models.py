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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        ordering = ['title']


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
