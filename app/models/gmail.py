from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


IntentCategory = Literal[
    "INTERESTED",
    "NOT_INTERESTED",
    "FOLLOW_UP",
    "MEETING_REQUEST",
    "PRICING_INQUIRY",
    "INFORMATION_REQUEST",
    "NEGOTIATION",
    "COMPLAINT",
    "OUT_OF_OFFICE",
    "OTHER",
]
Sentiment = Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED"]
MatchStatus = Literal["MATCHED", "UNMATCHED", "IGNORED", "AMBIGUOUS"]
ClassificationStatus = Literal[
    "PENDING", "ANALYZING", "SUCCESS", "FAILED", "SKIPPED"
]


class GmailExtractedInformation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_intent: str = Field(max_length=1000)
    important_requirements: list[str]
    mentioned_budget: str | None
    mentioned_timeline: str | None
    requested_meeting_dates: list[str]
    customer_questions: list[str]
    customer_commitments: list[str]


class GmailIntelligenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_category: IntentCategory
    sentiment: Sentiment
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(max_length=1200)
    extracted_information: GmailExtractedInformation
    action_items: list[str]
    suggested_next_step: str = Field(max_length=1000)


class GmailMessage(BaseModel):
    message_id: str = Field(min_length=1)
    thread_id: str = ""
    sender_email: str = ""
    sender_name: str = ""
    recipient_email: str = ""
    subject: str = ""
    received_timestamp: str = ""
    internal_date: int = 0
    snippet: str = ""
    labels: list[str] = Field(default_factory=list)
    unread: bool = True


class GmailMessageListItem(BaseModel):
    message_id: str = Field(min_length=1)
    sender_email: str = ""
    sender_name: str = ""
    recipient_email: str = ""
    subject: str = ""
    received_timestamp: str = ""
    snippet: str = ""
    unread: bool = True


class GmailMessageListResponse(BaseModel):
    messages: list[GmailMessageListItem]
    page: int
    page_size: int
    total: int


class GmailMatchResponse(BaseModel):
    matched: int
    unmatched: int
    ambiguous: int
    ignored: int
    processed: int


class GmailAnalyzeRequest(BaseModel):
    batch_size: int = Field(default=20, ge=1, le=100)
    force_reanalysis: bool = False


class GmailAnalyzeResponse(BaseModel):
    requested: int
    succeeded: int
    failed: int
    skipped: int


class GmailIntelligenceDetail(BaseModel):
    message_id: str
    lead_id: str | None = None
    match_status: MatchStatus
    ignore_reason: str | None = None
    classification_status: ClassificationStatus
    intent_category: IntentCategory | None = None
    sentiment: Sentiment | None = None
    confidence: float | None = None
    summary: str | None = None
    extracted_information: dict[str, object] = Field(default_factory=dict)
    action_items: list[str] = Field(default_factory=list)
    suggested_next_step: str | None = None
    analysis_error: str | None = None
    analyzed_at: str | None = None
    created_at: str
    updated_at: str
    analysis_history: list[dict[str, object]] = Field(default_factory=list)


class GmailIntelligenceOverview(BaseModel):
    total_synchronized_messages: int
    total_eligible_messages: int
    matched_messages: int
    unmatched_messages: int
    ignored_messages: int
    ambiguous_messages: int
    analyzed_messages: int
    pending_analyses: int
    failed_analyses: int
    intent_category_counts: dict[str, int]
    sentiment_counts: dict[str, int]


class LeadCommunicationItem(BaseModel):
    message_id: str
    received_timestamp: str
    subject: str
    sender: str
    snippet: str
    intent_category: IntentCategory | None = None
    sentiment: Sentiment | None = None
    summary: str | None = None
    suggested_next_action: str | None = None
    analysis_status: ClassificationStatus


class LeadCommunicationHistory(BaseModel):
    lead_id: str
    lead_name: str
    lead_email: str
    total_matched_messages: int
    latest_message_timestamp: str | None = None
    page: int
    page_size: int
    messages: list[LeadCommunicationItem]
