import base64
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace
from unittest.mock import Mock

from googleapiclient.errors import HttpError

from app.services import gmail_service


def _gmail_api():
    request = Mock()
    request.execute.return_value = {
        "id": "gmail-message-id",
        "threadId": "gmail-thread-id",
    }

    messages = Mock()
    messages.send.return_value = request

    users = Mock()
    users.messages.return_value = messages

    service = Mock()
    service.users.return_value = users
    return service, messages, request


def test_send_email_builds_multipart_message_and_returns_gmail_ids(monkeypatch):
    service, messages, _ = _gmail_api()
    monkeypatch.setattr(gmail_service, "get_gmail_credentials", Mock())
    monkeypatch.setattr(gmail_service, "build", Mock(return_value=service))
    monkeypatch.setattr(
        gmail_service.settings,
        "GMAIL_SENDER_EMAIL",
        "sender@example.com",
    )

    result = gmail_service.send_email(
        "lead@example.com",
        "A subject",
        "Plain-text body",
        "<p>HTML body</p>",
    )

    assert result == {
        "success": True,
        "message_id": "gmail-message-id",
        "thread_id": "gmail-thread-id",
        "error_code": None,
        "error_message": None,
        "ambiguous": False,
    }

    sent = messages.send.call_args.kwargs
    assert sent["userId"] == "me"
    raw = base64.urlsafe_b64decode(sent["body"]["raw"])
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    assert parsed["To"] == "lead@example.com"
    assert parsed["From"] == "sender@example.com"
    assert parsed["Subject"] == "A subject"
    assert parsed.get_content_type() == "multipart/alternative"
    assert [part.get_content_type() for part in parsed.iter_parts()] == [
        "text/plain",
        "text/html",
    ]
    assert "Plain-text body" in parsed.get_body(preferencelist=("plain",)).get_content()
    assert "<p>HTML body</p>" in parsed.get_body(preferencelist=("html",)).get_content()


def test_invalid_recipient_does_not_access_gmail(monkeypatch):
    get_credentials = Mock()
    monkeypatch.setattr(gmail_service, "get_gmail_credentials", get_credentials)
    monkeypatch.setattr(
        gmail_service.settings,
        "GMAIL_SENDER_EMAIL",
        "sender@example.com",
    )

    result = gmail_service.send_email("not-an-email", "Subject", "Body")

    assert result["success"] is False
    assert result["error_code"] == "INVALID_RECIPIENT"
    get_credentials.assert_not_called()


def test_ambiguous_gmail_timeout_is_not_retried(monkeypatch):
    service, messages, request = _gmail_api()
    request.execute.side_effect = TimeoutError
    get_credentials = Mock()
    monkeypatch.setattr(gmail_service, "get_gmail_credentials", get_credentials)
    monkeypatch.setattr(gmail_service, "build", Mock(return_value=service))
    monkeypatch.setattr(
        gmail_service.settings,
        "GMAIL_SENDER_EMAIL",
        "sender@example.com",
    )

    result = gmail_service.send_email("lead@example.com", "Subject", "Body")

    assert result["success"] is False
    assert result["error_code"] == "DELIVERY_UNKNOWN"
    assert result["ambiguous"] is True
    request.execute.assert_called_once()
    messages.send.assert_called_once()


def test_gmail_server_error_is_reported_as_ambiguous(monkeypatch):
    service, _, request = _gmail_api()
    request.execute.side_effect = HttpError(
        SimpleNamespace(status=503, reason="Service unavailable"),
        b"server error",
    )
    monkeypatch.setattr(gmail_service, "get_gmail_credentials", Mock())
    monkeypatch.setattr(gmail_service, "build", Mock(return_value=service))
    monkeypatch.setattr(
        gmail_service.settings,
        "GMAIL_SENDER_EMAIL",
        "sender@example.com",
    )

    result = gmail_service.send_email("lead@example.com", "Subject", "Body")

    assert result["success"] is False
    assert result["ambiguous"] is True
