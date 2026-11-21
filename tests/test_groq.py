import json
import sqlite3
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest
from groq import (
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.models.ai_response import AIEmailResponse
from app.models.lead import LeadCreate
from app.services.automation_service import AutomationService
from app.services.automation_store import AutomationStore
from app.services.groq_service import (
    GroqGenerationError,
    RecoverableGenerationError,
    UnrecoverableGenerationError,
    generate_personalized_email,
    is_recoverable_error,
)


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    """Bypass real time.sleep during retry tests for instant execution."""
    monkeypatch.setattr("time.sleep", lambda _: None)


@pytest.fixture
def sample_lead():
    return LeadCreate(
        name="Priya Patel",
        email="priya.demo@example.com",
        phone="9876543210",
        company="Digital Solutions",
        service="Website Development",
        requirements=(
            "I need a responsive business website with an admin dashboard "
            "and customer enquiry management."
        ),
        budget="25000-50000",
        preferred_contact="email",
        consent=True,
    )


@pytest.fixture
def valid_ai_json():
    return json.dumps({
        "subject": "Proposal for Website Development - Digital Solutions",
        "body": (
            "Dear Priya,\n\n"
            "Thank you for contacting us regarding your website development needs. "
            "We can build a modern responsive business website with an admin dashboard.\n\n"
            "Best regards,\nLeadFlow Team"
        ),
        "lead_summary": "Customer requested responsive business website with admin dashboard.",
        "suggested_next_step": "Schedule a 15-minute scoping call to review requirements.",
    })


def _make_mock_response(content: str | None = None, finish_reason: str = "stop", refusal: str | None = None):
    message = Mock()
    message.content = content
    message.refusal = refusal
    choice = Mock()
    choice.message = message
    choice.finish_reason = finish_reason
    response = Mock()
    response.choices = [choice]
    return response


def _make_bad_request_error(message: str = "400 json_validate_failed: max completion tokens reached before generating a valid document"):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    resp = httpx.Response(400, request=req, json={"error": {"message": message, "code": "json_validate_failed"}})
    return BadRequestError(message=message, response=resp, body=resp.json())


def _make_auth_error(message: str = "Invalid API Key"):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    resp = httpx.Response(401, request=req, json={"error": {"message": message}})
    return AuthenticationError(message=message, response=resp, body=resp.json())


def _make_rate_limit_error(message: str = "Rate limit reached"):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    resp = httpx.Response(429, request=req, json={"error": {"message": message}})
    return RateLimitError(message=message, response=resp, body=resp.json())


# ---------------------------------------------------------------------------
# Test 1: Token exhaustion recovery (400 json_validate_failed)
# ---------------------------------------------------------------------------
def test_token_exhaustion_recovery_bad_request(sample_lead, valid_ai_json):
    """
    Simulate Groq API 400 error when max completion tokens is reached before
    generating a valid document. Verifies that it retries with an increased
    token budget and succeeds.
    """
    mock_client = Mock()
    mock_calls = []

    def side_effect(*args, **kwargs):
        mock_calls.append(kwargs)
        if len(mock_calls) == 1:
            raise _make_bad_request_error(
                "400 json_validate_failed: max completion tokens reached before generating a valid document"
            )
        return _make_mock_response(content=valid_ai_json)

    mock_client.chat.completions.create.side_effect = side_effect

    result = generate_personalized_email(sample_lead, max_retries=2, client=mock_client)

    assert isinstance(result, AIEmailResponse)
    assert result.subject == "Proposal for Website Development - Digital Solutions"
    assert len(mock_calls) == 2
    # Verify the second call escalated the token limit
    assert mock_calls[1]["max_completion_tokens"] > mock_calls[0]["max_completion_tokens"]


# ---------------------------------------------------------------------------
# Test 2: Truncated output recovery (finish_reason="length")
# ---------------------------------------------------------------------------
def test_token_exhaustion_finish_reason_length(sample_lead, valid_ai_json):
    """
    Simulate response cut off at max tokens with finish_reason="length".
    Verifies retry parses and succeeds on second attempt.
    """
    mock_client = Mock()
    truncated_json = '{"subject": "Incomplete Subject", "body": "Cut off mid-sent'

    mock_client.chat.completions.create.side_effect = [
        _make_mock_response(content=truncated_json, finish_reason="length"),
        _make_mock_response(content=valid_ai_json, finish_reason="stop"),
    ]

    result = generate_personalized_email(sample_lead, max_retries=2, client=mock_client)

    assert isinstance(result, AIEmailResponse)
    assert result.subject == "Proposal for Website Development - Digital Solutions"
    assert mock_client.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# Test 3: Malformed JSON recovery
# ---------------------------------------------------------------------------
def test_malformed_json_recovery(sample_lead, valid_ai_json):
    """
    Simulate invalid/corrupted JSON returned from Groq.
    Verifies retry detects JSONDecodeError, retries, and succeeds.
    """
    mock_client = Mock()
    mock_client.chat.completions.create.side_effect = [
        _make_mock_response(content="not a json document at all {{{"),
        _make_mock_response(content=valid_ai_json),
    ]

    result = generate_personalized_email(sample_lead, max_retries=2, client=mock_client)

    assert isinstance(result, AIEmailResponse)
    assert mock_client.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# Test 4: Schema validation failure recovery
# ---------------------------------------------------------------------------
def test_schema_validation_failure_recovery(sample_lead, valid_ai_json):
    """
    Simulate JSON returned missing required fields (e.g. missing lead_summary).
    Verifies retry detects Pydantic validation error, retries, and succeeds.
    """
    mock_client = Mock()
    incomplete_json = json.dumps({"subject": "Only subject provided"})

    mock_client.chat.completions.create.side_effect = [
        _make_mock_response(content=incomplete_json),
        _make_mock_response(content=valid_ai_json),
    ]

    result = generate_personalized_email(sample_lead, max_retries=2, client=mock_client)

    assert isinstance(result, AIEmailResponse)
    assert mock_client.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# Test 5: Successful retry after transient rate limit / server error
# ---------------------------------------------------------------------------
def test_transient_rate_limit_and_server_error_recovery(sample_lead, valid_ai_json):
    """
    Simulate transient 429 rate limit on first attempt, succeeding on second attempt.
    """
    mock_client = Mock()
    mock_client.chat.completions.create.side_effect = [
        _make_rate_limit_error("Rate limit reached. Please wait."),
        _make_mock_response(content=valid_ai_json),
    ]

    result = generate_personalized_email(sample_lead, max_retries=2, client=mock_client)

    assert isinstance(result, AIEmailResponse)
    assert mock_client.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# Test 6: Exhausted retries raises error
# ---------------------------------------------------------------------------
def test_exhausted_retries_raises_error(sample_lead):
    """
    When recoverable failures persist across all attempts (initial + max_retries),
    the final error must be raised.
    """
    mock_client = Mock()
    mock_client.chat.completions.create.side_effect = _make_bad_request_error(
        "400 json_validate_failed: max completion tokens reached before generating a valid document"
    )

    with pytest.raises(BadRequestError) as exc_info:
        generate_personalized_email(sample_lead, max_retries=2, client=mock_client)

    assert "json_validate_failed" in str(exc_info.value)
    # 1 initial + 2 retries = 3 total attempts
    assert mock_client.chat.completions.create.call_count == 3


# ---------------------------------------------------------------------------
# Test 7: Unrecoverable errors fail immediately without retrying
# ---------------------------------------------------------------------------
def test_unrecoverable_auth_error_no_retry(sample_lead):
    """
    Authentication errors (401) are permanent and should never be retried.
    """
    mock_client = Mock()
    mock_client.chat.completions.create.side_effect = _make_auth_error("Invalid API key")

    with pytest.raises(AuthenticationError):
        generate_personalized_email(sample_lead, max_retries=2, client=mock_client)

    # Must fail on the very first attempt without retrying
    assert mock_client.chat.completions.create.call_count == 1


def test_unrecoverable_refusal_no_retry(sample_lead):
    """
    Model refusals must fail immediately with UnrecoverableGenerationError.
    """
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = _make_mock_response(
        content=None, refusal="I cannot fulfill this request."
    )

    with pytest.raises(UnrecoverableGenerationError):
        generate_personalized_email(sample_lead, max_retries=2, client=mock_client)

    assert mock_client.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# Test 8: Empty content recovery
# ---------------------------------------------------------------------------
def test_empty_content_recovery(sample_lead, valid_ai_json):
    """
    Simulate model returning empty string. Verifies it retries and succeeds.
    """
    mock_client = Mock()
    mock_client.chat.completions.create.side_effect = [
        _make_mock_response(content=""),
        _make_mock_response(content=valid_ai_json),
    ]

    result = generate_personalized_email(sample_lead, max_retries=1, client=mock_client)

    assert isinstance(result, AIEmailResponse)
    assert mock_client.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# Test 9: No duplicate email drafts or approvals created across retries
# ---------------------------------------------------------------------------
def test_no_duplicate_drafts_or_approvals_across_retries(tmp_path, sample_lead, valid_ai_json):
    """
    Verifies that when a form submission or background retry job runs
    multiple times, duplicate email drafts and approval requests are NOT created,
    idempotency is preserved, draft status is PENDING, and no emails are sent.
    """
    db_file = str(tmp_path / "test_automation.sqlite3")
    store = AutomationStore(db_file)
    service = AutomationService(store=store)

    submission_id = "sub_test_retry_101"
    lead_id = "LF-RETRY-001"
    normalized_lead = {
        "name": sample_lead.name,
        "email": sample_lead.email,
        "company": sample_lead.company,
        "service": sample_lead.service,
        "requirements": sample_lead.requirements,
        "budget": sample_lead.budget,
        "preferred_contact": "email",
        "consent": True,
    }

    mock_client = Mock()
    mock_client.chat.completions.create.return_value = _make_mock_response(content=valid_ai_json)

    # 1. Execute initial background retry
    with patch("app.services.groq_service.get_groq_client", return_value=mock_client), \
         patch("app.services.sheets_service.update_lead_ai_response", return_value=True):
        res1 = service._handle_retry_groq_personalization({
            "submission_id": submission_id,
            "lead_id": lead_id,
            "normalized_lead": normalized_lead,
        })

    assert res1["status"] == "retried"
    assert res1["ai_status"] == "SUCCESS"

    drafts_1 = store.list_email_drafts(lead_id=lead_id)
    approvals_1 = store.list_approval_requests(lead_id=lead_id)

    assert len(drafts_1) == 1
    assert len(approvals_1) == 1
    assert drafts_1[0]["status"] == "PENDING"
    assert approvals_1[0]["status"] == "PENDING"
    assert drafts_1[0]["recipient"] == sample_lead.email
    assert drafts_1[0]["consent"] == 1

    # 2. Simulate subsequent retry execution with same submission_id
    with patch("app.services.groq_service.get_groq_client", return_value=mock_client), \
         patch("app.services.sheets_service.update_lead_ai_response", return_value=True):
        res2 = service._handle_retry_groq_personalization({
            "submission_id": submission_id,
            "lead_id": lead_id,
            "normalized_lead": normalized_lead,
        })

    assert res2["status"] == "retried"

    drafts_2 = store.list_email_drafts(lead_id=lead_id)
    approvals_2 = store.list_approval_requests(lead_id=lead_id)

    # CRITICAL: Verify NO duplicate drafts or approval requests were created
    assert len(drafts_2) == 1
    assert len(approvals_2) == 1
    assert drafts_2[0]["id"] == drafts_1[0]["id"]
    assert approvals_2[0]["id"] == approvals_1[0]["id"]

    # CRITICAL: Verify draft status is still PENDING and NOT sent
    assert drafts_2[0]["status"] == "PENDING"
    assert drafts_2[0]["sent_at"] is None
