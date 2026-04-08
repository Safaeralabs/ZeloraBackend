import uuid
from django.db import models


class MetricsSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='metrics'
    )
    date = models.DateField()
    canal = models.CharField(max_length=20)
    total_conversations = models.IntegerField(default=0)
    resolved = models.IntegerField(default=0)
    escalated = models.IntegerField(default=0)
    avg_response_time_s = models.FloatField(default=0)
    csat_score = models.FloatField(default=0)
    ai_handled = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'metrics_snapshots'
        unique_together = ['organization', 'date', 'canal']
        ordering = ['-date']
        indexes = [models.Index(fields=['organization', 'date'])]


class LearningCandidate(models.Model):
    KIND_CHOICES = [
        ('faq', 'FAQ'),
        ('winning_reply', 'Winning reply'),
        ('objection', 'Objection'),
        ('estilo_comunicacion', 'Estilo de comunicación'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='learning_candidates'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation', on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_candidates'
    )
    kind = models.CharField(max_length=40, choices=KIND_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    title = models.CharField(max_length=255)
    source_question = models.TextField(blank=True)
    proposed_answer = models.TextField(blank=True)
    fingerprint = models.CharField(max_length=64)
    confidence = models.FloatField(default=0.0)
    evidence_count = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(default=dict, blank=True)
    approved_article = models.ForeignKey(
        'knowledge_base.KBArticle', on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_candidates'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_learning_candidates'
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['organization', 'kind', 'fingerprint'], name='uniq_learning_candidate_per_org')
        ]
        indexes = [
            models.Index(fields=['organization', 'status', 'kind']),
            models.Index(fields=['organization', 'updated_at']),
        ]


class DocumentExtractionCandidate(models.Model):
    KIND_CHOICES = [
        ('service', 'Service'),
        ('pricing_rule', 'Pricing rule'),
        ('policy', 'Policy'),
        ('flow_hint', 'Flow hint'),
        ('ai_summary', 'AI Summary'),
        ('ai_qa', 'AI Q&A'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='document_extraction_candidates'
    )
    source_document = models.ForeignKey(
        'knowledge_base.KBDocument', on_delete=models.CASCADE, related_name='extraction_candidates'
    )
    kind = models.CharField(max_length=40, choices=KIND_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    fingerprint = models.CharField(max_length=64)
    confidence = models.FloatField(default=0.0)
    metadata = models.JSONField(default=dict, blank=True)
    approved_article = models.ForeignKey(
        'knowledge_base.KBArticle', on_delete=models.SET_NULL, null=True, blank=True, related_name='document_extraction_candidates'
    )
    approved_product = models.ForeignKey(
        'ecommerce.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='document_extraction_candidates'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_document_extraction_candidates'
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'kind', 'fingerprint'],
                name='uniq_doc_extraction_candidate_per_org',
            )
        ]
        indexes = [
            models.Index(fields=['organization', 'status', 'kind']),
            models.Index(fields=['organization', 'updated_at']),
        ]
