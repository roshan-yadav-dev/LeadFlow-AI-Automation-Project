import os
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.automation_store import AutomationStore, EntityNotFoundError
from app.services import (
    form_service,
    sheets_service,
    gmail_service,
    automation_service,
    email_delivery_service,
)
from app.services.email_delivery_service import (
    ConsentMissingError,
    DraftNotApprovedError,
    DuplicateSendError,
    EmailDeliveryService,
    GmailDeliveryError,
    InvalidContactChannelError,
    InvalidRecipientError,
)


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
def test_store(temp_db, monkeypatch):
    store = AutomationStore(temp_db)
    monkeypatch.setattr(form_service, "automation_store", store)
    monkeypatch.setattr(automation_service.automation_service, "store", store)
    monkeypatch.setattr(email_delivery_service, "automation_store", store)
    monkeypatch.setattr(email_delivery_service.email_delivery_service, "store", store)
    return store


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", "test-secret-value-12345")
    return TestClient(app)


def _mock_ai_result():
    return SimpleNamespace(
        subject="Personalized Proposal for LeadFlow CRM",
        body="Dear Alex,\n\nThank you for reaching out regarding our CRM integration services.\n\nBest regards,\nLeadFlow Team",
        lead_summary="Inquiry regarding CRM integration services.",
        suggested_next_step="Schedule an introductory discovery call.",
    )


@pytest.fixture
def mock_sheets(monkeypatch):
    sheets_status_log = []
    appended_leads = []

    def _mock_update_email_status(lead_id, email_status, error_message=""):
        sheets_status_log.append({
            "lead_id": lead_id,
            "email_status": email_status,
            "error_message": error_message,
        })
        return True

    monkeypatch.setattr(
        sheets_service,
        "update_lead_email_status",
        _mock_update_email_status,
    )
    monkeypatch.setattr(
        email_delivery_service,
        "update_lead_email_status",
        _mock_update_email_status,
    )
    monkeypatch.setattr(
        sheets_service,
        "append_lead",
        lambda lead: appended_leads.append(lead) or {"spreadsheetId": "mock-sheet"},
    )
    monkeypatch.setattr(
        form_service,
        "append_lead",
        lambda lead: appended_leads.append(lead) or {"spreadsheetId": "mock-sheet"},
    )
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
        "generate_personalized_email",
        lambda lead: _mock_ai_result(),
    )

    return {
        "status_log": sheets_status_log,
        "appended_leads": appended_leads,
    }


# ---------------------------------------------------------------------------
# Test 1: Form submission creates draft & approval request WITHOUT sending
# ---------------------------------------------------------------------------
def test_form_submission_creates_draft_and_approval_without_sending(
    client, auth_headers, test_store, mock_sheets, monkeypatch
):
    send_email_calls = []
    monkeypatch.setattr(
        gmail_service,
        "send_email",
        lambda **kwargs: send_email_calls.append(kwargs) or {"success": True},
    )

    payload = {
        "submission_id": "test_form_sub_001",
        "spreadsheet_id": "sheet_123",
        "sheet_id": 0,
        "named_values": {
            "Full Name": ["Alex Morgan"],
            "Email": ["alex.morgan@example.com"],
            "Phone": ["+1-555-0144"],
            "Company": ["Morgan Ventures"],
            "Service": ["Enterprise AI Strategy"],
            "Requirements": ["We need automated lead qualification for 200 agents."],
            "Consent": ["Yes, I consent to email communications"],
            "Preferred Contact": ["Email"],
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
    assert data["ai_status"] == "SUCCESS"
    assert data["email_status"] == "PENDING"
    assert data["draft_id"] is not None
    assert data["approval_id"] is not None

    # CRITICAL: Verify NO email was sent!
    assert len(send_email_calls) == 0

    # Verify draft saved in SQLite
    draft = test_store.get_email_draft(data["draft_id"])
    assert draft is not None
    assert draft["recipient"] == "alex.morgan@example.com"
    assert draft["subject"] == "Personalized Proposal for LeadFlow CRM"
    assert "Dear Alex" in draft["body"]
    assert draft["status"] == "PENDING"
    assert draft["consent"] is True
    assert draft["preferred_contact"] == "email"

    # Verify approval request created in SQLite
    approval = test_store.get_approval_request(data["approval_id"])
    assert approval is not None
    assert approval["action_type"] == "SEND_EMAIL"
    assert approval["status"] == "PENDING"
    assert approval["action_payload"]["recipient"] == "alex.morgan@example.com"


# ---------------------------------------------------------------------------
# Test 2: Missing or false consent blocks sending
# ---------------------------------------------------------------------------
def test_consent_missing_or_false_blocks_sending(test_store, monkeypatch):
    send_email_calls = []
    monkeypatch.setattr(
        gmail_service,
        "send_email",
        lambda **kwargs: send_email_calls.append(kwargs) or {"success": True},
    )
    monkeypatch.setattr(
        email_delivery_service,
        "is_gmail_connected",
        lambda: True,
    )

    draft = test_store.create_email_draft(
        lead_id="LF-NOCONSENT",
        recipient="user@example.com",
        subject="Intro",
        body="Body",
        preferred_contact="email",
        consent=False,  # NO CONSENT
        status="APPROVED",  # Even if approved by mistake
    )

    with pytest.raises(ConsentMissingError) as exc_info:
        email_delivery_service.email_delivery_service.send_approved_draft(draft["id"])

    assert "consent was not granted" in str(exc_info.value).lower()
    assert len(send_email_calls) == 0


# ---------------------------------------------------------------------------
# Test 3: Preferred contact not Email blocks sending
# ---------------------------------------------------------------------------
def test_preferred_contact_not_email_blocks_sending(test_store, monkeypatch):
    send_email_calls = []
    monkeypatch.setattr(
        gmail_service,
        "send_email",
        lambda **kwargs: send_email_calls.append(kwargs) or {"success": True},
    )
    monkeypatch.setattr(
        email_delivery_service,
        "is_gmail_connected",
        lambda: True,
    )

    draft = test_store.create_email_draft(
        lead_id="LF-PHONEONLY",
        recipient="user@example.com",
        subject="Intro",
        body="Body",
        preferred_contact="phone",  # PREFERRED CONTACT IS PHONE
        consent=True,
        status="APPROVED",
    )

    with pytest.raises(InvalidContactChannelError) as exc_info:
        email_delivery_service.email_delivery_service.send_approved_draft(draft["id"])

    assert "preferred contact" in str(exc_info.value).lower()
    assert len(send_email_calls) == 0


# ---------------------------------------------------------------------------
# Test 4: Invalid or empty recipient blocks sending
# ---------------------------------------------------------------------------
def test_invalid_recipient_blocks_sending(test_store, monkeypatch):
    monkeypatch.setattr(
        email_delivery_service,
        "is_gmail_connected",
        lambda: True,
    )

    draft = test_store.create_email_draft(
        lead_id="LF-BADEMAIL",
        recipient="not-an-email",
        subject="Intro",
        body="Body",
        preferred_contact="email",
        consent=True,
        status="APPROVED",
    )

    with pytest.raises(InvalidRecipientError) as exc_info:
        email_delivery_service.email_delivery_service.send_approved_draft(draft["id"])

    assert "valid recipient email" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 5: Approval without sending (Approval alone does NOT dispatch)
# ---------------------------------------------------------------------------
def test_approval_without_sending(test_store, mock_sheets, monkeypatch):
    send_email_calls = []
    monkeypatch.setattr(
        gmail_service,
        "send_email",
        lambda **kwargs: send_email_calls.append(kwargs) or {"success": True},
    )

    draft = test_store.create_email_draft(
        lead_id="LF-APPROVETEST",
        recipient="client@example.com",
        subject="Proposal",
        body="Here is your proposal.",
        preferred_contact="email",
        consent=True,
        status="PENDING",
    )

    appr = test_store.create_approval_request(
        lead_id="LF-APPROVETEST",
        action_type="SEND_EMAIL",
        action_payload={"draft_id": draft["id"]},
        requested_by="ai_agent",
    )
    test_store.update_email_draft(draft["id"], approval_id=appr["id"])

    # Human operator approves the draft
    approved = email_delivery_service.email_delivery_service.approve_draft(
        draft_id=draft["id"],
        reviewed_by="admin_operator",
        decision_notes="Looks great, verified personal information",
    )

    assert approved["status"] == "APPROVED"
    assert approved["approved_by"] == "admin_operator"
    assert approved["approved_at"] is not None

    # CRITICAL: Verify send_email was NOT called
    assert len(send_email_calls) == 0

    # Verify Google Sheets status updated to APPROVED
    assert any(
        s["lead_id"] == "LF-APPROVETEST" and s["email_status"] == "APPROVED"
        for s in mock_sheets["status_log"]
    )


# ---------------------------------------------------------------------------
# Test 6: Sending unapproved draft is rejected
# ---------------------------------------------------------------------------
def test_sending_unapproved_draft_is_blocked(test_store, monkeypatch):
    monkeypatch.setattr(
        email_delivery_service,
        "is_gmail_connected",
        lambda: True,
    )

    draft = test_store.create_email_draft(
        lead_id="LF-UNAPPROVED",
        recipient="client@example.com",
        subject="Proposal",
        body="Body",
        preferred_contact="email",
        consent=True,
        status="PENDING",  # NOT APPROVED
    )

    with pytest.raises(DraftNotApprovedError) as exc_info:
        email_delivery_service.email_delivery_service.send_approved_draft(draft["id"])

    assert "has not been approved" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 7: Explicit send after approval succeeds
# ---------------------------------------------------------------------------
def test_explicit_send_after_approval_success(
    client, auth_headers, test_store, mock_sheets, monkeypatch
):
    send_email_calls = []

    def _mock_send(to_email, subject, body, html_body=None):
        send_email_calls.append({
            "to": to_email,
            "subject": subject,
            "body": body,
        })
        return {
            "success": True,
            "message_id": "18c21a4f8992cde",
            "thread_id": "18c21a4f8992thd",
            "error_code": None,
            "error_message": None,
            "ambiguous": False,
        }

    monkeypatch.setattr(email_delivery_service, "send_email", _mock_send)
    monkeypatch.setattr(email_delivery_service, "is_gmail_connected", lambda: True)

    draft = test_store.create_email_draft(
        lead_id="LF-DISPATCH01",
        recipient="dispatch.target@example.com",
        subject="Approved Subject",
        body="Approved Body Text",
        preferred_contact="email",
        consent=True,
        status="PENDING",
    )

    # 1. Approve draft
    appr_resp = client.post(
        f"/api/v1/automation/emails/drafts/{draft['id']}/approve",
        json={"decision_notes": "Sign-off complete"},
        headers=auth_headers,
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "APPROVED"
    assert len(send_email_calls) == 0

    # 2. Explicit deliberate send action
    send_resp = client.post(
        f"/api/v1/automation/emails/drafts/{draft['id']}/send",
        headers=auth_headers,
    )
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["success"] is True
    assert send_data["status"] == "SENT"
    assert send_data["message_id"] == "18c21a4f8992cde"
    assert send_data["thread_id"] == "18c21a4f8992thd"

    # Verify send_email called exactly once with correct payload
    assert len(send_email_calls) == 1
    assert send_email_calls[0]["to"] == "dispatch.target@example.com"
    assert send_email_calls[0]["subject"] == "Approved Subject"
    assert send_email_calls[0]["body"] == "Approved Body Text"

    # Verify draft updated to SENT in SQLite
    updated = test_store.get_email_draft(draft["id"])
    assert updated["status"] == "SENT"
    assert updated["gmail_message_id"] == "18c21a4f8992cde"
    assert updated["sent_at"] is not None

    # Verify Google Sheets status updated to SENT
    assert any(
        s["lead_id"] == "LF-DISPATCH01" and s["email_status"] == "SENT"
        for s in mock_sheets["status_log"]
    )


# ---------------------------------------------------------------------------
# Test 8: Duplicate send prevention
# ---------------------------------------------------------------------------
def test_duplicate_send_prevention(client, auth_headers, test_store, monkeypatch):
    send_email_calls = []

    def _mock_send(to_email, subject, body, html_body=None):
        send_email_calls.append({"to": to_email})
        return {
            "success": True,
            "message_id": "msg_dup_prevent_123",
            "thread_id": "th_dup",
        }

    monkeypatch.setattr(email_delivery_service, "send_email", _mock_send)
    monkeypatch.setattr(email_delivery_service, "is_gmail_connected", lambda: True)

    draft = test_store.create_email_draft(
        lead_id="LF-DUPTEST",
        recipient="dup.target@example.com",
        subject="Dup Test",
        body="Body",
        preferred_contact="email",
        consent=True,
        status="APPROVED",
    )

    # First send succeeds
    r1 = client.post(
        f"/api/v1/automation/emails/drafts/{draft['id']}/send",
        headers=auth_headers,
    )
    assert r1.status_code == 200
    assert len(send_email_calls) == 1

    # Second send attempt must be rejected with 409 CONFLICT!
    r2 = client.post(
        f"/api/v1/automation/emails/drafts/{draft['id']}/send",
        headers=auth_headers,
    )
    assert r2.status_code == 409
    assert "already been delivered" in r2.json()["detail"].lower()
    # Ensure send_email was NOT called a second time
    assert len(send_email_calls) == 1


# ---------------------------------------------------------------------------
# Test 9: Gmail OAuth unavailable surfaces safe error
# ---------------------------------------------------------------------------
def test_gmail_oauth_unavailable_surfaces_safe_error(
    client, auth_headers, test_store, mock_sheets, monkeypatch
):
    # Mock Gmail connection failure
    monkeypatch.setattr(email_delivery_service, "is_gmail_connected", lambda: False)

    draft = test_store.create_email_draft(
        lead_id="LF-OAUTHFAIL",
        recipient="oauth.target@example.com",
        subject="Subject",
        body="Body",
        preferred_contact="email",
        consent=True,
        status="APPROVED",
    )

    resp = client.post(
        f"/api/v1/automation/emails/drafts/{draft['id']}/send",
        headers=auth_headers,
    )

    assert resp.status_code == 502
    assert "gmail is not connected" in resp.json()["detail"].lower()

    # Verify status in SQLite updated to FAILED
    updated = test_store.get_email_draft(draft["id"])
    assert updated["status"] == "FAILED"
    assert updated["error_code"] == "AUTHENTICATION_ERROR"

    # Verify status in Sheets updated to FAILED
    assert any(
        s["lead_id"] == "LF-OAUTHFAIL" and s["email_status"] == "FAILED"
        for s in mock_sheets["status_log"]
    )


# ---------------------------------------------------------------------------
# Test 10: Gmail API error handling
# ---------------------------------------------------------------------------
def test_gmail_api_error_handling(
    client, auth_headers, test_store, mock_sheets, monkeypatch
):
    monkeypatch.setattr(email_delivery_service, "is_gmail_connected", lambda: True)
    monkeypatch.setattr(
        email_delivery_service,
        "send_email",
        lambda **kwargs: {
            "success": False,
            "error_code": "GMAIL_API_ERROR",
            "error_message": "Daily sending quota exceeded for this account.",
            "ambiguous": False,
        },
    )

    draft = test_store.create_email_draft(
        lead_id="LF-QUOTAFAIL",
        recipient="quota.target@example.com",
        subject="Subject",
        body="Body",
        preferred_contact="email",
        consent=True,
        status="APPROVED",
    )

    resp = client.post(
        f"/api/v1/automation/emails/drafts/{draft['id']}/send",
        headers=auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["status"] == "FAILED"
    assert data["error_code"] == "GMAIL_API_ERROR"
    assert "daily sending quota" in data["error_message"].lower()

    # Verify SQLite record updated to FAILED
    updated = test_store.get_email_draft(draft["id"])
    assert updated["status"] == "FAILED"
    assert updated["error_message"] == "Daily sending quota exceeded for this account."

    # Verify Sheets updated to FAILED
    assert any(
        s["lead_id"] == "LF-QUOTAFAIL" and s["email_status"] == "FAILED"
        for s in mock_sheets["status_log"]
    )


# ---------------------------------------------------------------------------
# Test 11: Uncertain API outcome prevents blind retry
# ---------------------------------------------------------------------------
def test_uncertain_api_outcome_prevents_blind_retry(
    client, auth_headers, test_store, mock_sheets, monkeypatch
):
    monkeypatch.setattr(email_delivery_service, "is_gmail_connected", lambda: True)
    monkeypatch.setattr(
        email_delivery_service,
        "send_email",
        lambda **kwargs: {
            "success": False,
            "error_code": "DELIVERY_UNKNOWN",
            "error_message": "Gmail could not confirm delivery. Check the Sent folder before retrying.",
            "ambiguous": True,
        },
    )

    draft = test_store.create_email_draft(
        lead_id="LF-AMBIGUOUS",
        recipient="ambiguous.target@example.com",
        subject="Subject",
        body="Body",
        preferred_contact="email",
        consent=True,
        status="APPROVED",
    )

    resp = client.post(
        f"/api/v1/automation/emails/drafts/{draft['id']}/send",
        headers=auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["ambiguous"] is True
    assert "check the sent folder" in data["error_message"].lower()


# ---------------------------------------------------------------------------
# Test 12: Lead send endpoint (/api/v1/leads/{id}/send-email)
# ---------------------------------------------------------------------------
def test_lead_send_endpoint_flow(
    client, auth_headers, test_store, mock_sheets, monkeypatch
):
    monkeypatch.setattr(email_delivery_service, "is_gmail_connected", lambda: True)
    monkeypatch.setattr(
        email_delivery_service,
        "send_email",
        lambda **kwargs: {
            "success": True,
            "message_id": "msg_lead_send_777",
            "thread_id": "th_lead_send_777",
        },
    )

    draft = test_store.create_email_draft(
        lead_id="LF-ROUTETEST",
        recipient="route.target@example.com",
        subject="Direct Route Subject",
        body="Direct Route Body",
        preferred_contact="email",
        consent=True,
        status="APPROVED",
    )

    resp = client.post(
        "/api/v1/leads/LF-ROUTETEST/send-email",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["message_id"] == "msg_lead_send_777"
