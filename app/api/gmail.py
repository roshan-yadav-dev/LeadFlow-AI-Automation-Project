
import asyncio
import logging
import re

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from googleapiclient.errors import HttpError

from app.core.config import settings
from app.core.security import verify_webhook_secret
from app.models.gmail import (
    GmailAnalyzeRequest,
    GmailAnalyzeResponse,
    GmailIntelligenceDetail,
    GmailIntelligenceOverview,
    GmailMatchResponse,
    GmailMessageListResponse,
)
from app.services.gmail_auth import (
    create_oauth_url,
    complete_oauth,
    is_gmail_connected
)
from app.services.gmail_sync_service import (
    sync_inbox,
    gmail_store,
)
from app.services.gmail_intelligence_service import (
    gmail_intelligence_service,
)

router = APIRouter(
    prefix="/api/v1/gmail",
    tags=["Gmail Integration"]
)

logger = logging.getLogger("leadflow")


@router.get("/authorize")
def authorize_gmail():
    try:
        authorization_url, _ = create_oauth_url()

        return RedirectResponse(
            url=authorization_url,
            status_code=302
        )

    except Exception:
        logger.exception("Gmail authorization initialization failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to initialize Gmail authorization"
        )



@router.get("/oauth/callback")
def gmail_oauth_callback(
    request: Request,
    state: str = Query(...),
    code: str = Query(None),
    error: str = Query(None),
):
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"Google authorization failed: {error}",
        )

    if not code:
        raise HTTPException(
            status_code=400,
            detail="Authorization code is missing",
        )

    try:
        complete_oauth(
            authorization_response=str(request.url),
            state=state,
        )

        return {
            "status": "connected",
            "message": "Gmail authorization completed successfully",
        }

    except Exception:
        logger.exception("Gmail OAuth callback failed")
        raise HTTPException(
            status_code=400,
            detail="Gmail authorization failed. Check server logs.",
        )


@router.get("/status")
def gmail_status():
    connected = is_gmail_connected()

    return {
        "connected": connected,
        "sender": settings.GMAIL_SENDER_EMAIL if connected else None
    }


@router.post("/sync")
async def sync_gmail():
    try:
        result = await asyncio.to_thread(sync_inbox)
        if result["status"] == "error":
            raise HTTPException(
                status_code=502,
                detail=result["error"],
            )
        return result
    except HttpError:
        logger.exception("Gmail inbox synchronization failed")
        raise HTTPException(
            status_code=502,
            detail="Unable to synchronize with Gmail",
        )
    except Exception:
        logger.exception("Unexpected Gmail inbox synchronization failure")
        raise HTTPException(
            status_code=500,
            detail="Gmail synchronization failed",
        )


@router.get("/messages", response_model=GmailMessageListResponse)
def list_gmail_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    unread: bool | None = None,
    sender: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
):
    try:
        result = gmail_store.list_messages(
            page=page,
            page_size=page_size,
            unread=unread,
            sender=sender,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )
        return {
            **result,
            "messages": [
                {
                    key: message.get(key)
                    for key in (
                        "message_id",
                        "sender_email",
                        "sender_name",
                        "recipient_email",
                        "subject",
                        "received_timestamp",
                        "snippet",
                        "unread",
                    )
                }
                for message in result["messages"]
            ],
        }
    except Exception:
        logger.exception("Unable to retrieve stored Gmail messages")
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve Gmail messages",
        )


@router.get("/messages/{message_id}")
def get_gmail_message(message_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", message_id):
        raise HTTPException(status_code=400, detail="Invalid message identifier")

    message = gmail_store.get_message(message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


@router.post("/intelligence/match", response_model=GmailMatchResponse)
async def match_gmail_messages(
    authenticated: bool = Depends(verify_webhook_secret),
):
    try:
        result = await asyncio.to_thread(
            gmail_intelligence_service.match_messages
        )
        return {
            "matched": result["matched"],
            "unmatched": result["unmatched"],
            "ambiguous": result["ambiguous"],
            "ignored": result["ignored"],
            "processed": result["processed"],
        }
    except HttpError:
        logger.exception("CRM data could not be loaded for Gmail matching")
        raise HTTPException(
            status_code=502,
            detail="Unable to load CRM leads for Gmail matching",
        )
    except Exception:
        logger.exception("Gmail-to-CRM matching failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to match Gmail messages",
        )


@router.post(
    "/intelligence/analyze",
    response_model=GmailAnalyzeResponse,
)
async def analyze_gmail_messages(
    request: GmailAnalyzeRequest | None = Body(default=None),
    authenticated: bool = Depends(verify_webhook_secret),
):
    configured_limit = max(
        1, settings.GMAIL_INTELLIGENCE_MAX_BATCH_SIZE
    )
    batch_size = (
        request.batch_size
        if request is not None
        else max(1, settings.GMAIL_INTELLIGENCE_BATCH_SIZE)
    )
    force_reanalysis = request.force_reanalysis if request is not None else False
    batch_size = min(batch_size, configured_limit)
    try:
        return await asyncio.to_thread(
            gmail_intelligence_service.analyze_messages,
            batch_size,
            force_reanalysis,
        )
    except Exception:
        logger.exception("Gmail intelligence analysis failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to analyze Gmail messages",
        )


@router.get(
    "/intelligence/overview",
    response_model=GmailIntelligenceOverview,
)
def gmail_intelligence_overview(
    authenticated: bool = Depends(verify_webhook_secret),
):
    try:
        counts = gmail_intelligence_service.intelligence_store.overview_counts()
        return {
            "total_synchronized_messages": gmail_store.count_messages(),
            "total_eligible_messages": (
                counts["matched"] + counts["unmatched"] + counts["ambiguous"]
            ),
            "matched_messages": counts["matched"],
            "unmatched_messages": counts["unmatched"],
            "ignored_messages": counts["ignored"],
            "ambiguous_messages": counts["ambiguous"],
            "analyzed_messages": counts["analyzed"],
            "pending_analyses": counts["pending"],
            "failed_analyses": counts["failed"],
            "intent_category_counts": counts["intents"],
            "sentiment_counts": counts["sentiments"],
        }
    except Exception:
        logger.exception("Unable to retrieve Gmail intelligence overview")
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve Gmail intelligence overview",
        )


@router.get(
    "/intelligence/messages/{message_id}",
    response_model=GmailIntelligenceDetail,
)
def gmail_intelligence_detail(
    message_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", message_id):
        raise HTTPException(status_code=400, detail="Invalid message identifier")
    try:
        result = gmail_intelligence_service.get_detail(message_id)
    except Exception:
        logger.exception("Unable to retrieve Gmail message intelligence")
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve Gmail message intelligence",
        )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Message intelligence record not found",
        )
    return result


@router.post(
    "/intelligence/messages/{message_id}/reanalyze",
    response_model=GmailAnalyzeResponse,
)
async def reanalyze_gmail_message(
    message_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", message_id):
        raise HTTPException(status_code=400, detail="Invalid message identifier")
    if gmail_store.get_message(message_id) is None:
        raise HTTPException(status_code=404, detail="Message not found")
    try:
        return await asyncio.to_thread(
            gmail_intelligence_service.reanalyze_message,
            message_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except HttpError:
        logger.exception("CRM data could not be loaded for reanalysis")
        raise HTTPException(
            status_code=502,
            detail="Unable to verify the associated CRM lead",
        )
    except Exception:
        logger.exception("Gmail intelligence reanalysis failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to reanalyze Gmail message",
        )
