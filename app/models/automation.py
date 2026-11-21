from datetime import datetime, timezone
from typing import Any, Literal
import zoneinfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_TIMEZONE = "Asia/Kolkata"
KOLKATA_TZ = zoneinfo.ZoneInfo(DEFAULT_TIMEZONE)


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def validate_and_normalize_timezone(tz_name: str | None) -> str:
    """Validate timezone string and return normalized name."""
    if not tz_name or not tz_name.strip():
        return DEFAULT_TIMEZONE
    name = tz_name.strip()
    try:
        zoneinfo.ZoneInfo(name)
        return name
    except Exception as exc:
        raise ValueError(f"Invalid timezone: '{name}'") from exc


def to_utc_iso(dt_or_str: datetime | str | None, tz_name: str = DEFAULT_TIMEZONE) -> str:
    """
    Normalize a datetime or ISO string to UTC ISO-8601 format.
    If the datetime is timezone-naive, it is interpreted in the given tz_name.
    """
    if dt_or_str is None:
        return utc_now_iso()

    tz = zoneinfo.ZoneInfo(validate_and_normalize_timezone(tz_name))

    if isinstance(dt_or_str, str):
        val = dt_or_str.strip()
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception as exc:
            raise ValueError(
                f"Invalid ISO-8601 datetime: '{dt_or_str}'. "
                "Must be a valid ISO-8601 string (e.g. 2026-11-20T16:00:00Z or 2026-11-20T16:00:00)."
            ) from exc
    else:
        dt = dt_or_str

    if dt.tzinfo is None:
        # Timezone-naive input interpreted using the supplied valid timezone
        dt = dt.replace(tzinfo=tz)

    return dt.astimezone(timezone.utc).isoformat()


def to_kolkata_iso(utc_iso_string: str) -> str:
    """Convert a UTC ISO timestamp to Asia/Kolkata ISO timestamp for display."""
    val = utc_iso_string.strip()
    dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
    return dt.astimezone(KOLKATA_TZ).isoformat()


# Enums & Types
ScoreTier = Literal["HOT", "WARM", "COLD"]
TaskPriority = Literal["LOW", "MEDIUM", "HIGH", "URGENT"]
TaskStatus = Literal["SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
TaskChannel = Literal["EMAIL", "CALL", "MEETING", "MANUAL"]
ReminderStatus = Literal["PENDING", "SENT", "DISMISSED", "FAILED"]
ReminderChannel = Literal["INTERNAL_LOG", "NOTIFICATION"]
WorkflowTriggerType = Literal[
    "LEAD_CREATED",
    "INTENT_CLASSIFIED",
    "SCORE_UPDATED",
    "SCHEDULED_TIME",
    "MANUAL",
]
WorkflowActionType = Literal[
    "CREATE_FOLLOW_UP",
    "CREATE_REMINDER",
    "UPDATE_LEAD_PRIORITY",
    "REQUEST_HUMAN_APPROVAL",
    "CREATE_INTERNAL_NOTIFICATION",
]
WorkflowExecutionStatus = Literal[
    "PENDING",
    "AWAITING_APPROVAL",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "SKIPPED",
]
ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED"]
ApprovalAction = Literal["APPROVE", "REJECT"]
JobStatus = Literal["PENDING", "PROCESSING", "COMPLETED", "FAILED", "CANCELLED"]


# 1. Lead Score Models
class LeadScoreCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "lead_id": "LF-101",
                "score": 85,
                "tier": "HOT",
                "factors": {
                    "intent": "MEETING_REQUEST",
                    "sentiment": "POSITIVE",
                    "budget": "$10,000",
                },
                "version": "v2-deterministic",
                "idempotency_key": "score-key-001",
            }
        },
    )

    lead_id: str = Field(min_length=1, max_length=100)
    score: int = Field(ge=0, le=100)
    tier: ScoreTier
    factors: dict[str, Any] = Field(default_factory=dict)
    version: str = Field(default="v2-deterministic", max_length=50)
    idempotency_key: str | None = Field(default=None, max_length=120)


class LeadScoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    lead_id: str
    score: int
    tier: ScoreTier
    factors: dict[str, Any]
    version: str
    idempotency_key: str | None
    created_at: str
    updated_at: str


class LeadScoreLeaderboardItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    name: str = ""
    email: str = ""
    company: str = ""
    score: int
    tier: ScoreTier
    complaint_attention_flag: bool = False
    factors_summary: dict[str, int] = Field(default_factory=dict)
    calculated_at: str


class LeadScoreRecalculateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recalculated: int
    lead_ids: list[str]
    results: list[LeadScoreResponse]


# 2. Follow-Up Task Models
class FollowUpTaskCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "lead_id": "LF-101",
                "title": "Send enterprise proposal",
                "description": "Follow up on pricing discussion and include SLA terms",
                "scheduled_for": "2026-11-21T10:00:00Z",
                "timezone": "Asia/Kolkata",
                "priority": "HIGH",
                "channel": "EMAIL",
                "generate_reminder": True,
                "reminder_minutes_before": 15,
                "metadata": {"inquiry_type": "enterprise"},
                "idempotency_key": "task-key-001",
            }
        },
    )

    lead_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    scheduled_for: str = Field(description="ISO 8601 timestamp")
    timezone: str = Field(default=DEFAULT_TIMEZONE, max_length=50)
    priority: TaskPriority = "MEDIUM"
    channel: TaskChannel = "EMAIL"
    generate_reminder: bool = False
    reminder_minutes_before: int = Field(default=15, ge=0, le=10080)
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=120)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        return validate_and_normalize_timezone(v)

    @field_validator("scheduled_for")
    @classmethod
    def validate_scheduled_for(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("scheduled_for cannot be empty")
        val = v.strip()
        try:
            datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception as exc:
            raise ValueError(
                f"Invalid ISO-8601 datetime '{v}'. "
                "Must be a valid ISO-8601 timestamp (e.g. 2026-11-20T16:00:00Z or 2026-11-20T16:00:00)."
            ) from exc
        return val


class FollowUpTaskUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "status": "IN_PROGRESS",
                "description": "Reviewed requirements; drafting proposal",
                "priority": "URGENT",
            }
        },
    )

    status: TaskStatus | None = None
    description: str | None = Field(default=None, max_length=2000)
    priority: TaskPriority | None = None
    scheduled_for: str | None = None
    timezone: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("timezone")
    @classmethod
    def validate_tz(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_and_normalize_timezone(v)
        return v

    @field_validator("scheduled_for")
    @classmethod
    def validate_sched(cls, v: str | None) -> str | None:
        if v is not None:
            val = v.strip()
            try:
                datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception as exc:
                raise ValueError(f"Invalid ISO-8601 datetime: '{v}'") from exc
            return val
        return v


class FollowUpTaskReschedule(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "scheduled_for": "2026-11-22T14:30:00Z",
                "timezone": "Asia/Kolkata",
            }
        },
    )

    scheduled_for: str
    timezone: str = DEFAULT_TIMEZONE

    @field_validator("timezone")
    @classmethod
    def validate_tz(cls, v: str) -> str:
        return validate_and_normalize_timezone(v)

    @field_validator("scheduled_for")
    @classmethod
    def validate_sched(cls, v: str) -> str:
        val = v.strip()
        try:
            datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception as exc:
            raise ValueError(f"Invalid ISO-8601 datetime: '{v}'") from exc
        return val


class FollowUpTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    lead_id: str
    title: str
    description: str
    scheduled_for: str
    scheduled_for_local: str = ""
    timezone: str
    priority: TaskPriority
    status: TaskStatus
    channel: TaskChannel
    metadata: dict[str, Any]
    idempotency_key: str | None
    completed_at: str | None = None
    created_at: str
    updated_at: str


# 3. Reminder Models
class ReminderCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "lead_id": "LF-101",
                "task_id": "task_12345",
                "title": "Prepare discovery questions",
                "remind_at": "2026-11-21T09:45:00Z",
                "timezone": "Asia/Kolkata",
                "recipient": "sales_lead@example.com",
                "channel": "INTERNAL_LOG",
                "idempotency_key": "rem-key-001",
            }
        },
    )

    lead_id: str = Field(min_length=1, max_length=100)
    task_id: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    remind_at: str = Field(description="ISO 8601 timestamp")
    timezone: str = Field(default=DEFAULT_TIMEZONE, max_length=50)
    recipient: str = Field(default="", max_length=200)
    channel: ReminderChannel = "INTERNAL_LOG"
    idempotency_key: str | None = Field(default=None, max_length=120)

    @field_validator("timezone")
    @classmethod
    def validate_tz(cls, v: str) -> str:
        return validate_and_normalize_timezone(v)

    @field_validator("remind_at")
    @classmethod
    def validate_remind_at(cls, v: str) -> str:
        val = v.strip()
        try:
            datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception as exc:
            raise ValueError(f"Invalid ISO-8601 datetime: '{v}'") from exc
        return val


class ReminderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    lead_id: str
    task_id: str | None
    title: str
    remind_at: str
    remind_at_local: str = ""
    timezone: str
    status: ReminderStatus
    recipient: str
    channel: ReminderChannel
    idempotency_key: str | None
    created_at: str
    updated_at: str


# 4. Workflow Rule Models
class WorkflowRuleCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "name": "Meeting Request Auto-Followup",
                "trigger_type": "INTENT_CLASSIFIED",
                "conditions": {
                    "intent_category": "MEETING_REQUEST",
                    "tier": ["HOT", "WARM"],
                },
                "actions": [
                    {
                        "type": "CREATE_FOLLOW_UP",
                        "params": {
                            "title": "Schedule discovery meeting",
                            "delay_hours": 4,
                            "priority": "URGENT",
                            "channel": "EMAIL",
                        },
                    }
                ],
                "requires_approval": True,
                "is_active": True,
            }
        },
    )

    name: str = Field(min_length=1, max_length=150)
    trigger_type: WorkflowTriggerType
    conditions: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    requires_approval: bool = True
    is_active: bool = True


class WorkflowRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=150)
    conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None
    requires_approval: bool | None = None
    is_active: bool | None = None


class WorkflowRuleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    trigger_type: WorkflowTriggerType
    conditions: dict[str, Any]
    actions: list[dict[str, Any]]
    requires_approval: bool
    is_active: bool
    is_deleted: bool = False
    created_at: str
    updated_at: str


# 5. Workflow Execution Models
class WorkflowExecutionCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "rule_id": "rule_12345",
                "lead_id": "LF-101",
                "trigger_event": "MANUAL_TRIGGER",
                "context_data": {"user": "admin", "reason": "High interest in demo"},
                "idempotency_key": "exec-key-001",
            }
        },
    )

    rule_id: str = Field(min_length=1, max_length=100)
    lead_id: str = Field(min_length=1, max_length=100)
    trigger_event: str = Field(min_length=1, max_length=100)
    context_data: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=120)


class WorkflowTriggerRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "trigger_type": "MANUAL",
                "lead_id": "LF-101",
                "context_data": {"source": "manual_review"},
                "idempotency_key": "wf-trigger-001",
            }
        },
    )

    trigger_type: WorkflowTriggerType = "MANUAL"
    lead_id: str = Field(min_length=1, max_length=100)
    context_data: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=120)


class RuleTriggerRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "lead_id": "LF-101",
                "context_data": {"score": 85},
                "idempotency_key": "rule-trig-001",
            }
        },
    )

    lead_id: str = Field(min_length=1, max_length=100)
    context_data: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=120)


class WorkflowExecutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rule_id: str
    lead_id: str
    trigger_event: str
    status: WorkflowExecutionStatus
    context_data: dict[str, Any]
    result_data: dict[str, Any] | None
    error_message: str | None
    idempotency_key: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str


# 6. Approval Request Models
class ApprovalRequestCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "lead_id": "LF-101",
                "action_type": "SEND_EMAIL",
                "action_payload": {
                    "subject": "Follow up on demo",
                    "recipient": "customer@example.com",
                    "body_preview": "Hi Alice, following up on our call...",
                },
                "requested_by": "workflow_engine",
                "idempotency_key": "appr-key-001",
            }
        },
    )

    workflow_execution_id: str | None = Field(default=None, max_length=100)
    lead_id: str = Field(min_length=1, max_length=100)
    action_type: str = Field(min_length=1, max_length=100)
    action_payload: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = Field(default="system", max_length=100)
    expires_at: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=120)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "action": "APPROVE",
                "reviewed_by": "operator@example.com",
                "rejection_reason": None,
            }
        },
    )

    action: ApprovalAction
    reviewed_by: str = Field(min_length=1, max_length=100)
    rejection_reason: str | None = Field(default=None, max_length=500)


class ApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    workflow_execution_id: str | None
    lead_id: str
    action_type: str
    action_payload: dict[str, Any]
    status: ApprovalStatus
    requested_by: str
    reviewed_by: str | None
    reviewed_at: str | None
    rejection_reason: str | None
    expires_at: str | None = None
    idempotency_key: str | None
    created_at: str
    updated_at: str


class ApprovalExpireResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expired_count: int
    expired_ids: list[str]


# 7. Audit Log Models
class AuditLogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    entity_type: str
    entity_id: str
    lead_id: str | None
    action: str
    actor: str
    details: dict[str, Any]
    ip_address: str | None
    created_at: str


# 8. Background Job Models
class JobCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "job_type": "PROCESS_REMINDER",
                "payload": {"reminder_id": "rem_123"},
                "scheduled_at": "2026-11-21T09:45:00Z",
                "max_retries": 3,
                "idempotency_key": "job-key-001",
            }
        },
    )

    job_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    scheduled_at: str | None = None
    max_retries: int = Field(default=3, ge=0, le=10)
    idempotency_key: str | None = Field(default=None, max_length=120)


class JobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    job_type: str
    payload: dict[str, Any]
    scheduled_at: str
    status: JobStatus
    attempts: int
    max_retries: int
    locked_until: str | None
    last_error: str | None
    idempotency_key: str | None
    created_at: str
    updated_at: str


# 9. Health & Status Models
class AutomationHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    database: str
    worker_running: bool
    project: str


class AutomationStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    database: str
    worker_running: bool
    default_timezone: str
    counts: dict[str, int]


# 10. Email Draft & Delivery Models
class EmailDraftResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    lead_id: str
    submission_id: str | None = None
    recipient: str
    subject: str
    body: str
    html_body: str | None = None
    preferred_contact: str = "email"
    consent: bool = True
    status: str
    approval_id: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    sent_at: str | None = None
    sent_by: str | None = None
    gmail_message_id: str | None = None
    gmail_thread_id: str | None = None
    error_message: str | None = None
    error_code: str | None = None
    retry_count: int = 0
    idempotency_key: str | None = None
    created_at: str
    updated_at: str


class EmailDraftListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    drafts: list[EmailDraftResponse]
    total: int
    page: int
    page_size: int


class EmailSendResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool
    status: str
    draft_id: str
    message_id: str | None = None
    thread_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    ambiguous: bool = False


class EmailDraftDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    decision_notes: str | None = None
    rejection_reason: str | None = None
