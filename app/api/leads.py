
import logging
import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from googleapiclient.errors import HttpError

from app.models.lead import (
    LeadCreate,
    LeadResponse,
    LeadListItem,
    LeadListResponse,
    LeadDetailResponse,
)
from app.models.forms import (
    GoogleFormWebhookPayload,
    GoogleFormWebhookResponse,
)
from app.core.security import verify_webhook_secret
from app.core.dashboard_auth import dashboard_auth
from app.services.lead_service import process_lead
from app.services.form_service import process_form_submission
from app.models.gmail import LeadCommunicationHistory
from app.services.gmail_intelligence_service import (
    gmail_intelligence_service,
)
from app.services.sheets_service import list_leads_for_matching
from app.services.automation_store import automation_store
from app.services.automation_service import automation_service
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

router = APIRouter(
    prefix="/api/v1/leads",
    tags=["Lead Management"]
)

logger = logging.getLogger("leadflow")


@router.post(
    "",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED
)
def create_lead(
    lead: LeadCreate,
    authenticated: bool = Depends(verify_webhook_secret)
):

    try:
        result = process_lead(lead)

        if result["duplicate"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A lead with this email already exists"
            )

        return {
            "lead_id": result["lead_id"],
            "message": result["message"],
            "status": result["status"],
            "email": result["email"],
            "ai_status": result["ai_status"],
            "email_status": result["email_status"],
            "email_status_updated": result["email_status_updated"],
            "email_error": result["email_error"],
            "email_message_id": result["email_message_id"],
            "email_thread_id": result["email_thread_id"],
        }

    except HTTPException:
        raise

    except HttpError:
        logger.exception("Google Sheets API failure")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to save lead to Google Sheets"
        )

    except Exception:
        logger.exception("Unexpected lead processing failure")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lead processing failed"
        )


@router.post(
    "/webhook/forms",
    response_model=GoogleFormWebhookResponse,
    status_code=status.HTTP_200_OK,
)
def handle_google_forms_webhook(
    payload: GoogleFormWebhookPayload,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """
    Ingest and process Google Form / Apps Script submissions:
    - Verifies webhook authentication.
    - Validates and normalizes varied question labels.
    - Persists submission idempotency in SQLite.
    - Enforces fail-safe consent (missing/ambiguous consent -> False).
    - Generates Groq AI personalization.
    - Appends new or updates existing Google Sheets CRM row.
    - Emits LEAD_CREATED automation event.
    - Strictly never dispatches emails automatically.
    """
    try:
        result = process_form_submission(payload)
        return result
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error processing Google Form webhook")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Form processing error: {exc}",
        )


@router.get(
    "/{lead_id}/communications",
    response_model=LeadCommunicationHistory,
)
async def get_lead_communications(
    lead_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    try:
        result = await asyncio.to_thread(
            gmail_intelligence_service.lead_communications,
            lead_id,
            page,
            page_size,
        )
    except HttpError:
        logger.exception("CRM data could not be loaded for lead communications")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to load CRM lead data",
        )
    except Exception:
        logger.exception("Unable to retrieve lead communications")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve lead communications",
        )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    return result


def _fetch_crm_leads_safely() -> tuple[list[dict[str, Any]], bool]:
    """Fetch CRM leads from Google Sheets, or fallback to local intelligence / scores if offline."""
    try:
        leads = list_leads_for_matching()
        return leads, True
    except Exception as exc:
        logger.warning("CRM lead loading from Google Sheets failed: %s", exc)
        # Fallback to local intelligence / score records
        local_leads: dict[str, dict[str, Any]] = {}
        try:
            with gmail_intelligence_service.intelligence_store._connect() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT lead_id FROM gmail_message_intelligence WHERE lead_id IS NOT NULL AND lead_id != ''"
                ).fetchall()
                for row in rows:
                    lid = row[0]
                    local_leads[lid] = {
                        "lead_id": lid,
                        "name": f"Lead {lid}",
                        "email": "",
                        "company": "",
                        "service": "General Inquiry",
                        "requirements": "",
                        "lead_status": "NEW",
                        "budget": "",
                        "consent": True,
                        "timestamp": "",
                    }
        except Exception:
            pass

        try:
            scores = automation_store.get_lead_leaderboard(limit=100)
            for sc in scores:
                lid = sc["lead_id"]
                if lid not in local_leads:
                    local_leads[lid] = {
                        "lead_id": lid,
                        "name": f"Lead {lid}",
                        "email": "",
                        "company": "",
                        "service": "General Inquiry",
                        "requirements": "",
                        "lead_status": "NEW",
                        "budget": "",
                        "consent": True,
                        "timestamp": sc.get("created_at", ""),
                    }
        except Exception:
            pass

        return list(local_leads.values()), False


@router.get("", response_model=LeadListResponse)
def list_leads(
    search: str | None = None,
    status: str | None = None,
    tier: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    raw_leads, crm_synced = _fetch_crm_leads_safely()

    enriched_leads: list[dict[str, Any]] = []
    for l in raw_leads:
        lid = str(l.get("lead_id", "")).strip()
        if not lid:
            continue

        item = dict(l)
        # Fetch score
        score_rec = automation_store.get_latest_lead_score(lid)
        if score_rec:
            item["score"] = score_rec.get("score")
            item["tier"] = score_rec.get("tier")
        else:
            item["score"] = None
            item["tier"] = None

        # Fetch intelligence info
        records, _ = gmail_intelligence_service.intelligence_store.list_by_lead(lid, limit=5, offset=0)
        if records:
            latest_rec = records[0]
            item["intent"] = latest_rec.get("intent_category")
            item["sentiment"] = latest_rec.get("sentiment")
            item["last_interaction"] = (
                latest_rec.get("received_timestamp")
                or latest_rec.get("analyzed_at")
                or latest_rec.get("created_at")
            )
        else:
            item["intent"] = None
            item["sentiment"] = None
            item["last_interaction"] = item.get("timestamp") or None

        item["created_at"] = item.get("timestamp") or None
        enriched_leads.append(item)

    # Search filter
    if search:
        s = search.strip().lower()
        enriched_leads = [
            l for l in enriched_leads
            if s in str(l.get("name", "")).lower()
            or s in str(l.get("email", "")).lower()
            or s in str(l.get("company", "")).lower()
            or s in str(l.get("lead_id", "")).lower()
        ]

    # Status filter
    if status:
        stat_filter = status.strip().upper()
        enriched_leads = [
            l for l in enriched_leads
            if str(l.get("lead_status", "")).strip().upper() == stat_filter
        ]

    # Tier filter
    if tier:
        t_filter = tier.strip().upper()
        enriched_leads = [
            l for l in enriched_leads
            if str(l.get("tier", "")).strip().upper() == t_filter
        ]

    # Sort
    reverse = sort_order.lower() == "desc"
    if sort_by == "score":
        enriched_leads.sort(key=lambda x: (x.get("score") is not None, x.get("score") or 0), reverse=reverse)
    elif sort_by == "name":
        enriched_leads.sort(key=lambda x: str(x.get("name", "")).lower(), reverse=reverse)
    elif sort_by == "company":
        enriched_leads.sort(key=lambda x: str(x.get("company", "")).lower(), reverse=reverse)
    else:  # created_at / timestamp
        enriched_leads.sort(key=lambda x: str(x.get("created_at") or ""), reverse=reverse)

    total = len(enriched_leads)
    offset = (page - 1) * page_size
    paged = enriched_leads[offset : offset + page_size]

    return {
        "leads": paged,
        "total": total,
        "page": page,
        "page_size": page_size,
        "crm_synced": crm_synced,
    }


@router.get("/{lead_id}", response_model=LeadDetailResponse)
def get_lead_details(
    lead_id: str,
):
    raw_leads, _ = _fetch_crm_leads_safely()
    lead = next(
        (l for l in raw_leads if str(l.get("lead_id", "")).strip() == lead_id.strip()),
        None,
    )

    if not lead:
        # Check intelligence or score store
        if not automation_service.validate_lead_exists(lead_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lead '{lead_id}' not found",
            )
        lead = {
            "lead_id": lead_id,
            "name": f"Lead {lead_id}",
            "email": "",
            "company": "",
            "service": "General Inquiry",
            "requirements": "",
            "lead_status": "NEW",
            "email_status": "PENDING",
            "ai_status": "PENDING",
            "budget": "",
            "consent": True,
            "created_at": None,
            "error_message": "",
        }

    # Fetch associated data
    score = automation_store.get_latest_lead_score(lead_id)
    score_history = automation_store.list_lead_score_history(lead_id)
    tasks = automation_store.list_follow_up_tasks(lead_id=lead_id, limit=50)
    reminders = automation_store.list_reminders(lead_id=lead_id, limit=50)
    executions = automation_store.list_workflow_executions(lead_id=lead_id, limit=50)
    approvals = automation_store.list_approval_requests(lead_id=lead_id, limit=50)
    records, _ = gmail_intelligence_service.intelligence_store.list_by_lead(lead_id, limit=50, offset=0)
    audit_logs = automation_store.list_audit_logs(lead_id=lead_id, limit=50)
    email_drafts = automation_store.list_email_drafts(lead_id=lead_id, limit=50)

    # Timeline construction
    timeline: list[dict[str, Any]] = []
    for log in audit_logs:
        timeline.append({
            "type": "AUDIT",
            "title": f"{log.get('action')}: {log.get('entity_type')}",
            "timestamp": log.get("created_at"),
            "details": log.get("details", {}),
            "actor": log.get("actor", "system"),
        })
    for exc in executions:
        timeline.append({
            "type": "WORKFLOW_EXECUTION",
            "title": f"Workflow Triggered: {exc.get('trigger_event')} ({exc.get('status')})",
            "timestamp": exc.get("created_at"),
            "details": exc.get("result_data") or {"rule_id": exc.get("rule_id")},
            "actor": "workflow_engine",
        })
    for rec in records:
        timeline.append({
            "type": "COMMUNICATION",
            "title": f"Email Analyzed: {rec.get('intent_category', 'Inquiry')}",
            "timestamp": rec.get("analyzed_at") or rec.get("created_at"),
            "details": {
                "sentiment": rec.get("sentiment"),
                "summary": rec.get("summary"),
                "confidence": rec.get("confidence"),
            },
            "actor": "gmail_intelligence",
        })

    timeline.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)

    return {
        "lead_id": lead.get("lead_id"),
        "name": lead.get("name", ""),
        "email": lead.get("email", ""),
        "phone": lead.get("phone", ""),
        "company": lead.get("company", ""),
        "service": lead.get("service", ""),
        "requirements": lead.get("requirements", ""),
        "lead_status": lead.get("lead_status", "NEW"),
        "email_status": lead.get("email_status", "PENDING"),
        "ai_status": lead.get("ai_status", "PENDING"),
        "budget": lead.get("budget", ""),
        "consent": lead.get("consent", False),
        "created_at": lead.get("timestamp") or lead.get("created_at"),
        "error_message": lead.get("error_message", ""),
        "score": score,
        "score_history": score_history,
        "tasks": tasks,
        "reminders": reminders,
        "workflow_executions": executions,
        "approvals": approvals,
        "intelligence_records": records,
        "email_drafts": email_drafts,
        "activity_timeline": timeline,
    }


@router.post(
    "/{lead_id}/send-email",
    status_code=status.HTTP_200_OK,
)
def send_email_for_lead(
    lead_id: str,
    request: Request,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """
    Explicit, deliberate send action for a lead's approved email draft.
    """
    session = dashboard_auth.get_session_from_request(request)
    actor = session.username if session else "operator"
    try:
        return email_delivery_service.send_lead_email(lead_id=lead_id, actor=actor)
    except DuplicateSendError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except DraftNotApprovedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except (ConsentMissingError, InvalidContactChannelError, InvalidRecipientError, InvalidStateError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except GmailDeliveryError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to send email for lead %s", lead_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

