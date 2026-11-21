
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Literal


class LeadCreate(BaseModel):

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid"
    )

    name: str = Field(min_length=2, max_length=100)

    email: EmailStr

    phone: str | None = Field(default=None, max_length=20)

    company: str | None = Field(default=None, max_length=150)

    service: str = Field(min_length=2, max_length=100)

    requirements: str = Field(min_length=10, max_length=3000)

    budget: str | None = Field(default=None, max_length=100)

    preferred_contact: Literal["email", "phone", "whatsapp"] = "email"

    consent: bool


class LeadResponse(BaseModel):

    lead_id: str
    message: str
    status: str
    email: EmailStr
    ai_status: Literal["SUCCESS", "FAILED", "PENDING"]
    email_status: Literal["PENDING", "SENT", "FAILED", "SKIPPED"] = "PENDING"
    email_status_updated: bool = True
    email_error: str | None = None
    email_message_id: str | None = None
    email_thread_id: str | None = None


class HealthResponse(BaseModel):

    status: str
    project: str


class LeadListItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lead_id: str
    name: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    service: str = ""
    requirements: str = ""
    lead_status: str = "NEW"
    budget: str = ""
    consent: bool | str = False
    score: int | None = None
    tier: str | None = None
    intent: str | None = None
    sentiment: str | None = None
    last_interaction: str | None = None
    created_at: str | None = None
    sheet_row: int | None = None


class LeadListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    leads: list[LeadListItem]
    total: int
    page: int
    page_size: int
    crm_synced: bool = True


class LeadDetailResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lead_id: str
    name: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    service: str = ""
    requirements: str = ""
    lead_status: str = "NEW"
    email_status: str = "PENDING"
    ai_status: str = "PENDING"
    budget: str = ""
    consent: bool | str = False
    created_at: str | None = None
    error_message: str = ""
    score: dict | None = None
    score_history: list[dict] = Field(default_factory=list)
    tasks: list[dict] = Field(default_factory=list)
    reminders: list[dict] = Field(default_factory=list)
    workflow_executions: list[dict] = Field(default_factory=list)
    approvals: list[dict] = Field(default_factory=list)
    intelligence_records: list[dict] = Field(default_factory=list)
    email_drafts: list[dict] = Field(default_factory=list)
    activity_timeline: list[dict] = Field(default_factory=list)

