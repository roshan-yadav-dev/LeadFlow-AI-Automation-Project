import logging
import uuid
from typing import Any
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.services.automation_store import (
    AutomationError,
    AutomationStore,
    DuplicateIdempotencyKeyError,
    EntityNotFoundError,
    InvalidStateError,
    automation_store,
)
from app.services.lead_service import _lock_lead_email
from app.services.gmail_auth import is_gmail_connected
from app.services.gmail_service import send_email
from app.services.sheets_service import update_lead_email_status

logger = logging.getLogger("leadflow")
_email_adapter = TypeAdapter(EmailStr)


class EmailDeliveryError(AutomationError):
    """Base exception for email delivery domain."""
    pass


class ConsentMissingError(EmailDeliveryError):
    """Raised when email delivery is attempted without explicit customer consent."""
    pass


class InvalidContactChannelError(EmailDeliveryError):
    """Raised when preferred contact channel is not Email."""
    pass


class InvalidRecipientError(EmailDeliveryError):
    """Raised when recipient email is empty or invalid."""
    pass


class DuplicateSendError(EmailDeliveryError):
    """Raised when an email has already been delivered and repeated dispatch is attempted."""
    pass


class DraftNotApprovedError(EmailDeliveryError):
    """Raised when email dispatch is attempted on a non-approved draft."""
    pass


class GmailDeliveryError(EmailDeliveryError):
    """Raised when Gmail API or OAuth connectivity blocks dispatch."""
    pass


class EmailDeliveryService:
    def __init__(self, store: AutomationStore | None = None):
        self.store = store or automation_store

    def get_draft(self, draft_id: str) -> dict:
        draft = self.store.get_email_draft(draft_id)
        if not draft:
            raise EntityNotFoundError(f"Email draft '{draft_id}' not found")
        return draft

    def list_drafts(
        self,
        lead_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        offset = (page - 1) * page_size
        drafts = self.store.list_email_drafts(
            lead_id=lead_id,
            status=status,
            limit=page_size,
            offset=offset,
        )
        total = self.store.count_email_drafts(lead_id=lead_id, status=status)
        return drafts, total

    def approve_draft(
        self,
        draft_id: str,
        reviewed_by: str,
        decision_notes: str | None = None,
    ) -> dict:
        draft = self.get_draft(draft_id)

        if draft["status"] == "APPROVED":
            return draft

        if draft["status"] != "PENDING":
            raise InvalidStateError(
                f"Email draft '{draft_id}' cannot be approved because it is in '{draft['status']}' state."
            )

        updated_draft = self.store.record_email_draft_approved(
            draft_id=draft_id,
            approved_by=reviewed_by,
        )

        # Synchronize linked approval request if one exists and is pending
        if draft.get("approval_id"):
            try:
                appr = self.store.get_approval_request(draft["approval_id"])
                if appr and appr.get("status") == "PENDING":
                    self.store.record_approval_decision(
                        approval_id=draft["approval_id"],
                        action="APPROVE",
                        reviewed_by=reviewed_by,
                    )
            except Exception:
                logger.warning(
                    "Could not sync linked approval_request %s for draft %s",
                    draft["approval_id"],
                    draft_id,
                    exc_info=True,
                )

        # Synchronize Google Sheets CRM row (email_status = "APPROVED")
        try:
            update_lead_email_status(
                lead_id=draft["lead_id"],
                email_status="APPROVED",
                error_message="",
            )
        except Exception:
            logger.warning(
                "Could not update Google Sheets email_status to APPROVED for lead %s",
                draft["lead_id"],
                exc_info=True,
            )

        if draft.get("submission_id"):
            try:
                self.store.update_lead_submission(
                    submission_id=draft["submission_id"],
                    processing_status="COMPLETED",
                    email_status="APPROVED",
                )
            except Exception:
                pass

        self.store.record_audit_log(
            entity_type="EMAIL_DRAFT",
            entity_id=draft_id,
            action="APPROVED",
            lead_id=draft["lead_id"],
            actor=reviewed_by,
            details={
                "action": "APPROVED",
                "decision_notes": decision_notes,
                "approval_id": draft.get("approval_id"),
            },
        )
        logger.info("Email draft %s approved by %s (NOT sent; awaiting explicit send)", draft_id, reviewed_by)
        return updated_draft

    def reject_draft(
        self,
        draft_id: str,
        reviewed_by: str,
        rejection_reason: str,
    ) -> dict:
        if not rejection_reason or not rejection_reason.strip():
            raise ValueError("Rejection reason is strictly required")

        draft = self.get_draft(draft_id)

        if draft["status"] == "REJECTED":
            return draft

        if draft["status"] != "PENDING":
            raise InvalidStateError(
                f"Email draft '{draft_id}' cannot be rejected because it is in '{draft['status']}' state."
            )

        updated_draft = self.store.update_email_draft(
            draft_id,
            status="REJECTED",
            error_message=f"Rejected: {rejection_reason.strip()}",
        )

        if draft.get("approval_id"):
            try:
                appr = self.store.get_approval_request(draft["approval_id"])
                if appr and appr.get("status") == "PENDING":
                    self.store.record_approval_decision(
                        approval_id=draft["approval_id"],
                        action="REJECT",
                        reviewed_by=reviewed_by,
                        rejection_reason=rejection_reason.strip(),
                    )
            except Exception:
                logger.warning(
                    "Could not sync linked approval_request %s for draft %s",
                    draft["approval_id"],
                    draft_id,
                    exc_info=True,
                )

        try:
            update_lead_email_status(
                lead_id=draft["lead_id"],
                email_status="FAILED",
                error_message=f"Rejected: {rejection_reason.strip()}",
            )
        except Exception:
            logger.warning(
                "Could not update Google Sheets email_status to FAILED for lead %s",
                draft["lead_id"],
                exc_info=True,
            )

        self.store.record_audit_log(
            entity_type="EMAIL_DRAFT",
            entity_id=draft_id,
            action="REJECTED",
            lead_id=draft["lead_id"],
            actor=reviewed_by,
            details={
                "action": "REJECTED",
                "rejection_reason": rejection_reason.strip(),
                "approval_id": draft.get("approval_id"),
            },
        )
        logger.info("Email draft %s rejected by %s", draft_id, reviewed_by)
        return updated_draft

    def send_approved_draft(
        self,
        draft_id: str,
        actor: str = "operator",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Executes explicit, authenticated send action for an approved email draft.
        Enforces:
        - Human approval prerequisite.
        - Strict consent check (consent == True).
        - Preferred contact channel check (preferred_contact == 'email').
        - Valid recipient email check.
        - Duplicate prevention (never resends already sent emails).
        - Safe handling of uncertain outcomes (prevents blind retries).
        - Complete logging in audit logs, SQLite, and Google Sheets CRM.
        """
        draft = self.get_draft(draft_id)
        recipient = str(draft.get("recipient", "")).strip().lower()

        # Thread-safe locking per recipient email to prevent race conditions
        with _lock_lead_email(recipient):
            # Refresh draft state inside the lock
            draft = self.get_draft(draft_id)

            # 1. Duplicate check: Has this draft already been delivered?
            if draft["status"] == "SENT" or draft.get("gmail_message_id"):
                msg_id = draft.get("gmail_message_id")
                logger.warning(
                    "Duplicate send prevented for draft %s (already SENT with Gmail ID %s)",
                    draft_id,
                    msg_id,
                )
                raise DuplicateSendError(
                    f"Email draft '{draft_id}' has already been delivered (Gmail ID: {msg_id}). Duplicate dispatch blocked."
                )

            # 2. Status check: Must be APPROVED (or retry on FAILED after being approved)
            if draft["status"] == "PENDING":
                logger.warning("Attempted to send unapproved email draft %s", draft_id)
                raise DraftNotApprovedError(
                    f"Email draft '{draft_id}' has not been approved. Explicit human approval is required before sending."
                )

            if draft["status"] in ("REJECTED", "EXPIRED"):
                raise InvalidStateError(
                    f"Email draft '{draft_id}' is in '{draft['status']}' state and cannot be sent."
                )

            # 3. Consent check: Only send when communication consent is explicitly true
            if not draft.get("consent"):
                logger.warning("Sending blocked for draft %s: consent is false", draft_id)
                raise ConsentMissingError(
                    "Communication consent was not granted by the lead. Outbound dispatch is strictly blocked."
                )

            # 4. Preferred Contact check: Respect Preferred Contact = Email
            pref_contact = str(draft.get("preferred_contact", "")).strip().lower()
            if pref_contact != "email":
                logger.warning(
                    "Sending blocked for draft %s: preferred_contact is '%s' (not 'email')",
                    draft_id,
                    pref_contact,
                )
                raise InvalidContactChannelError(
                    f"Lead specified preferred contact method as '{draft.get('preferred_contact')}', not 'email'. Outbound email dispatch is blocked."
                )

            # 5. Recipient validation: Never send to an empty or invalid email address
            if not recipient or "@" not in recipient:
                raise InvalidRecipientError("A valid recipient email address is required.")
            try:
                validated_recipient = str(_email_adapter.validate_python(recipient))
            except ValidationError:
                raise InvalidRecipientError("A valid recipient email address is required.")

            # 6. Check Gmail connection
            if not is_gmail_connected():
                err_msg = "Gmail is not connected or its credentials are invalid. Connect Gmail before sending."
                logger.error("Gmail connection check failed for sending draft %s", draft_id)
                self.store.record_email_draft_failed(
                    draft_id=draft_id,
                    error_message=err_msg,
                    error_code="AUTHENTICATION_ERROR",
                )
                try:
                    update_lead_email_status(
                        lead_id=draft["lead_id"],
                        email_status="FAILED",
                        error_message=err_msg,
                    )
                except Exception:
                    pass
                if draft.get("submission_id"):
                    try:
                        self.store.update_lead_submission(
                            submission_id=draft["submission_id"],
                            processing_status="COMPLETED",
                            email_status="FAILED",
                        )
                    except Exception:
                        pass

                self.store.record_audit_log(
                    entity_type="EMAIL_DRAFT",
                    entity_id=draft_id,
                    action="SEND_FAILED",
                    lead_id=draft["lead_id"],
                    actor=actor,
                    details={
                        "error_code": "AUTHENTICATION_ERROR",
                        "error_message": err_msg,
                    },
                )
                raise GmailDeliveryError(err_msg)

            # 7. Generate outbound operation identifier
            outbound_op_id = idempotency_key or f"outbound_{draft_id}_{uuid.uuid4().hex[:8]}"

            # 8. Dispatch through Gmail API
            logger.info("Executing deliberate email send for draft %s to %s", draft_id, validated_recipient)
            send_result = send_email(
                to_email=validated_recipient,
                subject=draft["subject"],
                body=draft["body"],
                html_body=draft.get("html_body"),
            )

            # 9. Process Result
            if send_result.get("success"):
                message_id = send_result.get("message_id")
                thread_id = send_result.get("thread_id")

                self.store.record_email_draft_sent(
                    draft_id=draft_id,
                    gmail_message_id=message_id,
                    gmail_thread_id=thread_id,
                    sent_by=actor,
                )

                # Synchronize Google Sheets CRM row
                try:
                    update_lead_email_status(
                        lead_id=draft["lead_id"],
                        email_status="SENT",
                        error_message="",
                    )
                except Exception as exc:
                    logger.error("Failed to update Sheets CRM status to SENT for lead %s: %s", draft["lead_id"], exc)

                if draft.get("submission_id"):
                    try:
                        self.store.update_lead_submission(
                            submission_id=draft["submission_id"],
                            processing_status="COMPLETED",
                            email_status="SENT",
                        )
                    except Exception:
                        pass

                self.store.record_audit_log(
                    entity_type="EMAIL_DRAFT",
                    entity_id=draft_id,
                    action="SENT",
                    lead_id=draft["lead_id"],
                    actor=actor,
                    details={
                        "recipient": validated_recipient,
                        "subject": draft["subject"],
                        "gmail_message_id": message_id,
                        "gmail_thread_id": thread_id,
                        "outbound_operation_id": outbound_op_id,
                    },
                )
                logger.info("Email draft %s successfully delivered with Gmail Message ID %s", draft_id, message_id)
                return {
                    "success": True,
                    "status": "SENT",
                    "draft_id": draft_id,
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "error_code": None,
                    "error_message": None,
                    "ambiguous": False,
                }
            else:
                error_msg = send_result.get("error_message") or "Gmail rejected the email request."
                error_code = send_result.get("error_code") or "GMAIL_API_ERROR"
                ambiguous = bool(send_result.get("ambiguous", False))

                self.store.record_email_draft_failed(
                    draft_id=draft_id,
                    error_message=error_msg,
                    error_code=error_code,
                )

                # Synchronize Google Sheets CRM row
                try:
                    update_lead_email_status(
                        lead_id=draft["lead_id"],
                        email_status="FAILED",
                        error_message=error_msg,
                    )
                except Exception as exc:
                    logger.error("Failed to update Sheets CRM status to FAILED for lead %s: %s", draft["lead_id"], exc)

                if draft.get("submission_id"):
                    try:
                        self.store.update_lead_submission(
                            submission_id=draft["submission_id"],
                            processing_status="COMPLETED",
                            email_status="FAILED",
                        )
                    except Exception:
                        pass

                self.store.record_audit_log(
                    entity_type="EMAIL_DRAFT",
                    entity_id=draft_id,
                    action="SEND_FAILED",
                    lead_id=draft["lead_id"],
                    actor=actor,
                    details={
                        "recipient": validated_recipient,
                        "error_code": error_code,
                        "error_message": error_msg,
                        "ambiguous": ambiguous,
                        "outbound_operation_id": outbound_op_id,
                    },
                )
                logger.warning(
                    "Email draft %s send failed (%s: %s, ambiguous=%s)",
                    draft_id,
                    error_code,
                    error_msg,
                    ambiguous,
                )
                return {
                    "success": False,
                    "status": "FAILED",
                    "draft_id": draft_id,
                    "message_id": None,
                    "thread_id": None,
                    "error_code": error_code,
                    "error_message": error_msg,
                    "ambiguous": ambiguous,
                }

    def send_lead_email(
        self,
        lead_id: str,
        actor: str = "operator",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Send the latest approved draft for a given lead ID.
        """
        drafts = self.store.list_email_drafts(lead_id=lead_id, limit=10)
        if not drafts:
            raise EntityNotFoundError(f"No email drafts found for lead '{lead_id}'")

        # Find latest approved draft
        approved_draft = next((d for d in drafts if d["status"] == "APPROVED"), None)
        if not approved_draft:
            # Check if latest draft is pending
            latest = drafts[0]
            if latest["status"] == "SENT":
                raise DuplicateSendError(f"Email for lead '{lead_id}' has already been sent (Gmail ID: {latest.get('gmail_message_id')}).")
            if latest["status"] == "PENDING":
                raise DraftNotApprovedError(f"Email draft for lead '{lead_id}' is pending approval. Human approval is strictly required before sending.")
            raise InvalidStateError(f"Email draft for lead '{lead_id}' is in '{latest['status']}' state.")

        return self.send_approved_draft(
            draft_id=approved_draft["id"],
            actor=actor,
            idempotency_key=idempotency_key,
        )


email_delivery_service = EmailDeliveryService()
