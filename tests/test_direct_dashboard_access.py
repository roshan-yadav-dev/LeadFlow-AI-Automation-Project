import time
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.core.config import settings
from app.services.automation_store import automation_store


def test_incognito_direct_dashboard_overview_access_without_auth():
    """
    Requirement 4.1-4.4:
    Simulate an incognito browser opening the dashboard URL without cookies or auth headers.
    Confirms dashboard overview loads directly with 200 OK and expected schema.
    """
    client = TestClient(app)

    # Completely unauthenticated request (no cookies, no X-Webhook-Secret)
    response = client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()
    assert "total_leads" in data
    assert "hot_leads" in data
    assert "warm_leads" in data
    assert "cold_leads" in data
    assert "temperature_distribution" in data
    assert "score_distribution" in data
    assert "task_status_distribution" in data
    assert "lead_creation_trend" in data
    assert "recent_activity" in data
    assert "gmail_overview" in data


def test_incognito_direct_leads_list_and_details_access_without_auth():
    """
    Requirement 4.4:
    Simulate incognito access to the leads list and lead detail endpoints.
    Confirms leads can be listed and retrieved without requiring login or cookies.
    """
    client = TestClient(app)

    # Unauthenticated leads list
    resp_list = client.get("/api/v1/leads")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert "leads" in list_data
    assert "total" in list_data
    assert "page" in list_data
    assert "page_size" in list_data

    # If there are leads, test detail of first lead
    if list_data["leads"]:
        first_lead = list_data["leads"][0]
        lid = first_lead["lead_id"]
        resp_detail = client.get(f"/api/v1/leads/{lid}")
        assert resp_detail.status_code == 200
        detail_data = resp_detail.json()
        assert detail_data["lead_id"] == lid
        assert "score" in detail_data
        assert "tasks" in detail_data
        assert "activity_timeline" in detail_data


def test_google_forms_webhook_security_remains_enforced():
    """
    Requirement 2 & 5:
    Confirms that Google Forms webhook authentication is NOT modified or bypassed.
    Missing or invalid X-Webhook-Secret MUST return 401 Unauthorized.
    """
    client = TestClient(app)
    payload = {
        "submission_id": f"sub_unauth_{int(time.time())}",
        "named_values": {"Name": ["Unauth Lead"], "Email": ["unauth@example.com"]},
    }

    # 1. Missing secret -> 401
    resp_no_secret = client.post("/api/v1/leads/webhook/forms", json=payload)
    assert resp_no_secret.status_code == 401

    # 2. Invalid secret -> 401
    resp_bad_secret = client.post(
        "/api/v1/leads/webhook/forms",
        json=payload,
        headers={"X-Webhook-Secret": "invalid_wrong_secret"},
    )
    assert resp_bad_secret.status_code == 401


def test_google_forms_webhook_submission_and_appearance_in_dashboard():
    """
    Requirement 4.5 & 4.6:
    1. Test Google Forms webhook with valid secret and a test lead.
    2. Verify the new lead appears in the dashboard leads list without auth.
    """
    client = TestClient(app)
    unique_ts = int(time.time() * 1000)
    test_email = f"presentation.lead.{unique_ts}@example.com"
    test_name = f"Presentation Lead {unique_ts}"
    sub_id = f"sub_pres_{unique_ts}"

    payload = {
        "submission_id": sub_id,
        "named_values": {
            "Full Name": [test_name],
            "Email Address": [test_email],
            "Phone Number": ["+91 9876543210"],
            "Company Name": ["Acme Presentations Inc"],
            "Service Interest": ["AI Integration"],
            "Project Requirements": ["Need AI automated lead workflow for demo."],
            "Budget": ["₹1,00,000+"],
            "Consent": ["Yes"],
        },
    }

    auth_headers = {"X-Webhook-Secret": settings.WEBHOOK_SECRET}

    from types import SimpleNamespace
    from app.services import form_service, sheets_service
    from app.api import leads as leads_api

    recorded_leads = []

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        form_service,
        "generate_personalized_email",
        lambda lead: SimpleNamespace(
            subject="AI Tailored Subject for Lead",
            body="Dear Customer, thank you for contacting us regarding our services.",
            lead_summary="Customer inquiring about web services.",
            suggested_next_step="Schedule an introductory discovery call.",
        ),
    )
    monkeypatch.setattr(form_service, "find_lead_by_email", lambda email: {"exists": False, "row": None})
    monkeypatch.setattr(form_service, "append_lead", lambda lead: recorded_leads.append(lead) or {"spreadsheetId": "mock-sheet-id"})
    monkeypatch.setattr(form_service, "update_lead_crm_row", lambda lead_id, lead: True)
    monkeypatch.setattr(form_service, "update_lead_ai_response", lambda **kwargs: True)

    # Mock sheets list_leads_for_matching so CRM leads are available offline
    monkeypatch.setattr(
        leads_api,
        "_fetch_crm_leads_safely",
        lambda: (recorded_leads, True),
    )

    # Mock automation service lead validation
    from app.services.automation_service import automation_service
    monkeypatch.setattr(automation_service, "validate_lead_exists", lambda lid: True)
    monkeypatch.setattr(automation_service, "emit_event", lambda **kwargs: [])

    try:
        response = client.post("/api/v1/leads/webhook/forms", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        res_data = response.json()
        assert res_data["status"] == "success"
        created_lead_id = res_data["lead_id"]
        assert created_lead_id.startswith("LF-")

        # Now verify the new lead appears in the dashboard leads list without authentication
        leads_resp = client.get(f"/api/v1/leads?search={test_email}")
        assert leads_resp.status_code == 200
        leads_data = leads_resp.json()
        matching_leads = [l for l in leads_data["leads"] if l.get("email") == test_email or l.get("lead_id") == created_lead_id]
        assert len(matching_leads) >= 1, f"Lead {created_lead_id} not found in leads list: {leads_data}"

        # Also verify lead detail can be retrieved without authentication
        detail_resp = client.get(f"/api/v1/leads/{created_lead_id}")
        assert detail_resp.status_code == 200
        lead_detail = detail_resp.json()
        assert lead_detail["lead_id"] == created_lead_id
        assert lead_detail["name"] == test_name
        assert lead_detail["email"] == test_email
    finally:
        monkeypatch.undo()
