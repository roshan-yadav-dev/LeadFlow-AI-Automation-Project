import time
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.core.config import settings
from app.core.dashboard_auth import dashboard_auth
from app.services.automation_store import automation_store


def test_health_endpoints():
    """
    Verification Phase 4.1:
    GET /health and GET /api/v1/automation/health return 200 OK.
    """
    client = TestClient(app)
    r1 = client.get("/health")
    assert r1.status_code == 200
    assert r1.json()["status"] == "healthy"

    r2 = client.get("/api/v1/automation/health")
    assert r2.status_code == 200
    assert r2.json()["status"] == "healthy"


def test_incognito_direct_dashboard_overview_access_without_auth():
    """
    Verification Phase 4.2 & 4.8:
    Simulate an incognito browser opening the dashboard URL without cookies or auth headers.
    Confirms dashboard overview loads directly with 200 OK both with and without /api/v1 prefix.
    """
    client = TestClient(app)

    # Completely unauthenticated request with /api/v1
    response = client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "total_leads" in data
    assert "hot_leads" in data
    assert "temperature_distribution" in data

    # Completely unauthenticated request without /api/v1 (compatibility middleware)
    resp_compat = client.get("/dashboard/overview")
    assert resp_compat.status_code == 200, f"Expected 200, got {resp_compat.status_code}"
    assert "total_leads" in resp_compat.json()


def test_incognito_direct_leads_list_and_details_access_without_auth():
    """
    Verification Phase 4.3 & 4.8:
    Simulate incognito access to the leads list and lead detail endpoints.
    Confirms leads can be listed and retrieved without requiring login or cookies.
    """
    client = TestClient(app)

    # Unauthenticated leads list (both prefixed and compatibility path)
    resp_list = client.get("/api/v1/leads")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert "leads" in list_data

    resp_list_compat = client.get("/leads")
    assert resp_list_compat.status_code == 200
    assert "leads" in resp_list_compat.json()

    # If there are leads, test detail of first lead
    if list_data["leads"]:
        first_lead = list_data["leads"][0]
        lid = first_lead["lead_id"]
        resp_detail = client.get(f"/api/v1/leads/{lid}")
        assert resp_detail.status_code == 200
        assert resp_detail.json()["lead_id"] == lid

        resp_detail_compat = client.get(f"/leads/{lid}")
        assert resp_detail_compat.status_code == 200
        assert resp_detail_compat.json()["lead_id"] == lid


def test_automation_tasks_leaderboard_and_reminders_apis():
    """
    Verification Phase 4.4, 4.5, 4.6:
    Verify automation tasks, leaderboard, and pending reminders APIs work with session/webhook authentication
    both with and without /api/v1 prefix.
    """
    client = TestClient(app)
    auth_headers = {"X-Webhook-Secret": settings.WEBHOOK_SECRET}

    # 1. Automation tasks API
    r_tasks_v1 = client.get("/api/v1/automation/tasks", headers=auth_headers)
    assert r_tasks_v1.status_code == 200

    r_tasks_compat = client.get("/automation/tasks", headers=auth_headers)
    assert r_tasks_compat.status_code == 200

    # 2. Automation leaderboard API
    r_board_v1 = client.get("/api/v1/automation/scores/leaderboard", headers=auth_headers)
    assert r_board_v1.status_code == 200

    r_board_compat = client.get("/automation/scores/leaderboard", headers=auth_headers)
    assert r_board_compat.status_code == 200

    # 3. Pending reminders API
    r_rem_v1 = client.get("/api/v1/automation/reminders/pending", headers=auth_headers)
    assert r_rem_v1.status_code == 200

    r_rem_compat = client.get("/automation/reminders/pending", headers=auth_headers)
    assert r_rem_compat.status_code == 200


def test_leaderboard_presentation_session_and_unauthorized_rejection():
    """
    Verification:
    1. Direct login returns a valid presentation session token.
    2. Unauthenticated requests to /api/v1/automation/scores/leaderboard return 401.
    3. Requests with invalid Bearer token return 401.
    4. Requests with valid Bearer token return 200.
    5. Requests with valid X-Session-ID header return 200.
    6. Requests with session cookie return 200.
    """
    client = TestClient(app)

    # 1. Unauthenticated request -> 401
    r_unauth = client.get("/api/v1/automation/scores/leaderboard")
    assert r_unauth.status_code == 401
    assert "Invalid webhook credentials" in r_unauth.json()["detail"]

    # 2. Request with invalid Bearer token -> 401
    r_bad_token = client.get(
        "/api/v1/automation/scores/leaderboard",
        headers={"Authorization": "Bearer invalid_presentation_token_999"},
    )
    assert r_bad_token.status_code == 401

    # 3. Direct login creates presentation session and returns valid token
    r_direct = client.post("/api/v1/auth/direct-login")
    assert r_direct.status_code == 200
    login_data = r_direct.json()
    token = login_data.get("token")
    assert token is not None
    assert login_data.get("session_id") == token
    assert login_data.get("status") == "authenticated"

    # 4. Request using Bearer token without cookies -> 200
    client_no_cookies = TestClient(app)
    r_bearer = client_no_cookies.get(
        "/api/v1/automation/scores/leaderboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_bearer.status_code == 200
    assert isinstance(r_bearer.json(), list)

    # Also test compatibility path without /api/v1
    r_bearer_compat = client_no_cookies.get(
        "/automation/scores/leaderboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_bearer_compat.status_code == 200
    assert isinstance(r_bearer_compat.json(), list)

    # 5. Request using X-Session-ID header -> 200
    r_x_session = client_no_cookies.get(
        "/api/v1/automation/scores/leaderboard",
        headers={"X-Session-ID": token},
    )
    assert r_x_session.status_code == 200

    # 6. Request using session cookie -> 200
    r_cookie = client.get("/api/v1/automation/scores/leaderboard")
    assert r_cookie.status_code == 200


def test_cors_preflight_from_deployed_origin():
    """
    Verification Phase 4.10:
    Verify CORS preflight succeeds from deployed origins (such as https://*.onrender.com).
    """
    client = TestClient(app)
    deployed_origins = [
        "https://leadflow-ai-frontend.onrender.com",
        "https://leadflow-ai-frontend-demo.vercel.app",
        "http://localhost:5173",
    ]

    for origin in deployed_origins:
        # Preflight on /api/v1/dashboard/overview
        resp = client.options(
            "/api/v1/dashboard/overview",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp.status_code == 200, f"CORS preflight failed for {origin}: {resp.status_code}"
        assert resp.headers.get("access-control-allow-origin") == origin
        assert resp.headers.get("access-control-allow-credentials") == "true"

        # Preflight on compatibility path /dashboard/overview
        resp_compat = client.options(
            "/dashboard/overview",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp_compat.status_code == 200
        assert resp_compat.headers.get("access-control-allow-origin") == origin


def test_google_forms_webhook_security_remains_enforced():
    """
    Verification Phase 4.7:
    Confirms that Google Forms webhook authentication is NOT modified or bypassed.
    Missing or invalid X-Webhook-Secret MUST return 401 Unauthorized.
    """
    client = TestClient(app)
    payload = {
        "submission_id": f"sub_unauth_{int(time.time())}",
        "named_values": {"Name": ["Unauth Lead"], "Email": ["unauth@example.com"]},
    }

    # 1. Missing secret on /api/v1/leads/webhook/forms -> 401
    resp_no_secret = client.post("/api/v1/leads/webhook/forms", json=payload)
    assert resp_no_secret.status_code == 401

    # 2. Missing secret on compatibility /leads/webhook/forms -> 401
    resp_no_secret_compat = client.post("/leads/webhook/forms", json=payload)
    assert resp_no_secret_compat.status_code == 401

    # 3. Invalid secret -> 401
    resp_bad_secret = client.post(
        "/api/v1/leads/webhook/forms",
        json=payload,
        headers={"X-Webhook-Secret": "invalid_wrong_secret"},
    )
    assert resp_bad_secret.status_code == 401


def test_google_forms_webhook_submission_and_appearance_in_dashboard():
    """
    Verification Phase 4.7:
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

    monkeypatch.setattr(
        leads_api,
        "_fetch_crm_leads_safely",
        lambda: (recorded_leads, True),
    )

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

        # Verify appearance via /api/v1/leads
        leads_resp = client.get(f"/api/v1/leads?search={test_email}")
        assert leads_resp.status_code == 200
        matching = [l for l in leads_resp.json()["leads"] if l.get("email") == test_email or l.get("lead_id") == created_lead_id]
        assert len(matching) >= 1

        # Verify appearance via compatibility /leads
        leads_compat = client.get(f"/leads?search={test_email}")
        assert leads_compat.status_code == 200
        matching_compat = [l for l in leads_compat.json()["leads"] if l.get("email") == test_email or l.get("lead_id") == created_lead_id]
        assert len(matching_compat) >= 1

        # Verify detail via /api/v1/leads/{id} and /leads/{id}
        det1 = client.get(f"/api/v1/leads/{created_lead_id}")
        assert det1.status_code == 200
        assert det1.json()["lead_id"] == created_lead_id

        det2 = client.get(f"/leads/{created_lead_id}")
        assert det2.status_code == 200
        assert det2.json()["lead_id"] == created_lead_id
    finally:
        monkeypatch.undo()
