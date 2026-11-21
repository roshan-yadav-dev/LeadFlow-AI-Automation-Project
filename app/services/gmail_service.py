
import base64
import logging
from email.message import EmailMessage
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import settings
from app.services.gmail_auth import get_gmail_credentials

logger = logging.getLogger("leadflow")
email_adapter = TypeAdapter(EmailStr)


def _failure(
    error_code: str,
    error_message: str,
    *,
    ambiguous: bool = False,
) -> dict[str, Any]:
    return {
        "success": False,
        "message_id": None,
        "thread_id": None,
        "error_code": error_code,
        "error_message": error_message,
        "ambiguous": ambiguous,
    }


def send_email(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> dict[str, Any]:
    """Send an email through the Gmail account authorized by the user."""
    if not isinstance(to_email, str):
        return _failure("INVALID_RECIPIENT", "A valid recipient email is required.")

    try:
        recipient = str(email_adapter.validate_python(to_email))
    except ValidationError:
        return _failure("INVALID_RECIPIENT", "A valid recipient email is required.")

    sender = settings.GMAIL_SENDER_EMAIL
    if not sender or sender.strip().lower() in ("your_personal_gmail@gmail.com", "user@example.com"):
        try:
            temp_creds = get_gmail_credentials()
            temp_service = build("gmail", "v1", credentials=temp_creds, cache_discovery=False)
            profile = temp_service.users().getProfile(userId="me").execute()
            if profile and profile.get("emailAddress"):
                sender = profile["emailAddress"]
        except Exception:
            pass

    if not sender:
        return _failure(
            "CONFIGURATION_ERROR",
            "Gmail sender is not configured.",
        )

    try:
        sender = str(email_adapter.validate_python(sender))
    except ValidationError:
        return _failure(
            "CONFIGURATION_ERROR",
            "Gmail sender configuration is invalid.",
        )

    if (
        not isinstance(subject, str)
        or not subject.strip()
        or "\r" in subject
        or "\n" in subject
        or not isinstance(body, str)
        or not body.strip()
    ):
        return _failure("INVALID_MESSAGE", "Email subject and body cannot be empty.")

    if html_body is not None and not isinstance(html_body, str):
        return _failure("INVALID_MESSAGE", "HTML email body must be text.")

    try:
        credentials = get_gmail_credentials()
    except Exception as exc:
        logger.warning(
            "Gmail authentication unavailable (%s)",
            type(exc).__name__,
        )
        return _failure(
            "AUTHENTICATION_ERROR",
            "Gmail is not connected or its credentials are invalid.",
        )

    message = EmailMessage()
    message["To"] = recipient
    message["From"] = sender
    message["Subject"] = subject.strip()
    message.set_content(body)
    if html_body is not None:
        message.add_alternative(html_body, subtype="html")

    encoded_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("ascii")

    try:
        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )
    except Exception as exc:
        logger.error(
            "Unable to initialize Gmail API client (%s)",
            type(exc).__name__,
        )
        return _failure(
            "GMAIL_CLIENT_ERROR",
            "Unable to initialize the Gmail service.",
        )

    try:
        result = (
            service.users()
            .messages()
            .send(
                userId="me",
                body={"raw": encoded_message},
            )
            .execute()
        )
    except HttpError as exc:
        http_status = getattr(getattr(exc, "resp", None), "status", None)
        logger.warning("Gmail API send failed with HTTP status %s", http_status)
        if http_status in (408,) or (
            isinstance(http_status, int) and http_status >= 500
        ):
            return _failure(
                "DELIVERY_UNKNOWN",
                "Gmail could not confirm delivery. Check the Sent folder before retrying.",
                ambiguous=True,
            )
        if http_status in (401, 403):
            return _failure(
                "AUTHENTICATION_ERROR",
                "Gmail rejected the authorization. Reconnect Gmail before sending.",
            )
        return _failure(
            "GMAIL_API_ERROR",
            "Gmail rejected the email request.",
        )
    except Exception as exc:
        logger.warning(
            "Gmail send outcome could not be confirmed (%s)",
            type(exc).__name__,
        )
        return _failure(
            "DELIVERY_UNKNOWN",
            "Gmail could not confirm delivery. Check the Sent folder before retrying.",
            ambiguous=True,
        )

    message_id = result.get("id")
    if not message_id:
        logger.warning("Gmail returned a send response without a message ID")
        return _failure(
            "DELIVERY_UNKNOWN",
            "Gmail could not confirm delivery. Check the Sent folder before retrying.",
            ambiguous=True,
        )

    logger.info("Gmail email send completed")
    return {
        "success": True,
        "message_id": message_id,
        "thread_id": result.get("threadId"),
        "error_code": None,
        "error_message": None,
        "ambiguous": False,
    }
