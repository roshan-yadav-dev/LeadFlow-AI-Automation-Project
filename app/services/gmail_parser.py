import base64
import binascii
import re
from html.parser import HTMLParser
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime, parseaddr
from datetime import datetime, timezone



class _ReadableHTMLParser(HTMLParser):
    _ignored_tags = {"script", "style", "noscript", "template", "head"}
    _block_tags = {
        "address", "article", "aside", "blockquote", "br", "dd", "div",
        "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form",
        "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main",
        "ol", "p", "pre", "section", "table", "tbody", "td", "th", "tr", "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_stack: list[str] = []
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._ignored_stack:
            if tag in self._ignored_tags:
                self._ignored_stack.append(tag)
            return

        if tag in self._ignored_tags:
            self._ignored_stack.append(tag)
        elif tag in self._block_tags:
            self._text.append("\n")

    def handle_endtag(self, tag):
        if self._ignored_stack:
            if tag == self._ignored_stack[-1]:
                self._ignored_stack.pop()
            return

        if tag in self._block_tags:
            self._text.append("\n")

    def handle_data(self, data):
        if not self._ignored_stack:
            self._text.append(data)


def html_to_text(html_body: str) -> str:
    if not html_body:
        return ""

    parser = _ReadableHTMLParser()

    try:
        parser.feed(html_body)
        parser.close()
    except Exception:
        return ""

    text = "".join(parser._text)
    text = (
    text.replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        )
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
    ]

    return "\n".join(line for line in lines if line)


def decode_base64url(data: str) -> bytes:
    if not isinstance(data, str):
        return b""
    try:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode((data + padding).encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        return b""


def _header(message: Message, name: str) -> str:
    try:
        value = message.get(name)
        return str(value).strip() if value is not None else ""
    except Exception:
        return ""


def parse_gmail_message(raw: dict) -> dict:
    message_id = str(raw.get("id", "")).strip()
    thread_id = str(raw.get("threadId", "")).strip()
    payload = raw.get("payload") or {}

    headers: dict[str, list[str]] = {}
    for header in payload.get("headers") or []:
        if not isinstance(header, dict):
            continue
        name = str(header.get("name") or "").strip().lower()
        value = str(header.get("value") or "").strip()
        if name and value:
            headers.setdefault(name, []).append(value)

    mime_bytes = payload_to_rfc822(payload)
    message = BytesParser(policy=policy.default).parsebytes(mime_bytes)

    sender = _header(message, "From")
    recipient = _header(message, "To")
    parsed_senders = [
        (name, address)
        for name, address in getaddresses([sender])
        if address.strip()
    ]
    if len(parsed_senders) == 1:
        sender_name, sender_email = parsed_senders[0]
    else:
        sender_name, sender_email = "", ""
    _, recipient_email = parseaddr(recipient)

    text_body = ""
    html_body = ""

    if payload:
        text_body, html_body = extract_mime_bodies(payload)
        if not text_body and not html_body:
            body_data = (payload.get("body") or {}).get("data")
            if body_data:
                text_body = decode_base64url(body_data).decode(
                    "utf-8", errors="replace"
                )

    if mime_bytes:
        if not text_body:
            try:
                text_body = "\n".join(
                    part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8",
                        errors="replace",
                    )
                    for part in message.walk()
                    if part.get_content_type() == "text/plain"
                    and not part.is_multipart()
                    and isinstance(part.get_payload(decode=True), bytes)
                )
            except (LookupError, AttributeError):
                text_body = ""
        if not html_body:
            try:
                for part in message.walk():
                    if part.get_content_type() == "text/html" and not part.is_multipart():
                        data = part.get_payload(decode=True)
                        if isinstance(data, bytes):
                            html_body = data.decode(
                                part.get_content_charset() or "utf-8",
                                errors="replace",
                            )
                        break
            except (LookupError, AttributeError):
                html_body = ""

    if not text_body.strip() and html_body:
        text_body = html_to_text(html_body)

    received_timestamp = ""
    date_header = _header(message, "Date")
    if date_header:
        try:
            parsed = parsedate_to_datetime(date_header)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            received_timestamp = parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            received_timestamp = ""

    internal_date = int(raw.get("internalDate") or 0)
    if not received_timestamp and internal_date:
        received_timestamp = datetime.fromtimestamp(
            internal_date / 1000, tz=timezone.utc
        ).isoformat()

    labels = [
        str(label) for label in (raw.get("labelIds") or [])
        if isinstance(label, (str, int))
    ]

    return {
        "message_id": message_id,
        "thread_id": thread_id,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "recipient_email": recipient_email,
        "subject": _header(message, "Subject"),
        "received_timestamp": received_timestamp,
        "internal_date": internal_date,
        "snippet": str(raw.get("snippet") or ""),
        "text_body": text_body,
        "html_body": html_body,
        "headers": headers,
        "labels": labels,
        "unread": "UNREAD" in labels,
    }


def extract_mime_bodies(payload: dict) -> tuple[str, str]:
    text_body = ""
    html_body = ""

    def walk(node: dict) -> None:
        nonlocal text_body, html_body
        if not isinstance(node, dict):
            return
        mime_type = str(node.get("mimeType") or "").lower()
        body = node.get("body") or {}
        data = body.get("data") if isinstance(body, dict) else None

        if data and not node.get("parts"):
            decoded = decode_base64url(data).decode("utf-8", errors="replace")
            if mime_type == "text/plain" and not text_body:
                text_body = decoded
            elif mime_type == "text/html" and not html_body:
                html_body = decoded

        for part in node.get("parts") or []:
            if isinstance(part, dict):
                walk(part)

    walk(payload)
    return text_body, html_body


def payload_to_rfc822(payload: dict) -> bytes:
    try:
        from email.mime.text import MIMEText
        message = MIMEText("", "plain", "utf-8")
        headers = payload.get("headers") or []
        for header in headers:
            if not isinstance(header, dict):
                continue
            name = header.get("name")
            value = header.get("value")
            if name and value:
                try:
                    message[name] = str(value)
                except Exception:
                    continue
        return message.as_bytes()
    except Exception:
        return b""
