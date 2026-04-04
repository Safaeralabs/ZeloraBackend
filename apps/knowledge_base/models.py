"""
Knowledge Base models — KBArticle (editable content), KBDocument (uploaded files).
Used by AI RAG pipeline and the Knowledge Base module in the frontend.
"""
import uuid
from django.db import models


class KBArticle(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    # Purpose controls how the Sales Agent uses this article.
    # faq          → general Q&A, always injected in snapshots
    # objection    → how to handle specific buyer objections (pulled on checkout_blocked / lost stages)
    # closing      → closing language / techniques (pulled on intent_to_buy / follow_up stages)
    # brand_voice  → on-brand example responses (pulled every message alongside faq)
    # policy       → business policies — payments, returns, shipping (pulled when customer asks)
    # product_context → deep product knowledge (pulled on considering stage)
    PURPOSE_CHOICES = [
        ('faq', 'FAQ General'),
        ('objection', 'Manejo de Objeción'),
        ('closing', 'Técnica de Cierre'),
        ('brand_voice', 'Voz de Marca'),
        ('policy', 'Política del Negocio'),
        ('product_context', 'Contexto de Producto'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='kb_articles'
    )
    author = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )

    title = models.CharField(max_length=300)
    content = models.TextField()
    category = models.CharField(max_length=100, blank=True)
    purpose = models.CharField(max_length=30, choices=PURPOSE_CHOICES, default='faq', blank=True)
    tags = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    visits = models.PositiveIntegerField(default=0)

    # Embedding vector for semantic search (list of floats — OpenAI text-embedding-3-small)
    embedding_vector = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kb_articles'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['organization', 'category']),
            models.Index(fields=['organization', 'purpose']),
        ]

    def __str__(self):
        return self.title


class KBDocument(models.Model):
    """
    Uploaded file attached to the knowledge base.
    Processed asynchronously to extract text and generate embeddings.
    """
    PROCESSING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='kb_documents'
    )
    article = models.ForeignKey(
        KBArticle, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents'
    )

    # File metadata
    filename = models.CharField(max_length=255)
    file = models.FileField(upload_to='kb_documents/')
    file_size = models.PositiveIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)

    # AI processing
    processing_status = models.CharField(
        max_length=20, choices=PROCESSING_STATUS_CHOICES, default='pending', db_index=True
    )
    processed = models.BooleanField(default=False)  # Alias for processing_status == 'ready'
    is_active = models.BooleanField(default=True)

    # Extracted content + embedding
    extracted_text = models.TextField(blank=True)
    embedding = models.JSONField(default=dict, blank=True)  # Word-freq or OpenAI vector

    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kb_documents'
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['organization', 'processing_status']),
        ]

    def __str__(self):
        return self.filename

    def save(self, *args, **kwargs):
        # Keep `processed` flag in sync with `processing_status`
        self.processed = self.processing_status == 'ready'
        super().save(*args, **kwargs)
