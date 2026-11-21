import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status

from app.core.config import settings
from app.core.security import verify_webhook_secret
from app.models.automation import (
    ApprovalDecision,
    ApprovalExpireResponse,
    ApprovalRequestResponse,
    ApprovalStatus,
    AuditLogResponse,
    AutomationHealthResponse,
    AutomationStatusResponse,
    FollowUpTaskCreate,
    FollowUpTaskReschedule,
    FollowUpTaskResponse,
    FollowUpTaskUpdate,
    JobResponse,
    JobStatus,
    LeadScoreCreate,
    LeadScoreLeaderboardItem,
    LeadScoreRecalculateResponse,
    LeadScoreResponse,
    ReminderCreate,
    ReminderResponse,
    ReminderStatus,
    RuleTriggerRequest,
    ScoreTier,
    TaskPriority,
    TaskStatus,
    WorkflowExecutionCreate,
    WorkflowExecutionResponse,
    WorkflowRuleCreate,
    WorkflowRuleResponse,
    WorkflowRuleUpdate,
    WorkflowTriggerRequest,
    WorkflowTriggerType,
)
from app.services.automation_service import (
    AutomationWorker,
    InvalidLeadIdError,
    InvalidStateError,
    automation_service,
    automation_worker,
)
from app.services.automation_store import (
    DuplicateIdempotencyKeyError,
    EntityNotFoundError,
    automation_store,
)

logger = logging.getLogger("leadflow")

router = APIRouter(
    prefix="/api/v1/automation",
    tags=["Lead Automation"],
)


# --- Health & Status ---
@router.get("/health", response_model=AutomationHealthResponse)
def automation_health():
    """Unauthenticated health check for automation foundation."""
    return {
        "status": "healthy",
        "database": "connected",
        "worker_running": automation_worker.is_running,
        "project": settings.PROJECT_NAME,
    }


@router.get("/status", response_model=AutomationStatusResponse)
def automation_status(
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Protected overview of automation system status and queue counts."""
    counts = automation_store.get_overview_counts()
    return {
        "status": "active",
        "database": "connected",
        "worker_running": automation_worker.is_running,
        "default_timezone": settings.AUTOMATION_DEFAULT_TIMEZONE,
        "counts": counts,
    }


# --- 1. Lead Scores ---
@router.get(
    "/scores/leaderboard",
    response_model=list[LeadScoreLeaderboardItem],
)
def get_lead_scores_leaderboard(
    limit: int = Query(default=50, ge=1, le=200),
    tier: ScoreTier | None = None,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Retrieve ranked leaderboard of leads sorted by score DESC."""
    return automation_service.get_lead_leaderboard(limit=limit, tier=tier)


@router.post(
    "/scores/recalculate",
    response_model=LeadScoreRecalculateResponse,
)
def recalculate_all_scores(
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Recalculate scores for all CRM leads using deterministic business logic."""
    return automation_service.recalculate_all_scores(actor="webhook_client")


@router.post(
    "/scores/calculate/{lead_id}",
    response_model=LeadScoreResponse,
)
def calculate_lead_score(
    lead_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Calculate and persist deterministic score for a single lead."""
    try:
        return automation_service.calculate_and_save_score(
            lead_id=lead_id, actor="webhook_client"
        )
    except InvalidLeadIdError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/scores",
    response_model=LeadScoreResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lead_score(
    payload: LeadScoreCreate,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Record a lead score."""
    try:
        return automation_service.record_lead_score(
            lead_id=payload.lead_id,
            score=payload.score,
            tier=payload.tier,
            factors=payload.factors,
            version=payload.version,
            idempotency_key=payload.idempotency_key,
            actor="webhook_client",
        )
    except InvalidLeadIdError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DuplicateIdempotencyKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/scores/{lead_id}",
    response_model=LeadScoreResponse,
)
def get_latest_lead_score(
    lead_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Retrieve latest lead score, or calculate on the fly if not existing."""
    try:
        return automation_service.get_latest_lead_score(lead_id)
    except (InvalidLeadIdError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/scores/{lead_id}/history",
    response_model=list[LeadScoreResponse],
)
def list_lead_score_history(
    lead_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Retrieve score history for a lead."""
    try:
        return automation_service.list_lead_score_history(lead_id)
    except InvalidLeadIdError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# --- 2. Follow-Up Tasks ---
@router.get(
    "/tasks/upcoming",
    response_model=list[FollowUpTaskResponse],
)
def list_upcoming_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List scheduled upcoming follow-up tasks (scheduled_for >= now)."""
    return automation_service.list_upcoming_tasks(limit=limit, offset=offset)


@router.get(
    "/tasks/overdue",
    response_model=list[FollowUpTaskResponse],
)
def list_overdue_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List overdue follow-up tasks (scheduled_for < now and status active)."""
    return automation_service.list_overdue_tasks(limit=limit, offset=offset)


@router.post(
    "/tasks",
    response_model=FollowUpTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_follow_up_task(
    payload: FollowUpTaskCreate,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Create and schedule a follow-up task."""
    try:
        return automation_service.create_follow_up_task(
            lead_id=payload.lead_id,
            title=payload.title,
            scheduled_for=payload.scheduled_for,
            description=payload.description,
            timezone_str=payload.timezone,
            priority=payload.priority,
            channel=payload.channel,
            generate_reminder=payload.generate_reminder,
            reminder_minutes_before=payload.reminder_minutes_before,
            metadata=payload.metadata,
            idempotency_key=payload.idempotency_key,
            actor="webhook_client",
        )
    except InvalidLeadIdError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DuplicateIdempotencyKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/tasks",
    response_model=list[FollowUpTaskResponse],
)
def list_follow_up_tasks(
    lead_id: str | None = None,
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = None,
    channel: str | None = None,
    upcoming_only: bool = False,
    overdue_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List tasks with flexible filtering and pagination."""
    try:
        offset = (page - 1) * page_size
        return automation_service.list_follow_up_tasks(
            lead_id=lead_id,
            status=status_filter,
            priority=priority,
            channel=channel,
            upcoming_only=upcoming_only,
            overdue_only=overdue_only,
            limit=page_size,
            offset=offset,
        )
    except InvalidLeadIdError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/tasks/{task_id}",
    response_model=FollowUpTaskResponse,
)
def get_follow_up_task(
    task_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Retrieve task details."""
    try:
        return automation_service.get_follow_up_task(task_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch(
    "/tasks/{task_id}",
    response_model=FollowUpTaskResponse,
)
def update_follow_up_task(
    task_id: str,
    payload: FollowUpTaskUpdate,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Update task details."""
    try:
        return automation_service.update_follow_up_task(
            task_id=task_id,
            status=payload.status,
            description=payload.description,
            priority=payload.priority,
            scheduled_for=payload.scheduled_for,
            timezone_str=payload.timezone,
            metadata=payload.metadata,
            actor="webhook_client",
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/tasks/{task_id}/reschedule",
    response_model=FollowUpTaskResponse,
)
def reschedule_follow_up_task(
    task_id: str,
    payload: FollowUpTaskReschedule,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Reschedule task to a new target time."""
    try:
        return automation_service.reschedule_task(
            task_id=task_id,
            new_scheduled_for=payload.scheduled_for,
            timezone_str=payload.timezone,
            actor="webhook_client",
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/tasks/{task_id}/complete",
    response_model=FollowUpTaskResponse,
)
def complete_follow_up_task(
    task_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Mark task as completed."""
    try:
        return automation_service.complete_task(task_id=task_id, actor="webhook_client")
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=FollowUpTaskResponse,
)
def cancel_follow_up_task(
    task_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Mark task as cancelled."""
    try:
        return automation_service.cancel_task(task_id=task_id, actor="webhook_client")
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# --- 3. Reminders ---
@router.get(
    "/reminders/pending",
    response_model=list[ReminderResponse],
)
def list_pending_reminders(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List pending reminders."""
    return automation_service.list_pending_reminders(limit=limit, offset=offset)


@router.post(
    "/reminders",
    response_model=ReminderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_reminder(
    payload: ReminderCreate,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Create and schedule a reminder."""
    try:
        return automation_service.create_reminder(
            lead_id=payload.lead_id,
            title=payload.title,
            remind_at=payload.remind_at,
            task_id=payload.task_id,
            timezone_str=payload.timezone,
            recipient=payload.recipient,
            channel=payload.channel,
            idempotency_key=payload.idempotency_key,
            actor="webhook_client",
        )
    except (InvalidLeadIdError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DuplicateIdempotencyKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/reminders",
    response_model=list[ReminderResponse],
)
def list_reminders(
    lead_id: str | None = None,
    task_id: str | None = None,
    status_filter: ReminderStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List reminders with filters."""
    try:
        offset = (page - 1) * page_size
        return automation_service.list_reminders(
            lead_id=lead_id,
            task_id=task_id,
            status=status_filter,
            limit=page_size,
            offset=offset,
        )
    except InvalidLeadIdError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/reminders/{reminder_id}",
    response_model=ReminderResponse,
)
def get_reminder(
    reminder_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Retrieve reminder details."""
    try:
        return automation_service.get_reminder(reminder_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/reminders/{reminder_id}/dismiss",
    response_model=ReminderResponse,
)
def dismiss_reminder(
    reminder_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Dismiss a reminder so it will not trigger."""
    try:
        return automation_service.dismiss_reminder(
            reminder_id=reminder_id, actor="webhook_client"
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# --- 4. Workflow Rules & Executions ---
@router.post(
    "/rules",
    response_model=WorkflowRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow_rule(
    payload: WorkflowRuleCreate,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Define a workflow rule."""
    return automation_service.create_workflow_rule(
        name=payload.name,
        trigger_type=payload.trigger_type,
        conditions=payload.conditions,
        actions=payload.actions,
        requires_approval=payload.requires_approval,
        is_active=payload.is_active,
        actor="webhook_client",
    )


@router.get(
    "/rules",
    response_model=list[WorkflowRuleResponse],
)
def list_workflow_rules(
    trigger_type: WorkflowTriggerType | None = None,
    is_active: bool | None = None,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List workflow rules."""
    return automation_service.list_workflow_rules(
        trigger_type=trigger_type, is_active=is_active
    )


@router.get(
    "/rules/{rule_id}",
    response_model=WorkflowRuleResponse,
)
def get_workflow_rule(
    rule_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Retrieve workflow rule details."""
    try:
        return automation_service.get_workflow_rule(rule_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch(
    "/rules/{rule_id}",
    response_model=WorkflowRuleResponse,
)
def update_workflow_rule(
    rule_id: str,
    payload: WorkflowRuleUpdate,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Update workflow rule attributes."""
    try:
        return automation_service.update_workflow_rule(
            rule_id=rule_id,
            name=payload.name,
            conditions=payload.conditions,
            actions=payload.actions,
            requires_approval=payload.requires_approval,
            is_active=payload.is_active,
            actor="webhook_client",
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete(
    "/rules/{rule_id}",
)
def delete_workflow_rule(
    rule_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Delete a workflow rule."""
    try:
        success = automation_service.delete_workflow_rule(
            rule_id=rule_id, actor="webhook_client"
        )
        return {"deleted": success, "rule_id": rule_id}
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/rules/{rule_id}/trigger",
    response_model=WorkflowExecutionResponse,
)
def trigger_workflow_rule_by_id(
    rule_id: str,
    payload: RuleTriggerRequest,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Manually trigger a specific rule for a lead."""
    try:
        return automation_service.trigger_workflow_execution(
            rule_id=rule_id,
            lead_id=payload.lead_id,
            trigger_event="MANUAL_TRIGGER",
            context_data=payload.context_data,
            idempotency_key=payload.idempotency_key,
            actor="manual_trigger",
        )
    except InvalidLeadIdError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DuplicateIdempotencyKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))



@router.post(
    "/workflows/trigger",
    response_model=list[WorkflowExecutionResponse],
)
def trigger_workflow_for_lead(
    payload: WorkflowTriggerRequest,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Trigger active workflow rules for a lead by event type."""
    try:
        return automation_service.emit_event(
            trigger_type=payload.trigger_type,
            lead_id=payload.lead_id,
            context_data=payload.context_data,
            idempotency_key=payload.idempotency_key,
            actor="manual_trigger",
        )
    except InvalidLeadIdError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/executions",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
def trigger_specific_workflow_execution(
    payload: WorkflowExecutionCreate,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Execute a specific rule for a lead."""
    try:
        return automation_service.trigger_workflow_execution(
            rule_id=payload.rule_id,
            lead_id=payload.lead_id,
            trigger_event=payload.trigger_event,
            context_data=payload.context_data,
            idempotency_key=payload.idempotency_key,
            actor="webhook_client",
        )
    except (InvalidLeadIdError, EntityNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DuplicateIdempotencyKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/executions",
    response_model=list[WorkflowExecutionResponse],
)
def list_workflow_executions(
    lead_id: str | None = None,
    rule_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List workflow executions."""
    try:
        offset = (page - 1) * page_size
        return automation_service.list_workflow_executions(
            lead_id=lead_id,
            rule_id=rule_id,
            status=status_filter,
            limit=page_size,
            offset=offset,
        )
    except InvalidLeadIdError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/executions/{execution_id}",
    response_model=WorkflowExecutionResponse,
)
def get_workflow_execution(
    execution_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Retrieve execution details."""
    try:
        return automation_service.get_workflow_execution(execution_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))



# --- 5. Approvals (Human-in-the-Loop Safeguard) ---
@router.get(
    "/approvals/pending",
    response_model=list[ApprovalRequestResponse],
)
def list_pending_approvals(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List pending approval requests."""
    return automation_service.list_approval_requests(status="PENDING", limit=limit, offset=offset)


@router.post(
    "/approvals/expire-stale",
    response_model=ApprovalExpireResponse,
)
def expire_stale_approvals(
    max_age_hours: int = Query(default=72, ge=1, le=720),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Expire stale pending approval requests."""
    expired = automation_service.expire_stale_approvals(max_age_hours=max_age_hours)
    return {
        "expired_count": len(expired),
        "expired_ids": [a["id"] for a in expired],
    }


@router.get(
    "/approvals",
    response_model=list[ApprovalRequestResponse],
)
def list_approval_requests(
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
    lead_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List approval requests."""
    try:
        offset = (page - 1) * page_size
        return automation_service.list_approval_requests(
            status=status_filter,
            lead_id=lead_id,
            limit=page_size,
            offset=offset,
        )
    except InvalidLeadIdError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/approvals/{approval_id}",
    response_model=ApprovalRequestResponse,
)
def get_approval_request(
    approval_id: str,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Retrieve approval request details."""
    try:
        return automation_service.get_approval_request(approval_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/approvals/{approval_id}/decision",
    response_model=ApprovalRequestResponse,
)
def record_approval_decision(
    approval_id: str,
    payload: ApprovalDecision,
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Record human approval decision (APPROVE or REJECT)."""
    try:
        return automation_service.record_approval_decision(
            approval_id=approval_id,
            action=payload.action,
            reviewed_by=payload.reviewed_by,
            rejection_reason=payload.rejection_reason,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# --- 6. Audit Logs ---
@router.get(
    "/audit-logs",
    response_model=list[AuditLogResponse],
)
def list_audit_logs(
    entity_type: str | None = None,
    entity_id: str | None = None,
    lead_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Retrieve automation audit logs."""
    offset = (page - 1) * page_size
    return automation_service.list_audit_logs(
        entity_type=entity_type,
        entity_id=entity_id,
        lead_id=lead_id,
        limit=page_size,
        offset=offset,
    )


# --- 7. Background Jobs ---
@router.get(
    "/jobs",
    response_model=list[JobResponse],
)
def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    job_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """List persistent background queue jobs."""
    offset = (page - 1) * page_size
    return automation_store.list_jobs(
        status=status_filter,
        job_type=job_type,
        limit=page_size,
        offset=offset,
    )


@router.post(
    "/jobs/process",
    response_model=dict[str, int],
)
async def process_jobs_now(
    batch_size: int = Query(default=10, ge=1, le=50),
    authenticated: bool = Depends(verify_webhook_secret),
):
    """Manually trigger background job processing."""
    return await asyncio.to_thread(automation_service.process_due_jobs, batch_size=batch_size)
