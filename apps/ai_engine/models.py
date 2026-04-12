"""
AI Engine models — AI memory, tasks, insights, performance tracking.
Supports the AI Workspace module in the frontend.
"""
import uuid
from django.db import models
from django.conf import settings


class AIMemoryEntry(models.Model):
    """
    Persistent AI memory scoped to an organization.
    Used to give the AI context across conversations (e.g., company-specific knowledge,
    recurring user preferences, past resolutions).
    """
    TYPE_CHOICES = [
        ('fact', 'Fact'),
        ('preference', 'Preference'),
        ('resolution', 'Resolved Case'),
        ('escalation', 'Escalation Pattern'),
        ('faq', 'FAQ'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='ai_memories'
    )
    memory_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='fact')
    key = models.CharField(max_length=200)
    value = models.TextField()
    source_conversation = models.ForeignKey(
        'conversations.Conversation', on_delete=models.SET_NULL, null=True, blank=True
    )
    confidence = models.FloatField(default=1.0)  # 0.0 - 1.0
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_memory_entries'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['organization', 'memory_type']),
            models.Index(fields=['organization', 'is_active']),
        ]

    def __str__(self):
        return f'[{self.memory_type}] {self.key[:80]}'


class AITask(models.Model):
    """
    Background AI task tracking (e.g., "summarize all unresolved conversations",
    "generate weekly report", "refresh KB embeddings").
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='ai_tasks'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    task_type = models.CharField(max_length=100)  # e.g. 'summarize', 'score_qa', 'embed_kb'
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    celery_task_id = models.CharField(max_length=200, blank=True)  # Track Celery task ID
    input_data = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    progress_pct = models.PositiveSmallIntegerField(default=0)  # 0-100
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ai_tasks'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
        ]

    def __str__(self):
        return f'{self.name} [{self.status}]'


class AIInsight(models.Model):
    """
    AI-generated insights for the organization (e.g., "70% of escalations happen on Monday mornings",
    "Top unresolved intent: PQRS", "Average CSAT dropping in WhatsApp channel").
    """
    CATEGORY_CHOICES = [
        ('performance', 'Performance'),
        ('channel', 'Channel'),
        ('intent', 'Intent Pattern'),
        ('agent', 'Agent'),
        ('customer', 'Customer'),
        ('operations', 'Operations'),
    ]
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
        ('positive', 'Positive'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='ai_insights'
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='info')
    title = models.CharField(max_length=300)
    description = models.TextField()
    metric_value = models.FloatField(null=True, blank=True)
    metric_delta = models.FloatField(null=True, blank=True)  # Change vs previous period
    action_suggested = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # Insights can expire

    class Meta:
        db_table = 'ai_insights'
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['organization', 'category']),
            models.Index(fields=['organization', 'is_read']),
        ]

    def __str__(self):
        return f'[{self.severity.upper()}] {self.title}'


class SalesAgentLog(models.Model):
    """
    Structured audit log for every Sales Agent invocation.
    Captures funnel stage, decision, actions and context used.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='sales_agent_logs'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation', on_delete=models.CASCADE, related_name='sales_agent_logs'
    )
    stage = models.CharField(max_length=30)
    confidence = models.FloatField(default=0.0)
    decision = models.CharField(max_length=30)
    handoff_needed = models.BooleanField(default=False)
    handoff_reason = models.CharField(max_length=200, blank=True)
    products_shown = models.JSONField(default=list)
    recommended_actions = models.JSONField(default=list)
    context_used = models.JSONField(default=dict)
    # P2.4: Evaluation and channel tracking
    evaluation_score = models.FloatField(null=True, blank=True)  # 0-1, from evaluator
    evaluation_flags = models.JSONField(default=list, blank=True)  # list of flags from evaluator
    channel = models.CharField(max_length=30, blank=True)  # whatsapp, web, instagram, email, telegram
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sales_agent_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'stage']),
            models.Index(fields=['conversation']),
        ]

    def __str__(self):
        return f'[{self.stage}] {self.decision} @ {str(self.conversation_id)[:8]}'


class AIAgent(models.Model):
    """
    Configurable AI functional agent scoped to an organization.
    Represents a specialized business role (sales, marketing, operations)
    that the AI Router can activate per conversation context.
    """
    AGENT_TYPE_CHOICES = [
        ('sales', 'Sales Agent'),
        ('marketing', 'Marketing Agent'),
        ('operations', 'Operations Agent'),
        ('support', 'Support Agent'),
    ]
    PROVIDER_CHOICES = [
        ('openai', 'OpenAI'),
        ('claude', 'Claude'),
        ('heuristic', 'Heuristic'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='ai_agents'
    )
    agent_type = models.CharField(max_length=20, choices=AGENT_TYPE_CHOICES)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='openai')
    model = models.CharField(max_length=100, default='gpt-4o-mini')
    system_prompt = models.TextField(blank=True)
    tools = models.JSONField(default=list, blank=True)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_agents'
        unique_together = ['organization', 'agent_type']
        ordering = ['agent_type']

    def __str__(self):
        return f'{self.get_agent_type_display()} — {self.organization}'


class AIPerformanceLog(models.Model):
    """
    Tracks AI model performance metrics over time.
    Used in the AI Workspace > Performance tab.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='ai_performance_logs'
    )
    date = models.DateField()
    model_name = models.CharField(max_length=100, default='gpt-4o')
    total_calls = models.PositiveIntegerField(default=0)
    successful_calls = models.PositiveIntegerField(default=0)
    failed_calls = models.PositiveIntegerField(default=0)
    avg_latency_ms = models.FloatField(default=0.0)
    total_tokens_in = models.PositiveIntegerField(default=0)
    total_tokens_out = models.PositiveIntegerField(default=0)
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    bot_resolution_rate = models.FloatField(default=0.0)  # % conversations resolved by bot
    avg_confidence = models.FloatField(default=0.0)

    class Meta:
        db_table = 'ai_performance_logs'
        unique_together = ['organization', 'date', 'model_name']
        ordering = ['-date']


class OpenAIUsageLog(models.Model):
    """
    Per-call OpenAI usage log: tokens, cost, latency, feature.
    Used to track spend and debug performance per feature.
    """
    FEATURE_CHOICES = [
        ('sales_agent', 'Sales Agent'),
        ('learning', 'Learning Engine'),
        ('style_extraction', 'Style Extraction'),
        ('embedding', 'Embedding'),
        ('playbook_synthesis', 'Playbook Synthesis'),
        ('direct_reply', 'Direct Reply'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='openai_usage_logs'
    )
    feature = models.CharField(max_length=40, choices=FEATURE_CHOICES, default='other', db_index=True)
    model_name = models.CharField(max_length=100)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'openai_usage_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'created_at']),
            models.Index(fields=['organization', 'feature', 'created_at']),
        ]
