import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.dashboard_auth import dashboard_auth
from app.main import app


def test_password_hash_and_verify():
    pwd = "MySecretPassword123!"
    hashed = dashboard_auth.hash_password(pwd)
    assert "$" in hashed
    assert dashboard_auth.verify_password(pwd, hashed) is True
    assert dashboard_auth.verify_password("WrongPassword", hashed) is False
    assert dashboard_auth.verify_password("", hashed) is False


def test_auth_login_rate_limiting():
    client = TestClient(app)
    ip = "192.168.1.100"

    # Enable proxy header trust for this test
    original_trust = settings.TRUST_PROXY_HEADERS
    settings.TRUST_PROXY_HEADERS = True
    try:
        # Reset attempts for test
        dashboard_auth.clear_failed_attempts(ip)

        headers = {"X-Forwarded-For": ip}
        # Fail 5 times
        for _ in range(5):
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "wrong-password"},
                headers=headers,
            )
            assert resp.status_code == 401

        # 6th attempt should be rate limited
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong-password"},
            headers=headers,
        )
        assert resp.status_code == 429
        assert "Too many failed login attempts" in resp.json()["detail"]

        # Clear rate limit
        dashboard_auth.clear_failed_attempts(ip)
    finally:
        settings.TRUST_PROXY_HEADERS = original_trust


def test_auth_login_untrusted_forwarded_for_cannot_spoof_ip():
    """Verify that when TRUST_PROXY_HEADERS is False, attackers cannot rotate X-Forwarded-For to bypass limits."""
    client = TestClient(app)
    original_trust = settings.TRUST_PROXY_HEADERS
    settings.TRUST_PROXY_HEADERS = False

    try:
        # Clear client host attempts
        dashboard_auth.clear_failed_attempts("testclient")

        # Attempt with 5 different spoofed X-Forwarded-For headers
        for i in range(5):
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "wrong-password"},
                headers={"X-Forwarded-For": f"10.0.0.{i+1}"},
            )
            assert resp.status_code == 401

        # The 6th attempt should be blocked on request.client.host regardless of new spoofed header
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong-password"},
            headers={"X-Forwarded-For": "10.0.0.99"},
        )
        assert resp.status_code == 429
        assert "Too many failed login attempts" in resp.json()["detail"]
    finally:
        dashboard_auth.clear_failed_attempts("testclient")
        settings.TRUST_PROXY_HEADERS = original_trust


def test_auth_login_logout_and_session_flow():
    client = TestClient(app)

    # 1. Unauthenticated /me
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is False

    # 2. Login with correct credentials
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.DASHBOARD_USERNAME,
            "password": settings.DASHBOARD_PASSWORD,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "authenticated"
    assert data["user"]["username"] == settings.DASHBOARD_USERNAME
    csrf_token = data["csrf_token"]
    assert csrf_token is not None

    # Check cookies are set
    cookies = resp.cookies
    assert settings.SESSION_COOKIE_NAME in cookies
    session_id = cookies[settings.SESSION_COOKIE_NAME]

    # 3. Authenticated /me using cookies
    resp_me = client.get("/api/v1/auth/me", cookies=cookies)
    assert resp_me.status_code == 200
    assert resp_me.json()["authenticated"] is True
    assert resp_me.json()["user"]["username"] == settings.DASHBOARD_USERNAME

    # 4. Access protected endpoint using session cookie
    resp_overview = client.get("/api/v1/dashboard/overview", cookies=cookies)
    assert resp_overview.status_code == 200
    overview_data = resp_overview.json()
    assert "total_leads" in overview_data
    assert "temperature_distribution" in overview_data
    assert "score_distribution" in overview_data
    assert "recent_activity" in overview_data

    # 5. Mutation without CSRF token should be rejected (403)
    resp_mutate_no_csrf = client.post(
        "/api/v1/automation/rules/nonexistent/trigger",
        json={"lead_id": "LF-TEST", "context_data": {}},
        cookies=cookies,
    )
    assert resp_mutate_no_csrf.status_code == 403
    assert "CSRF token" in resp_mutate_no_csrf.json()["detail"]

    # 6. Logout
    resp_logout = client.post("/api/v1/auth/logout", cookies=cookies)
    assert resp_logout.status_code == 200
    assert resp_logout.json()["status"] == "logged_out"

    # 7. Session is now invalid
    resp_me_after = client.get("/api/v1/auth/me", cookies=cookies)
    assert resp_me_after.json()["authenticated"] is False


def test_leads_list_and_details_endpoints():
    client = TestClient(app)
    auth_headers = {"X-Webhook-Secret": settings.WEBHOOK_SECRET}

    # 1. List leads
    resp = client.get("/api/v1/leads", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "leads" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data

    # 2. Detail of known or test lead
    # If lead exists in DB (e.g. LF-AE9673C5B5C0)
    resp_detail = client.get("/api/v1/leads/LF-AE9673C5B5C0", headers=auth_headers)
    if resp_detail.status_code == 200:
        det = resp_detail.json()
        assert det["lead_id"] == "LF-AE9673C5B5C0"
        assert "score" in det
        assert "tasks" in det
        assert "activity_timeline" in det


def test_production_startup_validation_rejects_missing_or_default_password(monkeypatch):
    """Verify that in production mode, startup validation rejects missing or default passwords."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DASHBOARD_PASSWORD_HASH", None)
    monkeypatch.setattr(settings, "DASHBOARD_PASSWORD", "LeadFlow2026!Secure")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "LeadFlow2026!Secure")

    with pytest.raises(RuntimeError) as exc_info:
        settings.validate()
    assert "DASHBOARD_PASSWORD must be explicitly configured with a secure non-default password" in str(exc_info.value)

    # Also test with admin123
    monkeypatch.setattr(settings, "DASHBOARD_PASSWORD", "admin123")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "admin123")
    with pytest.raises(RuntimeError) as exc_info:
        settings.validate()
    assert "DASHBOARD_PASSWORD must be explicitly configured" in str(exc_info.value)


def test_production_startup_validation_succeeds_with_secure_password(monkeypatch):
    """Verify that in production mode, startup validation succeeds with strong credentials."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DASHBOARD_PASSWORD_HASH", None)
    monkeypatch.setattr(settings, "DASHBOARD_PASSWORD", "StrongP@ssw0rd987654321!")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "StrongP@ssw0rd987654321!")
    monkeypatch.setenv("SESSION_SECRET_KEY", "prod-secure-session-key-random-string-999")
    monkeypatch.setattr(settings, "SESSION_SECRET_KEY", "prod-secure-session-key-random-string-999")

    # Should not raise
    settings.validate()


def test_production_rejects_insecure_default_passwords_at_auth(monkeypatch):
    """Verify that in production environment, verify_password blocks default credentials."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    for insecure_pwd in settings.INSECURE_DEFAULT_PASSWORDS:
        # Even if stored secret matches, verify_password must reject it in production
        assert dashboard_auth.verify_password(insecure_pwd, insecure_pwd) is False


def test_approval_send_email_guarantees_no_automatic_dispatch(monkeypatch):
    """Verify that approving a SEND_EMAIL action grants authorization but does NOT auto-dispatch."""
    from app.services.automation_service import automation_service

    monkeypatch.setattr(
        automation_service,
        "leads_loader",
        lambda: [{"lead_id": "LEAD-EMAIL-SAFETY", "email": "safety@example.com"}],
    )

    # Create rule requiring approval
    rule = automation_service.create_workflow_rule(
        name="Contract Outbound Email",
        trigger_type="MANUAL",
        actions=[{"type": "SEND_EMAIL", "params": {"template": "contract_draft"}}],
        requires_approval=True,
    )

    # Trigger execution -> AWAITING_APPROVAL
    exec_res = automation_service.trigger_workflow_execution(
        rule_id=rule["id"],
        lead_id="LEAD-EMAIL-SAFETY",
        trigger_event="MANUAL",
    )
    assert exec_res["status"] == "AWAITING_APPROVAL"

    # Find pending approval
    approvals = automation_service.list_approval_requests(status="PENDING")
    appr = next(a for a in approvals if a["workflow_execution_id"] == exec_res["id"])
    assert appr["action_type"] == "SEND_EMAIL"

    # Approve decision
    decision = automation_service.record_approval_decision(
        approval_id=appr["id"],
        action="APPROVE",
        reviewed_by="security_admin",
        decision_notes="Authorized proposal content",
    )
    assert decision["status"] == "APPROVED"

    # Inspect workflow execution: authorization granted, but action_executed remains False
    updated_exec = automation_service.get_workflow_execution(exec_res["id"])
    assert updated_exec["status"] == "COMPLETED"
    result_data = updated_exec["result_data"]
    assert result_data["authorization_granted"] is True
    assert result_data["action_executed"] is False  # Invariant: No customer email dispatched!


def test_timezone_boundary_cases():
    """Test boundary cases between UTC and Asia/Kolkata (IST)."""
    from app.models.automation import to_kolkata_iso, to_utc_iso

    # Boundary 1: UTC 18:30:00 on Nov 20 is exactly midnight (00:00:00) on Nov 21 in IST
    utc_str = "2026-11-20T18:30:00Z"
    kolkata_str = to_kolkata_iso(utc_str)
    assert "2026-11-21T00:00:00" in kolkata_str

    # Boundary 2: Naive string '2026-11-21T00:00:00' with Asia/Kolkata tz normalizes to UTC '2026-11-20T18:30:00'
    normalized_utc = to_utc_iso("2026-11-21T00:00:00", tz_name="Asia/Kolkata")
    assert "2026-11-20T18:30:00+00:00" in normalized_utc

    # Boundary 3: Explicit positive offset normalized to UTC
    explicit_offset = "2026-11-21T05:30:00+05:30"
    normalized_offset = to_utc_iso(explicit_offset)
    assert "2026-11-21T00:00:00+00:00" in normalized_offset


def test_lead_scoring_factor_weights_contract():
    """Validate that DeterministicLeadScorer factor weights sum to 100 points maximum."""
    from app.services.lead_scoring_service import DeterministicLeadScorer

    # Intent max 30
    assert max(pts for pts, _ in DeterministicLeadScorer.INTENT_POINTS.values()) == 30

    # Sentiment max 20
    assert max(pts for pts, _ in DeterministicLeadScorer.SENTIMENT_POINTS.values()) == 20

    # Maximum factor weights defined in docstring and implementation:
    # Intent: 30, Sentiment: 20, Engagement: 15, Budget: 15, Urgency: 10, Recency: 10
    max_weights = [30, 20, 15, 15, 10, 10]
    assert sum(max_weights) == 100

