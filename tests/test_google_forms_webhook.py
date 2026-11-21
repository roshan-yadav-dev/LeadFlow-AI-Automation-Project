from types import SimpleNamespace
from unittest.mock import Mock, patch
import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError

from app.core.config import settings
from app.main import app
from app.services.automation_store import AutomationStore
from app.services import form_service, sheets_service, groq_service, automation_service


@pytest.fixture
def auth_headers():
    return {"X-Webhook-Secret": settings.WEBHOOK_SECRET or "test-secret-value-12345"}


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def temp_store(temp_db, monkeypatch):
    store = AutomationStore(temp_db)
    monkeypatch.setattr(form_service, "automation_store", store)
    monkeypatch.setattr(automation_service.automation_service, "store", store)
    return store


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", "test-secret-value-12345")
    return TestClient(app)


def _mock_ai_result():
    return SimpleNamespace(
        subject="AI Tailored Subject for Lead",
        body="Dear Customer, thank you for contacting us regarding our services.",
        lead_summary="Customer inquiring about web services.",
        suggested_next_step="Schedule an introductory discovery call.",
    )


@pytest.fixture
def mock_services(monkeypatch, temp_store):
    appended_leads = []
    updated_rows = []
    emitted_events = []
    send_email_calls = []

    # Mock Groq
    monkeypatch.setattr(
        form_service,
        "generate_personalized_email",
        lambda lead: _mock_ai_result(),
    )

    # Mock Google Sheets
    monkeypatch.setattr(
        form_service,
        "find_lead_by_email",
        lambda email: {"exists": False, "row": None},
    )
    monkeypatch.setattr(
        form_service,
        "get_lead_by_email",
        lambda email: None,
    )
    monkeypatch.setattr(
        form_service,
        "append_lead",
        lambda lead: appended_leads.append(lead) or {"spreadsheetId": "mock-sheet-id"},
    )
    monkeypatch.setattr(
        form_service,
        "update_lead_crm_row",
        lambda lead_id, lead: updated_rows.append((lead_id, lead)) or True,
    )
    monkeypatch.setattr(
        form_service,
        "update_lead_ai_response",
        lambda **kwargs: True,
    )

    # Mock Automation Service Event Emission
    monkeypatch.setattr(
        automation_service.automation_service,
        "emit_event",
        lambda **kwargs: emitted_events.append(kwargs) or [],
    )

    # Mock Gmail Service (to prove never called)
    from app.services import gmail_service
    monkeypatch.setattr(
        gmail_service,
        "send_email",
        lambda **kwargs: send_email_calls.append(kwargs) or {"success": True},
    )

    return {
        "appended_leads": appended_leads,
        "updated_rows": updated_rows,
        "emitted_events": emitted_events,
        "send_email_calls": send_email_calls,
    }


# ---------------------------------------------------------------------------
# Test 1: Valid Apps Script Payload
# ---------------------------------------------------------------------------
def test_1_valid_apps_script_payload(client, auth_headers, mock_services):
    payload = {
        "submission_id": "sheet_123_0_row_2",
        "spreadsheet_id": "sheet_123",
        "sheet_id": 0,
        "sheet_name": "Form Responses 1",
        "row_number": 2,
        "timestamp": "2026-11-20T16:00:00Z",
        "named_values": {
            "Full Name": ["Jane Doe"],
            "Email Address": ["jane.doe@example.com"],
            "Phone Number": ["+1-555-0199"],
            "Company": ["Acme Corp"],
            "Service Requested": ["Web Application Development"],
            "Requirements": ["We need a scalable CRM dashboard for 50 users."],
            "Budget": ["$10,000 - $25,000"],
            "Consent": ["Yes, I agree to receive email communication"],
        },
    }

    response = client.post(
        "/api/v1/leads/webhook/forms",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["duplicate"] is False
    assert data["submission_id"] == "sheet_123_0_row_2"
    assert data["lead_id"].startswith("LF-")
    assert data["processing_status"] == "COMPLETED"
    assert data["ai_status"] == "SUCCESS"
    assert data["email_status"] == "PENDING"

    # Verify Google Sheets got appended
    assert len(mock_services["appended_leads"]) == 1
    appended = mock_services["appended_leads"][0]
    assert appended["name"] == "Jane Doe"
    assert appended["email"] == "jane.doe@example.com"
    assert appended["service"] == "Web Application Development"
    assert appended["ai_subject"] == "AI Tailored Subject for Lead"
    assert appended["consent"] is True


# ---------------------------------------------------------------------------
# Test 2: Alternative Google Form Question Labels
# ---------------------------------------------------------------------------
def test_2_alternative_google_form_question_labels(client, auth_headers, mock_services):
    payload = {
        "submission_id": "sub_alt_labels_01",
        "named_values": {
            "Your Name": ["Alex Miller"],
            "Your Email": ["alex.miller@example.org"],
            "Mobile": ["9876543210"],
            "Organization": ["Miller Labs"],
            "Interested Service": ["Cloud Migration Consulting"],
            "Project Details": ["Migrating legacy Postgres databases to GCP Spanner."],
            "Budget Range": ["$50,000+"],
            "I agree to terms and contact": ["I agree"],
        },
    }

    response = client.post(
        "/api/v1/leads/webhook/forms",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    appended = mock_services["appended_leads"][0]
    assert appended["name"] == "Alex Miller"
    assert appended["email"] == "alex.miller@example.org"
    assert appended["company"] == "Miller Labs"
    assert appended["service"] == "Cloud Migration Consulting"
    assert appended["consent"] is True


# ---------------------------------------------------------------------------
# Test 3: Missing Optional Fields
# ---------------------------------------------------------------------------
def test_3_missing_optional_fields(client, auth_headers, mock_services):
    payload = {
        "submission_id": "sub_minimal_fields",
        "named_values": {
            "Name": ["Robert King"],
            "Email": ["robert@example.com"],
            "Requirements": ["Need emergency consulting on security audit findings."],
        },
    }

    response = client.post(
        "/api/v1/leads/webhook/forms",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
    appended = mock_services["appended_leads"][0]
    assert appended["name"] == "Robert King"
    assert appended["email"] == "robert@example.com"
    assert appended["phone"] == ""
    assert appended["company"] == ""
    assert appended["service"] == "General Inquiry"
    assert appended["budget"] == ""
    assert appended["consent"] is False


# ---------------------------------------------------------------------------
# Test 4: Missing or Ambiguous Consent
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ambiguous_consent", [
    None,
    "",
    "maybe",
    "not sure",
    "call me instead",
    "No",
    "I do not agree",
    "refuse",
])
def test_4_missing_or_ambiguous_consent(client, auth_headers, mock_services, ambiguous_consent):
    payload = {
        "submission_id": f"sub_consent_{ambiguous_consent}",
        "named_values": {
            "Name": ["Sam Taylor"],
            "Email": ["sam@example.com"],
            "Requirements": ["General business inquiry for custom integration."],
            "Consent": [ambiguous_consent] if ambiguous_consent is not None else [],
        },
    }

    response = client.post(
        "/api/v1/leads/webhook/forms",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
    appended = mock_services["appended_leads"][-1]
    assert appended["consent"] is False
    assert mock_services["send_email_calls"] == []


# ---------------------------------------------------------------------------
# Test 5: Invalid Email
# ---------------------------------------------------------------------------
def test_5_invalid_email(client, auth_headers):
    payload = {
        "submission_id": "sub_bad_email",
        "named_values": {
            "Name": ["Bad Email User"],
            "Email": ["not-a-valid-email-format"],
            "Requirements": ["Inquiry with missing @ domain in email address."],
        },
    }

    response = client.post(
        "/api/v1/leads/webhook/forms",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "email" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 6: Missing Webhook Secret
# ---------------------------------------------------------------------------
def test_6_missing_webhook_secret(client):
    payload = {
        "submission_id": "sub_no_auth",
        "named_values": {"Name": ["Test"], "Email": ["t@example.com"]},
    }

    response = client.post("/api/v1/leads/webhook/forms", json=payload)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test 7: Invalid Webhook Secret
# ---------------------------------------------------------------------------
def test_7_invalid_webhook_secret(client):
    payload = {
        "submission_id": "sub_invalid_auth",
        "named_values": {"Name": ["Test"], "Email": ["t@example.com"]},
    }

    response = client.post(
        "/api/v1/leads/webhook/forms",
        json=payload,
        headers={"X-Webhook-Secret": "completely-wrong-secret"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test 8: Duplicate Submission ID
# ---------------------------------------------------------------------------
def test_8_duplicate_submission_id(client, auth_headers, mock_services):
    payload = {
        "submission_id": "sub_idempotent_test_01",
        "named_values": {
            "Name": ["Idempotent User"],
            "Email": ["idempotent@example.com"],
            "Requirements": ["Testing submission ID deduplication behavior."],
        },
    }

    # First delivery
    res1 = client.post("/api/v1/leads/webhook/forms", json=payload, headers=auth_headers)
    assert res1.status_code == 200
    assert res1.json()["duplicate"] is False
    first_lead_id = res1.json()["lead_id"]
    assert len(mock_services["appended_leads"]) == 1

    # Second delivery with SAME submission_id
    res2 = client.post("/api/v1/leads/webhook/forms", json=payload, headers=auth_headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["duplicate"] is True
    assert data2["lead_id"] == first_lead_id
    # Ensure sheets was NOT called again!
    assert len(mock_services["appended_leads"]) == 1


# ---------------------------------------------------------------------------
# Test 9: Same Email With A Different Submission ID
# ---------------------------------------------------------------------------
def test_9_same_email_with_different_submission_id(client, auth_headers, mock_services, monkeypatch):
    email = "repeat.customer@example.com"
    payload1 = {
        "submission_id": "sub_repeat_01",
        "named_values": {
            "Name": ["Repeat Customer"],
            "Email": [email],
            "Requirements": ["First inquiry about phase 1 architecture."],
        },
    }
    res1 = client.post("/api/v1/leads/webhook/forms", json=payload1, headers=auth_headers)
    assert res1.status_code == 200
    lead_id = res1.json()["lead_id"]

    # Now simulate that this lead exists in Google Sheets for the second submission
    monkeypatch.setattr(
        form_service,
        "find_lead_by_email",
        lambda e: {"exists": True, "row": 5} if e == email else {"exists": False, "row": None},
    )
    monkeypatch.setattr(
        form_service,
        "get_lead_by_email",
        lambda e: {"lead_id": lead_id, "email": email} if e == email else None,
    )

    payload2 = {
        "submission_id": "sub_repeat_02",  # Different submission ID!
        "named_values": {
            "Name": ["Repeat Customer"],
            "Email": [email],
            "Requirements": ["Second inquiry about phase 2 development."],
        },
    }
    res2 = client.post("/api/v1/leads/webhook/forms", json=payload2, headers=auth_headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["duplicate"] is False
    assert data2["submission_id"] == "sub_repeat_02"
    assert data2["lead_id"] == lead_id
    # Row was updated rather than appending a duplicate CRM row
    assert len(mock_services["updated_rows"]) == 1


# ---------------------------------------------------------------------------
# Test 10: Groq Generation Success
# ---------------------------------------------------------------------------
def test_10_groq_generation_success(client, auth_headers, mock_services):
    payload = {
        "submission_id": "sub_groq_success",
        "named_values": {
            "Name": ["AI Customer"],
            "Email": ["ai.customer@example.com"],
            "Service": ["AI Agents Development"],
            "Requirements": ["Looking to deploy autonomous agents for lead qualification."],
        },
    }

    res = client.post("/api/v1/leads/webhook/forms", json=payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["ai_status"] == "SUCCESS"
    appended = mock_services["appended_leads"][0]
    assert appended["ai_subject"] == "AI Tailored Subject for Lead"
    assert appended["ai_response"].startswith("Dear Customer")
    assert appended["lead_summary"] == "Customer inquiring about web services."
    assert appended["suggested_next_step"] == "Schedule an introductory discovery call."


# ---------------------------------------------------------------------------
# Test 11: Groq Transient Failure And Retry
# ---------------------------------------------------------------------------
def test_11_groq_transient_failure_and_retry(client, auth_headers, mock_services, temp_store, monkeypatch):
    monkeypatch.setattr(
        form_service,
        "generate_personalized_email",
        Mock(side_effect=RuntimeError("Groq 503 Rate limit exceeded")),
    )

    payload = {
        "submission_id": "sub_groq_fail",
        "named_values": {
            "Name": ["Fail User"],
            "Email": ["fail@example.com"],
            "Requirements": ["Inquiry during Groq downtime for testing."],
        },
    }

    res = client.post("/api/v1/leads/webhook/forms", json=payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["ai_status"] == "FAILED"

    # Verify lead was still appended to Google Sheets
    assert len(mock_services["appended_leads"]) == 1
    assert mock_services["appended_leads"][0]["ai_status"] == "FAILED"

    # Verify retry job was enqueued in automation_jobs
    jobs = temp_store.list_jobs(job_type="RETRY_GROQ_PERSONALIZATION")
    assert len(jobs) == 1
    assert jobs[0]["payload"]["submission_id"] == "sub_groq_fail"


# ---------------------------------------------------------------------------
# Test 12: Google Sheets Update Success
# ---------------------------------------------------------------------------
def test_12_google_sheets_update_success(client, auth_headers, mock_services, monkeypatch):
    monkeypatch.setattr(
        form_service,
        "find_lead_by_email",
        lambda e: {"exists": True, "row": 12},
    )
    monkeypatch.setattr(
        form_service,
        "get_lead_by_email",
        lambda e: {"lead_id": "LF-EXISTING-12", "email": e},
    )

    payload = {
        "submission_id": "sub_sheets_update",
        "named_values": {
            "Name": ["Existing CRM Lead"],
            "Email": ["existing@example.com"],
            "Requirements": ["Updating our requirements for new enterprise features."],
        },
    }

    res = client.post("/api/v1/leads/webhook/forms", json=payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["lead_id"] == "LF-EXISTING-12"
    assert len(mock_services["updated_rows"]) == 1
    lead_id, updated_lead = mock_services["updated_rows"][0]
    assert lead_id == "LF-EXISTING-12"
    assert updated_lead["ai_status"] == "SUCCESS"


# ---------------------------------------------------------------------------
# Test 13: Google Sheets Transient Failure And Retry
# ---------------------------------------------------------------------------
def test_13_google_sheets_transient_failure_and_retry(client, auth_headers, mock_services, temp_store, monkeypatch):
    monkeypatch.setattr(
        form_service,
        "append_lead",
        Mock(side_effect=RuntimeError("Google Sheets 503 Backend Error")),
    )

    payload = {
        "submission_id": "sub_sheets_fail",
        "named_values": {
            "Name": ["Sheets Fail User"],
            "Email": ["sheets.fail@example.com"],
            "Requirements": ["Inquiry when Sheets API is experiencing errors."],
        },
    }

    res = client.post("/api/v1/leads/webhook/forms", json=payload, headers=auth_headers)
    # The submission is accepted and saved in SQLite, while Sheets sync is queued for retry
    assert res.status_code == 200
    assert res.json()["processing_status"] == "PENDING_RETRY"

    # Verify retry job is in automation_jobs
    jobs = temp_store.list_jobs(job_type="RETRY_SHEETS_SYNC")
    assert len(jobs) == 1
    assert jobs[0]["payload"]["submission_id"] == "sub_sheets_fail"


# ---------------------------------------------------------------------------
# Test 14: No Automatic Email Dispatch
# ---------------------------------------------------------------------------
def test_14_no_automatic_email_dispatch(client, auth_headers, mock_services):
    payload = {
        "submission_id": "sub_safety_check",
        "named_values": {
            "Name": ["Safety First"],
            "Email": ["safety@example.com"],
            "Consent": ["Yes, explicit permission granted"],
            "Requirements": ["Checking that no email is automatically sent."],
        },
    }

    res = client.post("/api/v1/leads/webhook/forms", json=payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["email_status"] == "PENDING"
    # Verification: send_email was NEVER invoked!
    assert mock_services["send_email_calls"] == []


# ---------------------------------------------------------------------------
# Test 15: Automation Event Emitted Exactly Once
# ---------------------------------------------------------------------------
def test_15_automation_event_emitted_exactly_once(client, auth_headers, mock_services):
    payload = {
        "submission_id": "sub_event_test",
        "named_values": {
            "Name": ["Event Trigger User"],
            "Email": ["event.user@example.com"],
            "Requirements": ["Verify that LEAD_CREATED automation event is dispatched."],
        },
    }

    res = client.post("/api/v1/leads/webhook/forms", json=payload, headers=auth_headers)
    assert res.status_code == 200

    events = mock_services["emitted_events"]
    assert len(events) == 1
    event = events[0]
    assert event["trigger_type"] == "LEAD_CREATED"
    assert event["actor"] == "google_forms_webhook"
    assert event["idempotency_key"].startswith("event_lead_created_LF-")

    # Repeat submission (duplicate check)
    res2 = client.post("/api/v1/leads/webhook/forms", json=payload, headers=auth_headers)
    assert res2.status_code == 200
    # Still only 1 event emitted!
    assert len(mock_services["emitted_events"]) == 1


# ---------------------------------------------------------------------------
# Test 16: Existing Lead Intake Endpoint Regression
# ---------------------------------------------------------------------------
def test_16_existing_lead_intake_endpoint_regression(client, auth_headers, monkeypatch):
    # Ensure existing POST /api/v1/leads continues to function cleanly
    from app.api import leads as leads_api
    monkeypatch.setattr(
        leads_api,
        "process_lead",
        lambda lead: {
            "duplicate": False,
            "lead_id": "LF-EXISTING-ROUTE",
            "message": "Lead successfully registered",
            "status": "NEW",
            "email": lead.email,
            "ai_status": "SUCCESS",
            "email_status": "PENDING",
            "email_status_updated": True,
            "email_error": None,
            "email_message_id": None,
            "email_thread_id": None,
        },
    )

    lead_payload = {
        "name": "Original API Lead",
        "email": "original@example.com",
        "service": "Consulting",
        "requirements": "Requirements via original POST /api/v1/leads endpoint.",
        "consent": False,
    }

    res = client.post("/api/v1/leads", json=lead_payload, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["lead_id"] == "LF-EXISTING-ROUTE"
    assert res.json()["status"] == "NEW"
