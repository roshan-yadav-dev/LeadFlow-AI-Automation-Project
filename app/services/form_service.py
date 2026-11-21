import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import settings
from app.models.forms import GoogleFormWebhookPayload
from app.models.lead import LeadCreate
from app.services.automation_service import automation_service
from app.services.automation_store import (
    DuplicateIdempotencyKeyError,
    automation_store,
)
from app.services.groq_service import generate_personalized_email
from app.services.sheets_service import (
    append_lead,
    find_lead_by_email,
    get_lead_by_email,
    update_lead_crm_row,
    update_lead_ai_response,
)

logger = logging.getLogger("leadflow")
_email_adapter = TypeAdapter(EmailStr)

# Strict positive matches for consent
POSITIVE_CONSENT_TOKENS = frozenset({
    "yes", "y", "true", "1", "agree", "i agree", "consented",
    "accepted", "checked", "opt-in", "optin", "i consent", "allow"
})

# Explicit negative tokens that override
NEGATIVE_CONSENT_TOKENS = frozenset({
    "no", "n", "false", "0", "disagree", "refuse", "do not", "don't",
    "opt-out", "optout", "deny", "never"
})


def _extract_string_value(raw: Any) -> str:
    """Extract a clean scalar string from various form submission value representations."""
    if raw is None:
        return ""
    if isinstance(raw, list):
        # Google Apps Script namedValues are arrays of strings: ["value"]
        joined = " ".join(str(item).strip() for item in raw if item is not None)
        return joined.strip()
    return str(raw).strip()


def parse_consent_safely(raw: Any) -> bool:
    """
    Parse consent with a strict fail-safe policy:
    - Only unambiguous positive consent yields True.
    - Missing, empty, or ambiguous inputs strictly yield False.
    - Any negative token yields False.
    """
    text = _extract_string_value(raw).lower()
    if not text:
        return False

    # Clean words of punctuation
    clean_words = set(re.sub(r"[^\w]", "", w) for w in text.split() if w)

    # Check for multi-word negative phrases
    if any(phrase in text for phrase in ("do not", "don't", "opt out", "opt-out", "no consent")):
        return False

    # Check for single-word negative tokens
    if any(neg in clean_words for neg in NEGATIVE_CONSENT_TOKENS):
        return False

    # Check for positive tokens in clean words
    if any(pos in clean_words for pos in POSITIVE_CONSENT_TOKENS):
        return True

    # Exact phrasing checks
    if any(phrase in text for phrase in ("i agree", "i consent", "consent granted", "terms and contact")):
        return True

    # Ambiguous input (e.g. "maybe", "not sure", "depends") strictly defaults to False
    return False


def normalize_form_submission(payload_data: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize Google Forms / Google Sheets onFormSubmit data.
    Supports varied question labels and formats.
    Validates required fields (email, name, requirements).
    """
    # 1. Gather all candidate fields from named_values or top-level keys
    named_values = payload_data.get("named_values") or {}
    candidates: dict[str, Any] = {}

    if isinstance(named_values, dict):
        for k, v in named_values.items():
            candidates[str(k).strip()] = v

    # Also incorporate top-level keys if not already present
    for k, v in payload_data.items():
        if k not in {"named_values", "submission_id", "spreadsheet_id", "sheet_id", "sheet_name", "row_number", "timestamp"}:
            if k not in candidates:
                candidates[str(k).strip()] = v

    # 2. Match field labels to canonical attributes
    extracted: dict[str, Any] = {
        "name": None,
        "email": None,
        "phone": None,
        "company": None,
        "service": None,
        "requirements": None,
        "budget": None,
        "consent": None,
        "preferred_contact": None,
    }

    for label, val in candidates.items():
        clean_label = label.lower().replace("_", " ").replace("-", " ")
        str_val = _extract_string_value(val)
        if not str_val:
            continue

        # Email
        if extracted["email"] is None and ("email" in clean_label or "e-mail" in clean_label):
            extracted["email"] = str_val
            continue

        # Name
        if extracted["name"] is None and (
            clean_label in {"name", "full name", "your name", "contact name", "client name"}
            or clean_label.startswith("name")
            or "full name" in clean_label
            or "your name" in clean_label
        ):
            extracted["name"] = str_val
            continue

        # Phone
        if extracted["phone"] is None and any(t in clean_label for t in ["phone", "mobile", "contact number", "telephone", "cell"]):
            extracted["phone"] = str_val
            continue

        # Company
        if extracted["company"] is None and any(t in clean_label for t in ["company", "organization", "organisation", "business", "agency"]):
            extracted["company"] = str_val
            continue

        # Service
        if extracted["service"] is None and any(t in clean_label for t in ["service", "interested in", "service requested", "offering", "solution"]):
            extracted["service"] = str_val
            continue

        # Requirements
        if extracted["requirements"] is None and any(t in clean_label for t in [
            "requirement", "description", "detail", "project", "message", "inquiry", "how can we help", "notes", "scope"
        ]):
            extracted["requirements"] = str_val
            continue

        # Budget
        if extracted["budget"] is None and any(t in clean_label for t in ["budget", "investment", "price range", "pricing"]):
            extracted["budget"] = str_val
            continue

        # Consent
        if extracted["consent"] is None and any(t in clean_label for t in ["consent", "permission", "agree", "terms", "opt in", "receive email"]):
            extracted["consent"] = val
            continue

        # Preferred Contact
        if extracted["preferred_contact"] is None and any(t in clean_label for t in [
            "preferred contact", "contact method", "preferred method", "preferred channel",
            "communication preference", "how should we contact", "reach you"
        ]):
            extracted["preferred_contact"] = str_val
            continue

    # 3. Validate Email
    raw_email = extracted["email"]
    if not raw_email:
        raise ValueError("Invalid or missing email address")
    try:
        validated_email = str(_email_adapter.validate_python(raw_email.strip().lower()))
    except ValidationError:
        raise ValueError("Invalid or missing email address")

    # 4. Validate Name
    raw_name = extracted["name"] or ""
    if len(raw_name.strip()) < 2:
        raise ValueError("Name is required (at least 2 characters)")
    clean_name = raw_name.strip()[:100]

    # 5. Validate Service (default to 'General Inquiry' if unspecified)
    raw_service = extracted["service"] or ""
    clean_service = raw_service.strip()[:100] if len(raw_service.strip()) >= 2 else "General Inquiry"

    # 6. Validate Requirements
    raw_requirements = extracted["requirements"] or ""
    if len(raw_requirements.strip()) < 10:
        raise ValueError("Requirements or description must be at least 10 characters")
    clean_requirements = raw_requirements.strip()[:3000]

    # 7. Normalize Optional Fields
    clean_phone = (extracted["phone"] or "").strip()[:20] or None
    clean_company = (extracted["company"] or "").strip()[:150] or None
    clean_budget = (extracted["budget"] or "").strip()[:100] or None

    # 8. Parse Consent
    consent_bool = parse_consent_safely(extracted["consent"])

    # 9. Normalize Preferred Contact (default to 'email')
    raw_contact = (extracted["preferred_contact"] or "").strip().lower()
    if any(k in raw_contact for k in ["phone", "call", "sms", "mobile", "cellular"]):
        pref_contact = "phone"
    elif any(k in raw_contact for k in ["whatsapp", "wa"]):
        pref_contact = "whatsapp"
    else:
        pref_contact = "email"

    return {
        "name": clean_name,
        "email": validated_email,
        "phone": clean_phone,
        "company": clean_company,
        "service": clean_service,
        "requirements": clean_requirements,
        "budget": clean_budget,
        "consent": consent_bool,
        "preferred_contact": pref_contact,
    }


def compute_payload_hash(payload_dict: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of normalized payload data."""
    serialized = json.dumps(payload_dict, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def process_form_submission(
    payload: GoogleFormWebhookPayload,
    store=None,
    service=None,
) -> dict[str, Any]:
    """
    Core business logic for Google Forms webhook processing:
    1. Validate and normalize form data.
    2. Check and enforce durable idempotency via SQLite lead_submissions.
    3. Check whether lead exists in Google Sheets CRM (avoiding duplicate CRM rows).
    4. Generate personalized Groq AI response (separated from email dispatch).
    5. Save/Update 18-column CRM row in Google Sheets.
    6. Emit LEAD_CREATED automation event exactly once.
    7. Guarantee zero automatic email dispatch.
    """
    active_store = store or automation_store
    active_service = service or automation_service

    submission_id = str(payload.submission_id).strip()
    if not submission_id:
        raise ValueError("Submission ID is required")

    # Step 1: Normalize Form Submission Data
    raw_payload_dict = payload.model_dump()
    normalized = normalize_form_submission(raw_payload_dict)
    payload_hash = compute_payload_hash(normalized)

    # Step 2: Durable Idempotency Check in SQLite
    existing_sub = active_store.get_lead_submission(submission_id)
    if existing_sub:
        status = existing_sub["processing_status"]
        if status == "COMPLETED":
            logger.info("Ignoring duplicate completed submission: %s", submission_id)
            return {
                "status": "success",
                "duplicate": True,
                "submission_id": submission_id,
                "lead_id": existing_sub["lead_id"],
                "message": "Submission already processed (idempotent)",
                "processing_status": "COMPLETED",
                "ai_status": "SUCCESS",
                "email_status": "PENDING",
            }
        elif status in ("PENDING", "PROCESSING"):
            logger.info("Submission %s is currently processing", submission_id)
            return {
                "status": "accepted",
                "duplicate": True,
                "submission_id": submission_id,
                "lead_id": existing_sub["lead_id"],
                "message": "Submission is already being processed",
                "processing_status": status,
                "ai_status": "PENDING",
                "email_status": "PENDING",
            }

    # Record new submission record in SQLite (transaction-safe)
    try:
        active_store.create_lead_submission(
            submission_id=submission_id,
            form_id=payload.spreadsheet_id,
            email=normalized["email"],
            payload_hash=payload_hash,
            processing_status="PROCESSING",
        )
    except DuplicateIdempotencyKeyError:
        # Race condition handling: another process inserted between get and create
        sub = active_store.get_lead_submission(submission_id)
        return {
            "status": "accepted",
            "duplicate": True,
            "submission_id": submission_id,
            "lead_id": sub.get("lead_id") if sub else None,
            "message": "Submission already registered",
            "processing_status": sub.get("processing_status", "PROCESSING") if sub else "PROCESSING",
            "ai_status": "PENDING",
            "email_status": "PENDING",
        }

    # Step 3: Check CRM Association (determine whether new or existing lead)
    is_existing_crm_lead = False
    existing_lead_id = None
    try:
        crm_match = find_lead_by_email(normalized["email"])
        if crm_match.get("exists"):
            is_existing_crm_lead = True
            lead_details = get_lead_by_email(normalized["email"])
            if lead_details and lead_details.get("lead_id"):
                existing_lead_id = lead_details["lead_id"]
    except Exception as exc:
        logger.warning("CRM lookup failed for email %s: %s", normalized["email"], exc)

    lead_id = existing_lead_id or f"LF-{uuid.uuid4().hex[:12].upper()}"

    # Step 4: Generate Groq AI Personalization
    lead_create_obj = LeadCreate(
        name=normalized["name"],
        email=normalized["email"],
        phone=normalized["phone"],
        company=normalized["company"],
        service=normalized["service"],
        requirements=normalized["requirements"],
        budget=normalized["budget"],
        preferred_contact=normalized.get("preferred_contact") or "email",
        consent=normalized["consent"],
    )

    ai_subject = ""
    ai_response = ""
    ai_status = "PENDING"
    lead_summary = ""
    suggested_next_step = ""
    ai_error = ""

    try:
        ai_result = generate_personalized_email(lead_create_obj)
        ai_subject = ai_result.subject
        ai_response = ai_result.body
        ai_status = "SUCCESS"
        lead_summary = ai_result.lead_summary
        suggested_next_step = ai_result.suggested_next_step
        logger.info("Groq AI personalization succeeded for form lead: %s", lead_id)
    except Exception as exc:
        ai_status = "FAILED"
        ai_error = f"Groq AI generation failed: {exc}"
        logger.error("Groq AI generation failed for form lead %s: %s", lead_id, exc)

        # Enqueue background retry job in durable automation_jobs
        try:
            active_store.enqueue_job(
                job_type="RETRY_GROQ_PERSONALIZATION",
                payload={
                    "submission_id": submission_id,
                    "lead_id": lead_id,
                    "normalized_lead": normalized,
                },
                max_retries=3,
                idempotency_key=f"retry_groq_{submission_id}",
            )
        except Exception:
            logger.exception("Failed to enqueue Groq retry job for submission %s", submission_id)

    # Step 4b: Save Email Draft & Human Approval Request (Controlled Delivery Workflow)
    draft_id = None
    appr_id = None
    if ai_status == "SUCCESS":
        try:
            draft_idem_key = f"draft_sub_{submission_id}"
            draft = active_store.create_email_draft(
                lead_id=lead_id,
                submission_id=submission_id,
                recipient=normalized["email"],
                subject=ai_subject,
                body=ai_response,
                preferred_contact=normalized.get("preferred_contact") or "email",
                consent=normalized["consent"],
                status="PENDING",
                idempotency_key=draft_idem_key,
            )
            draft_id = draft["id"]

            appr_idem_key = f"appr_draft_{draft['id']}"
            appr = active_store.create_approval_request(
                lead_id=lead_id,
                action_type="SEND_EMAIL",
                action_payload={
                    "draft_id": draft["id"],
                    "lead_id": lead_id,
                    "recipient": normalized["email"],
                    "to_email": normalized["email"],
                    "subject": ai_subject,
                    "body": ai_response,
                    "preferred_contact": normalized.get("preferred_contact") or "email",
                    "consent": normalized["consent"],
                },
                requested_by="google_forms_ai",
                idempotency_key=appr_idem_key,
            )
            appr_id = appr["id"]
            active_store.update_email_draft(draft["id"], approval_id=appr["id"])

            active_store.record_audit_log(
                entity_type="EMAIL_DRAFT",
                entity_id=draft["id"],
                action="DRAFT_CREATED",
                lead_id=lead_id,
                actor="google_forms_ai",
                details={
                    "submission_id": submission_id,
                    "recipient": normalized["email"],
                    "subject": ai_subject,
                    "approval_id": appr["id"],
                },
            )
            logger.info("Saved email draft %s and approval request %s for lead %s", draft_id, appr_id, lead_id)
        except Exception:
            logger.exception("Failed to create email draft or approval for submission %s", submission_id)

    # Step 5: Save or Update Google Sheets CRM Row (18 columns)
    lead_record = {
        "lead_id": lead_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "name": normalized["name"],
        "email": normalized["email"],
        "phone": normalized["phone"] or "",
        "company": normalized["company"] or "",
        "service": normalized["service"],
        "requirements": normalized["requirements"],
        "ai_subject": ai_subject,
        "ai_response": ai_response,
        "email_status": "PENDING",  # SAFETY GUARANTEE: Never automatically send customer email!
        "lead_status": "NEW",
        "error_message": ai_error,
        "budget": normalized["budget"] or "",
        "consent": normalized["consent"],
        "ai_status": ai_status,
        "lead_summary": lead_summary,
        "suggested_next_step": suggested_next_step,
    }

    sheets_sync_failed = False
    sheets_error = ""
    try:
        if is_existing_crm_lead:
            update_lead_crm_row(lead_id, lead_record)
        else:
            append_lead(lead_record)
    except Exception as exc:
        sheets_sync_failed = True
        sheets_error = f"Google Sheets sync failed: {exc}"
        logger.error("Google Sheets sync failed for lead %s: %s", lead_id, exc)

        # Enqueue background retry job in durable automation_jobs
        try:
            active_store.enqueue_job(
                job_type="RETRY_SHEETS_SYNC",
                payload={
                    "submission_id": submission_id,
                    "lead_id": lead_id,
                    "lead_record": lead_record,
                    "is_existing": is_existing_crm_lead,
                },
                max_retries=5,
                idempotency_key=f"retry_sheets_{submission_id}",
            )
        except Exception:
            logger.exception("Failed to enqueue Sheets retry job for submission %s", submission_id)

    # Step 6: Update SQLite Submission Record
    final_processing_status = "COMPLETED"
    combined_error = " | ".join(filter(None, [ai_error, sheets_error]))

    if sheets_sync_failed or ai_status == "FAILED":
        final_processing_status = "PENDING_RETRY" if (sheets_sync_failed or ai_status == "FAILED") else "FAILED"

    active_store.update_lead_submission(
        submission_id=submission_id,
        processing_status=final_processing_status,
        lead_id=lead_id,
        error_message=combined_error,
        email_status="PENDING",
    )

    # Step 7: Emit LEAD_CREATED Automation Event (exactly once via idempotency key)
    try:
        active_service.emit_event(
            trigger_type="LEAD_CREATED",
            lead_id=lead_id,
            context_data={
                "email": normalized["email"],
                "name": normalized["name"],
                "company": normalized["company"] or "",
                "service": normalized["service"],
                "budget": normalized["budget"] or "",
                "consent": normalized["consent"],
                "ai_status": ai_status,
                "source": "google_forms",
                "submission_id": submission_id,
            },
            idempotency_key=f"event_lead_created_{lead_id}",
            actor="google_forms_webhook",
        )
    except Exception:
        logger.exception("Failed to emit LEAD_CREATED event for %s", lead_id)

    return {
        "status": "success" if not sheets_sync_failed else "accepted",
        "duplicate": False,
        "submission_id": submission_id,
        "lead_id": lead_id,
        "message": "Form submission successfully processed" if not sheets_sync_failed else "Form submission recorded; CRM sync queued for retry",
        "processing_status": final_processing_status,
        "ai_status": ai_status,
        "email_status": "PENDING",
        "draft_id": draft_id,
        "approval_id": appr_id,
    }
