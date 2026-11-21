from types import SimpleNamespace

import pytest

from app.models.lead import LeadCreate
from app.services import lead_service


def _lead(consent=True):
    return LeadCreate(
        name="Test Lead",
        email="lead@example.com",
        service="Consulting",
        requirements="Help improve our customer onboarding.",
        consent=consent,
    )


def _ai_result():
    return SimpleNamespace(
        subject="A tailored subject",
        body="A tailored plain-text email.",
        lead_summary="Customer needs onboarding support.",
        suggested_next_step="Schedule a discovery call.",
    )


def _stub_common(monkeypatch, *, consent=True):
    appended = []
    updates = []
    monkeypatch.setattr(
        lead_service,
        "find_lead_by_email",
        lambda email: {"exists": False, "row": None},
    )
    monkeypatch.setattr(
        lead_service,
        "generate_personalized_email",
        lambda lead: _ai_result(),
    )
    monkeypatch.setattr(lead_service, "append_lead", appended.append)
    monkeypatch.setattr(
        lead_service,
        "update_lead_email_status",
        lambda **kwargs: updates.append(kwargs) or True,
    )
    monkeypatch.setattr(
        lead_service.settings,
        "GMAIL_SENDER_EMAIL",
        "sender@example.com",
    )
    return appended, updates, _lead(consent=consent)


def test_process_lead_sends_after_crm_save_and_updates_existing_status(monkeypatch):
    appended, updates, lead = _stub_common(monkeypatch)
    monkeypatch.setattr(lead_service, "is_gmail_connected", lambda: True)
    send_calls = []
    monkeypatch.setattr(
        lead_service,
        "send_email",
        lambda **kwargs: send_calls.append(kwargs)
        or {
            "success": True,
            "message_id": "gmail-message-id",
            "thread_id": "gmail-thread-id",
        },
    )

    result = lead_service.process_lead(lead)

    assert result["email_status"] == "SENT"
    assert result["email_status_updated"] is True
    assert result["email_message_id"] == "gmail-message-id"
    assert appended[0]["email_status"] == "PENDING"
    assert send_calls == [
        {
            "to_email": "lead@example.com",
            "subject": "A tailored subject",
            "body": "A tailored plain-text email.",
        }
    ]
    assert updates == [
        {
            "lead_id": result["lead_id"],
            "email_status": "SENT",
            "error_message": "",
        }
    ]


def test_process_lead_skips_sending_without_consent(monkeypatch):
    appended, updates, lead = _stub_common(monkeypatch, consent=False)
    send_email = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("email must not be sent")
    )
    monkeypatch.setattr(lead_service, "send_email", send_email)

    result = lead_service.process_lead(lead)

    assert result["email_status"] == "SKIPPED"
    assert appended[0]["email_status"] == "PENDING"
    assert updates[0]["email_status"] == "SKIPPED"


def test_process_lead_skips_sending_after_ai_failure(monkeypatch):
    appended, updates, lead = _stub_common(monkeypatch)
    monkeypatch.setattr(
        lead_service,
        "generate_personalized_email",
        MockAIError.generate,
    )
    send_email = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("email must not be sent")
    )
    monkeypatch.setattr(lead_service, "send_email", send_email)

    result = lead_service.process_lead(lead)

    assert result["ai_status"] == "FAILED"
    assert result["email_status"] == "SKIPPED"
    assert appended[0]["ai_status"] == "FAILED"
    assert updates[0]["email_status"] == "SKIPPED"
    assert updates[0]["error_message"] == (
        "AI email generation failed; no email was sent."
    )


@pytest.mark.parametrize(
    ("sender_email", "connected", "expected_error"),
    [
        (
            "sender@example.com",
            False,
            "Gmail is not connected; no email was sent.",
        ),
        (
            None,
            True,
            "Gmail sender is not configured; no email was sent.",
        ),
    ],
)
def test_process_lead_does_not_send_without_gmail_configuration(
    monkeypatch,
    sender_email,
    connected,
    expected_error,
):
    _, updates, lead = _stub_common(monkeypatch)
    monkeypatch.setattr(
        lead_service.settings,
        "GMAIL_SENDER_EMAIL",
        sender_email,
    )
    monkeypatch.setattr(
        lead_service,
        "is_gmail_connected",
        lambda: connected,
    )
    monkeypatch.setattr(
        lead_service,
        "send_email",
        lambda **kwargs: pytest.fail("email must not be sent"),
    )

    result = lead_service.process_lead(lead)

    assert result["email_status"] == "FAILED"
    assert result["email_error"] == expected_error
    assert updates[0]["error_message"] == expected_error


class MockAIError:
    @staticmethod
    def generate(_lead):
        raise RuntimeError("AI provider details are not exposed")


def test_retry_for_existing_lead_does_not_send_again(monkeypatch):
    appended, _, lead = _stub_common(monkeypatch)
    existing = {"exists": False, "row": None}

    def find_lead(_email):
        nonlocal existing
        result = existing
        existing = {"exists": True, "row": 2}
        return result

    monkeypatch.setattr(lead_service, "find_lead_by_email", find_lead)
    monkeypatch.setattr(lead_service, "is_gmail_connected", lambda: True)
    send_email = lambda **kwargs: {
        "success": False,
        "error_message": "Gmail could not confirm delivery.",
        "ambiguous": True,
    }
    send_calls = []

    def send_once(**kwargs):
        send_calls.append(kwargs)
        return send_email(**kwargs)

    monkeypatch.setattr(lead_service, "send_email", send_once)

    first_result = lead_service.process_lead(lead)
    retry_result = lead_service.process_lead(lead)

    assert first_result["email_status"] == "FAILED"
    assert first_result["email_error"] == "Gmail could not confirm delivery."
    assert retry_result["duplicate"] is True
    assert len(appended) == 1
    assert len(send_calls) == 1


def test_lead_api_returns_email_delivery_status(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import leads as leads_api
    from app.main import app

    monkeypatch.setattr(
        leads_api,
        "process_lead",
        lambda lead: {
            "duplicate": False,
            "lead_id": "LF-TEST",
            "message": "Lead successfully registered",
            "status": "NEW",
            "email": "lead@example.com",
            "ai_status": "SUCCESS",
            "email_status": "SENT",
            "email_status_updated": True,
            "email_error": None,
            "email_message_id": "gmail-message-id",
            "email_thread_id": "gmail-thread-id",
        },
    )
    app.dependency_overrides[leads_api.verify_webhook_secret] = lambda: True
    try:
        response = TestClient(app).post(
            "/api/v1/leads",
            json={
                "name": "Test Lead",
                "email": "lead@example.com",
                "service": "Consulting",
                "requirements": "Help improve our customer onboarding.",
                "consent": True,
            },
        )
    finally:
        app.dependency_overrides.pop(leads_api.verify_webhook_secret, None)

    assert response.status_code == 201
    assert response.json()["email_status"] == "SENT"
    assert response.json()["email_status_updated"] is True
    assert response.json()["email_message_id"] == "gmail-message-id"
