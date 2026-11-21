
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Lock

from app.services.sheets_service import (
    append_lead,
    find_lead_by_email,
    update_lead_email_status,
)
from app.services.groq_service import generate_personalized_email
from app.services.gmail_auth import is_gmail_connected
from app.services.gmail_service import send_email
from app.core.config import settings

logger = logging.getLogger("leadflow")
_email_lock_guard = Lock()
_email_locks: dict[str, tuple[Lock, int]] = {}


@contextmanager
def _lock_lead_email(email: str):
    with _email_lock_guard:
        lock, references = _email_locks.get(email, (Lock(), 0))
        _email_locks[email] = (lock, references + 1)

    acquired = False
    try:
        lock.acquire()
        acquired = True
        yield
    finally:
        if acquired:
            lock.release()
        with _email_lock_guard:
            _, references = _email_locks[email]
            if references == 1:
                del _email_locks[email]
            else:
                _email_locks[email] = (lock, references - 1)


def process_lead(lead):
    email = str(lead.email).strip().lower()
    with _lock_lead_email(email):
        return _process_lead(lead)


def _process_lead(lead):
    """
    Process an incoming lead:
    1. Normalize email.
    2. Check duplicate email.
    3. Generate lead ID and timestamp.
    4. Generate personalized AI email using Groq.
    5. Save all lead and AI data to Google Sheets.
    6. Send only when consent, AI content, and Gmail are ready.
    7. Persist the final email status in Google Sheets.
    """

    lead_data = lead.model_dump(mode="json")

    # Normalize email
    email = str(lead_data.get("email", "")).strip().lower()
    lead_data["email"] = email

    # Check duplicate lead
    existing_lead = find_lead_by_email(email)

    if existing_lead["exists"]:
        return {
            "duplicate": True,
            "lead_id": None,
            "message": "Lead already exists",
            "ai_status": None,
        }

    # Generate unique lead ID and timestamp
    lead_data["lead_id"] = f"LF-{uuid.uuid4().hex[:12].upper()}"
    lead_data["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Initialize default fields
    lead_data.update({
        "lead_status": "NEW",
        "email_status": "PENDING",
        "ai_status": "PENDING",
        "ai_subject": "",
        "ai_response": "",
        "lead_summary": "",
        "suggested_next_step": "",
        "error_message": "",
    })

    # Generate AI response using Groq
    try:
        ai_result = generate_personalized_email(lead)

        lead_data.update({
            "ai_subject": ai_result.subject,
            "ai_response": ai_result.body,
            "ai_status": "SUCCESS",
            "lead_summary": ai_result.lead_summary,
            "suggested_next_step": ai_result.suggested_next_step,
        })

        logger.info(
            "Groq AI generation successful for lead: %s",
            lead_data["lead_id"]
        )

    except Exception:
        lead_data["ai_status"] = "FAILED"
        lead_data["error_message"] = "AI email generation failed"

        logger.error(
            "Groq AI generation failed for lead %s",
            lead_data["lead_id"],
        )

    # Persist first so retries find the lead and cannot send a second email.
    append_lead(lead_data)

    logger.info(
        "Lead successfully saved: %s",
        lead_data["lead_id"]
    )

    # Phase 6 Integration: Emit LEAD_CREATED automation event
    try:
        from app.services.automation_service import automation_service
        automation_service.emit_event(
            trigger_type="LEAD_CREATED",
            lead_id=lead_data["lead_id"],
            context_data={
                "email": email,
                "name": lead_data.get("name"),
                "company": lead_data.get("company"),
                "service": lead_data.get("service"),
                "budget": lead_data.get("budget"),
                "consent": lead_data.get("consent"),
                "ai_status": lead_data.get("ai_status"),
            },
            idempotency_key=f"event_lead_created_{lead_data['lead_id']}",
            actor="lead_registration",
        )
    except Exception:
        logger.exception("Failed to emit LEAD_CREATED event for %s", lead_data["lead_id"])

    email_status = "PENDING"
    email_error = lead_data["error_message"]
    email_message_id = None
    email_thread_id = None

    if not lead_data["consent"]:
        email_status = "SKIPPED"
        if lead_data["ai_status"] == "SUCCESS":
            email_error = ""
    elif lead_data["ai_status"] != "SUCCESS":
        email_status = "SKIPPED"
        email_error = "AI email generation failed; no email was sent."
    elif not settings.GMAIL_SENDER_EMAIL:
        email_status = "FAILED"
        email_error = "Gmail sender is not configured; no email was sent."
    elif not is_gmail_connected():
        email_status = "FAILED"
        email_error = "Gmail is not connected; no email was sent."
    else:
        try:
            send_result = send_email(
                to_email=email,
                subject=lead_data["ai_subject"],
                body=lead_data["ai_response"],
            )
        except Exception as exc:
            logger.error(
                "Gmail send failed for lead %s (%s)",
                lead_data["lead_id"],
                type(exc).__name__,
            )
            send_result = {
                "success": False,
                "message_id": None,
                "thread_id": None,
                "error_message": (
                    "Gmail could not confirm delivery. Check the Sent folder "
                    "before retrying."
                ),
            }

        if send_result.get("success"):
            email_status = "SENT"
            email_message_id = send_result.get("message_id")
            email_thread_id = send_result.get("thread_id")
            email_error = ""
        else:
            email_status = "FAILED"
            email_error = send_result.get(
                "error_message",
                "Gmail could not send the email.",
            )

    try:
        email_status_updated = update_lead_email_status(
            lead_id=lead_data["lead_id"],
            email_status=email_status,
            error_message=email_error,
        )
    except Exception as exc:
        logger.error(
            "Unable to update CRM email status for lead %s (%s)",
            lead_data["lead_id"],
            type(exc).__name__,
        )
        email_status_updated = False

    if not email_status_updated:
        logger.error(
            "CRM email status was not updated for lead %s",
            lead_data["lead_id"],
        )

    return {
        "duplicate": False,
        "lead_id": lead_data["lead_id"],
        "message": "Lead successfully registered",
        "status": lead_data["lead_status"],
        "email": email,
        "ai_status": lead_data["ai_status"],
        "email_status": email_status,
        "email_status_updated": email_status_updated,
        "email_error": email_error or None,
        "email_message_id": email_message_id,
        "email_thread_id": email_thread_id,
    }
