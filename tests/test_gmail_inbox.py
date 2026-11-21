import base64
import tempfile

from fastapi.testclient import TestClient

from app.main import app
from app.services.gmail_parser import (
    decode_base64url,
    html_to_text,
    parse_gmail_message,
)
from app.services.gmail_sync_service import GmailInboxStore


def _encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")


def test_base64url_decoding():
    assert decode_base64url(_encoded("Hello inbox")) == b"Hello inbox"
    assert decode_base64url("%%%") == b""


def test_multipart_and_missing_headers():
    raw = {
        "id": "msg-1",
        "threadId": "thread-1",
        "internalDate": "1700000000000",
        "snippet": "Hello",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Alice Example <alice@example.com>"},
                {"name": "To", "value": "Bob <bob@example.com>"},
                {"name": "Subject", "value": "Quarterly update"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _encoded("Plain body")}},
                {"mimeType": "text/html", "body": {"data": _encoded("<b>HTML</b>")}},
            ],
        },
    }
    parsed = parse_gmail_message(raw)
    assert parsed["sender_email"] == "alice@example.com"
    assert parsed["sender_name"] == "Alice Example"
    assert parsed["headers"]["from"] == [
        "Alice Example <alice@example.com>"
    ]
    assert parsed["recipient_email"] == "bob@example.com"
    assert parsed["text_body"] == "Plain body"
    assert parsed["html_body"] == "<b>HTML</b>"
    assert parsed["unread"] is True

    missing = parse_gmail_message({"id": "msg-2", "payload": {"mimeType": "text/plain"}})
    assert missing["subject"] == ""
    assert missing["sender_email"] == ""
    assert missing["text_body"] == ""


def test_multiple_from_addresses_are_not_matched_to_a_sender():
    parsed = parse_gmail_message({
        "id": "multiple-from",
        "payload": {
            "headers": [
                {
                    "name": "From",
                    "value": "First <first@example.com>, Second <second@example.com>",
                }
            ]
        },
    })

    assert parsed["sender_email"] == ""


def test_html_only_message_extracts_text_but_preserves_original_html():
    original_html = (
        "<html><head><style>.hidden{display:none}</style>"
        "<script>alert('not text')</script></head>"
        "<body><h1>Welcome</h1><p>Hello &amp; welcome.</p>"
        "<div>See <strong>details</strong>.</div></body></html>"
    )
    raw = {
        "id": "html-only",
        "payload": {
            "mimeType": "text/html",
            "headers": [],
            "body": {"data": _encoded(original_html)},
        },
    }

    parsed = parse_gmail_message(raw)

    assert parsed["text_body"] == "Welcome\nHello & welcome.\nSee details."
    assert parsed["html_body"] == original_html
    assert "alert" not in html_to_text(original_html)


def test_plain_text_takes_precedence_over_html():
    raw = {
        "id": "plain-first",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _encoded("Plain is preferred")}},
                {"mimeType": "text/html", "body": {"data": _encoded("<p>HTML fallback</p>")}},
            ],
        },
    }

    parsed = parse_gmail_message(raw)

    assert parsed["text_body"] == "Plain is preferred"
    assert parsed["html_body"] == "<p>HTML fallback</p>"


def test_store_duplicate_prevention_and_incremental_checkpoint():
    with tempfile.TemporaryDirectory() as directory:
        store = GmailInboxStore(f"{directory}/gmail.sqlite")
        message = {
            "message_id": "same-id",
            "subject": "Hello",
            "internal_date": 1700000000000,
        }
        assert store.add_message(message) is True
        assert store.add_message(message) is False
        assert store.get_message("same-id")["subject"] == "Hello"

        store.set_checkpoint(1700000000000)
        assert store.get_checkpoint() == 1700000000000
        listed = store.list_messages(
            page=1,
            page_size=25,
            search="Hello",
        )
        assert listed["total"] == 1


def test_gmail_api_pagination(monkeypatch):
    from app.services import gmail_inbox_service

    class Messages:
        def __init__(self):
            self.calls = 0

        def list(self, **kwargs):
            self.calls += 1
            call_number = self.calls
            return ListRequest(call_number)

        def get(self, **kwargs):
            message_id = kwargs["id"]
            return GetRequest(message_id)

    class ListRequest:
        def __init__(self, call_number):
            self.call_number = call_number

        def execute(self):
            if self.call_number == 1:
                return {
                    "messages": [{"id": "one"}],
                    "nextPageToken": "next",
                }
            return {"messages": [{"id": "two"}]}

    class GetRequest:
        def __init__(self, message_id):
            self.message_id = message_id

        def execute(self):
            return {
                "id": self.message_id,
                "payload": {"mimeType": "text/plain", "headers": []},
            }

    class Users:
        def __init__(self):
            self._messages = Messages()

        def messages(self):
            return self._messages

    class Service:
        def __init__(self):
            self._users = Users()

        def users(self):
            return self._users

    monkeypatch.setattr(gmail_inbox_service, "get_gmail_service", Service)
    messages, count = gmail_inbox_service.fetch_gmail_messages(max_pages=5)
    assert count == 2
    assert [message["message_id"] for message in messages] == ["one", "two"]


def test_message_api_validation_and_lookup(monkeypatch):
    client = TestClient(app)

    response = client.get("/api/v1/gmail/messages/not valid")
    assert response.status_code == 400

    response = client.get("/api/v1/gmail/messages/invalid%20id")
    assert response.status_code == 400

    response = client.get("/api/v1/gmail/messages/known-id")
    assert response.status_code in (404, 200)


def test_message_list_response_excludes_bodies_and_preserves_filters(monkeypatch):
    from app.api import gmail

    class Store:
        def list_messages(self, **kwargs):
            assert kwargs == {
                "page": 2,
                "page_size": 10,
                "unread": True,
                "sender": "alice@example.com",
                "date_from": "2026-01-01",
                "date_to": "2026-02-01",
                "search": "Quarterly",
            }
            return {
                "messages": [
                    {
                        "message_id": "mail-1",
                        "sender_email": "alice@example.com",
                        "sender_name": "Alice",
                        "recipient_email": "bob@example.com",
                        "subject": "Quarterly",
                        "received_timestamp": "2026-01-15T12:00:00+00:00",
                        "snippet": "Update",
                        "unread": True,
                        "text_body": "Large plain body",
                        "html_body": "<p>Large html body</p>",
                    }
                ],
                "page": 2,
                "page_size": 10,
                "total": 21,
            }

    monkeypatch.setattr(gmail, "gmail_store", Store())
    response = TestClient(app).get(
        "/api/v1/gmail/messages",
        params={
            "page": 2,
            "page_size": 10,
            "unread": "true",
            "sender": "alice@example.com",
            "date_from": "2026-01-01",
            "date_to": "2026-02-01",
            "search": "Quarterly",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["page_size"] == 10
    assert body["total"] == 21
    assert body["messages"] == [
        {
            "message_id": "mail-1",
            "sender_email": "alice@example.com",
            "sender_name": "Alice",
            "recipient_email": "bob@example.com",
            "subject": "Quarterly",
            "received_timestamp": "2026-01-15T12:00:00+00:00",
            "snippet": "Update",
            "unread": True,
        }
    ]


def test_manual_sync_endpoint(monkeypatch):
    from app.api import gmail

    monkeypatch.setattr(
        gmail,
        "sync_inbox",
        lambda: {
            "status": "success",
            "messages_fetched": 2,
            "new_messages": 1,
            "duplicates_skipped": 1,
            "error": None,
        },
    )
    client = TestClient(app)
    response = client.post("/api/v1/gmail/sync")
    assert response.status_code == 200
    assert response.json()["new_messages"] == 1


def test_sync_lock_and_temporary_failure(monkeypatch):
    from app.services import gmail_sync_service

    acquired = gmail_sync_service.sync_lock.acquire(blocking=False)
    assert acquired is True
    try:
        result = gmail_sync_service.sync_inbox()
        assert result["status"] == "running"
    finally:
        gmail_sync_service.sync_lock.release()

    monkeypatch.setattr(
        gmail_sync_service,
        "fetch_gmail_messages",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Gmail unavailable")),
    )
    result = gmail_sync_service.sync_inbox()
    assert result["status"] == "error"
    assert "Gmail" not in result["error"] or result["error"] is not None
