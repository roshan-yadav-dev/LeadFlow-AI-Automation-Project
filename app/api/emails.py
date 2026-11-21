import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status

from app.core.dashboard_auth import dashboard_auth
from app.core.security import verify_webhook_secret
from app.models.automation import (
    EmailDraftDecisionRequest,
    EmailDraftListResponse,
    EmailDraftResponse,
    EmailSendResponse,
)
from app.services.automation_store import (
    DuplicateIdempotencyKeyError,
    EntityNotFoundError,
    InvalidStateError,
)
from app.services.email_delivery_service import (
    ConsentMissingError,
    DraftNotApprovedError,
    DuplicateSendError,
    EmailDeliveryError,
    GmailDeliveryError,
    InvalidContactChannelError,
    InvalidRecipientError,
    email_delivery_service,
)

logger = logging.getLogger("leadflow")

router = APIRouter(
    prefix="/api/v1/automation/emails",
    tags=["Email Delivery & Drafts"],
)


def _get_actor(request: Request) -> str:
    session = dashboard_auth.get_session_from_request(request)
    if session:
        return session.username
    return "operator"


@router.get(
    "/drafts",
    response_model=EmailDraftListResponse,
)
def list_email_drafts(
    lead_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List email drafts with filtering by lead ID and status."""
    drafts, total = email_delivery_service.list_drafts(
        lead_id=lead_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return {
        "drafts": drafts,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/drafts/{draft_id}",
    response_model=EmailDraftResponse,
)
def get_email_draft(
    draft_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Retrieve details for a single email draft."""
    try:
        return email_delivery_service.get_draft(draft_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/drafts/{draft_id}/approve",
    response_model=EmailDraftResponse,
)
def approve_email_draft(
    draft_id: str,
    request: Request,
    payload: EmailDraftDecisionRequest | None = Body(default=None),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """
    Approve an email draft for sending.
    SAFETY GUARANTEE: Approval grants authorization only; it does NOT send the email.
    """
    actor = _get_actor(request)
    decision_notes = payload.decision_notes if payload else None
    try:
        return email_delivery_service.approve_draft(
            draft_id=draft_id,
            reviewed_by=actor,
            decision_notes=decision_notes,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/drafts/{draft_id}/reject",
    response_model=EmailDraftResponse,
)
def reject_email_draft(
    draft_id: str,
    request: Request,
    payload: EmailDraftDecisionRequest = Body(...),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Reject an email draft and permanently block dispatch."""
    actor = _get_actor(request)
    reason = payload.rejection_reason or ""
    if not reason.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rejection reason is required",
        )
    try:
        return email_delivery_service.reject_draft(
            draft_id=draft_id,
            reviewed_by=actor,
            rejection_reason=reason,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/drafts/{draft_id}/send",
    response_model=EmailSendResponse,
)
def send_approved_email(
    draft_id: str,
    request: Request,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """
    Deliberate, explicit action to send an approved email via the Gmail API.
    Enforces:
    - Must be explicitly APPROVED (approval alone does not send).
    - Customer consent must be True.
    - Preferred Contact method must be Email.
    - Valid recipient email address.
    - Duplicate send prevention.
    """
    actor = _get_actor(request)
    try:
        result = email_delivery_service.send_approved_draft(
            draft_id=draft_id,
            actor=actor,
        )
        return result
    except DuplicateSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except DraftNotApprovedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except (ConsentMissingError, InvalidContactChannelError, InvalidRecipientError, InvalidStateError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except GmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Unexpected error sending email draft %s", draft_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email delivery failed: {exc}",
        )


@router.post(
    "/leads/{lead_id}/send",
    response_model=EmailSendResponse,
)
def send_lead_email(
    lead_id: str,
    request: Request,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Send the latest approved email draft for a specific lead."""
    actor = _get_actor(request)
    try:
        result = email_delivery_service.send_lead_email(
            lead_id=lead_id,
            actor=actor,
        )
        return result
    except DuplicateSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except DraftNotApprovedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except (ConsentMissingError, InvalidContactChannelError, InvalidRecipientError, InvalidStateError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except GmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Unexpected error sending email for lead %s", lead_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email delivery failed: {exc}",
        )
