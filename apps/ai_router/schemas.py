from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class Channel(StrEnum):
    WHATSAPP = 'whatsapp'
    INSTAGRAM = 'instagram'
    WEB = 'web'
    APP = 'app'
    TIKTOK = 'tiktok'
    EMAIL = 'email'
    INTERNAL = 'internal'
    UNKNOWN = 'unknown'


class RiskLevel(StrEnum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class Sentiment(StrEnum):
    POSITIVE = 'positive'
    NEUTRAL = 'neutral'
    NEGATIVE = 'negative'


class Urgency(StrEnum):
    LOW = 'low'
    NORMAL = 'normal'
    HIGH = 'high'


class PolicyStatus(StrEnum):
    ALLOWED = 'allowed'
    RESTRICTED = 'restricted'
    BLOCKED = 'blocked'


class RouteType(StrEnum):
    DIRECT_AI_REPLY = 'direct_ai_reply'
    TRIGGER_FLOW = 'trigger_flow'
    ROUTE_TO_SALES_AGENT = 'route_to_sales_agent'
    ROUTE_TO_MARKETING_AGENT = 'route_to_marketing_agent'
    ROUTE_TO_OPERATIONS_AGENT = 'route_to_operations_agent'
    ESCALATE_TO_HUMAN = 'escalate_to_human'
    REQUEST_CLARIFICATION = 'request_clarification'
    CREATE_TASK = 'create_task'
    CREATE_INSIGHT = 'create_insight'
    BLOCK_ACTION = 'block_action'


class IntentName(StrEnum):
    # Legacy / institutional intents
    CHECK_SUBSIDY = 'check_subsidy'
    REQUEST_CERTIFICATE = 'request_certificate'
    BOOK_APPOINTMENT = 'book_appointment'
    # E-commerce intents
    BUY_INTENT = 'buy_intent'
    ORDER_STATUS = 'order_status'
    PRODUCT_INQUIRY = 'product_inquiry'
    PRICE_INQUIRY = 'price_inquiry'
    RETURN_REQUEST = 'return_request'
    GENERAL_FAQ = 'general_faq'
    # Security
    PROMPT_INJECTION_ATTEMPT = 'prompt_injection_attempt'
    UNKNOWN = 'unknown'


class ModelProfile(StrEnum):
    FAST = 'fast'
    STANDARD = 'standard'
    PREMIUM = 'premium'


class ProviderName(StrEnum):
    OPENAI = 'openai'
    CLAUDE = 'claude'


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Attachment:
    attachment_type: str
    url: str | None = None
    name: str | None = None
    mime_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedEvent:
    tenant_id: str
    channel: Channel
    contact_id: str | None
    conversation_id: str | None
    sender_id: str | None
    message_text: str
    language: str
    timestamp: datetime
    attachments: list[Attachment] = field(default_factory=list)
    structured_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_event: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RiskAssessment:
    level: RiskLevel
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    sanitized_text: str | None = None
    allow_tools: bool = True
    require_human_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IntentClassification:
    intent: IntentName
    confidence: float
    entities: dict[str, Any] = field(default_factory=dict)
    sentiment: Sentiment = Sentiment.NEUTRAL
    urgency: Urgency = Urgency.NORMAL
    recommended_action: str = 'request_clarification'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PolicyDecision:
    status: PolicyStatus
    reasons: list[str] = field(default_factory=list)
    requires_human_approval: bool = False
    allowed_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ModelSelection:
    profile: ModelProfile
    provider: ProviderName | None
    model_name: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PostAction:
    action_type: str
    target: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
