from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class GoogleFormWebhookPayload(BaseModel):
    """
    Incoming payload schema for Google Forms and Google Sheets onFormSubmit webhooks.
    """
    model_config = ConfigDict(
        extra="allow",
        str_strip_whitespace=True
    )

    submission_id: str = Field(
        ...,
        min_length=1,
        max_length=250,
        description="Stable submission identifier (e.g. spreadsheetId_sheetId_rowNumber)"
    )
    spreadsheet_id: str | None = Field(default=None, max_length=200)
    sheet_id: Any | None = None
    sheet_name: str | None = Field(default=None, max_length=150)
    row_number: int | None = Field(default=None, ge=1)
    timestamp: str | None = None
    named_values: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary mapping question labels to answer string or list of strings"
    )


class GoogleFormWebhookResponse(BaseModel):
    """
    Response schema for processed or accepted Google Forms submissions.
    """
    model_config = ConfigDict(extra="ignore")

    status: str
    duplicate: bool = False
    submission_id: str
    lead_id: str | None = None
    message: str
    processing_status: str
    ai_status: str | None = None
    email_status: str = "PENDING"
    draft_id: str | None = None
    approval_id: str | None = None
