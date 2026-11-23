import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.automation_service import automation_worker
from app.services.automation_store import automation_store
from app.services.gmail_intelligence_service import gmail_intelligence_service
from app.services.gmail_sync_service import gmail_store
from app.api.leads import _fetch_crm_leads_safely

logger = logging.getLogger("leadflow")

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard Aggregation"],
)


class MetricCard(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    value: int
    subtitle: str = ""
    trend: str = "neutral"
    color: str = "blue"


class ChartDataPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    value: int
    color: str | None = None


class DashboardOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_leads: int
    hot_leads: int
    warm_leads: int
    cold_leads: int
    pending_followups: int
    overdue_followups: int
    pending_reminders: int
    pending_approvals: int
    active_workflows: int
    total_executions: int
    worker_running: bool
    temperature_distribution: list[ChartDataPoint]
    score_distribution: list[ChartDataPoint]
    task_status_distribution: list[ChartDataPoint]
    workflow_execution_distribution: list[ChartDataPoint]
    lead_creation_trend: list[dict[str, Any]]
    recent_activity: list[dict[str, Any]]
    gmail_overview: dict[str, Any]


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview():
    counts = automation_store.get_overview_counts()
    leads, _ = _fetch_crm_leads_safely()
    total_leads = len(leads) if leads else counts.get("scores_total", 0)

    # Temperature distribution
    hot = counts.get("scores_hot", 0)
    warm = counts.get("scores_warm", 0)
    cold = counts.get("scores_cold", 0)
    temperature_dist = [
        ChartDataPoint(name="HOT", value=hot, color="#ef4444"),
        ChartDataPoint(name="WARM", value=warm, color="#f59e0b"),
        ChartDataPoint(name="COLD", value=cold, color="#3b82f6"),
    ]

    # Score distribution buckets (0-20, 21-40, 41-60, 61-80, 81-100)
    scores = automation_store.get_lead_leaderboard(limit=1000)
    buckets = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    for s in scores:
        val = s.get("score", 0)
        if val <= 20:
            buckets["0-20"] += 1
        elif val <= 40:
            buckets["21-40"] += 1
        elif val <= 60:
            buckets["41-60"] += 1
        elif val <= 80:
            buckets["61-80"] += 1
        else:
            buckets["81-100"] += 1

    score_dist = [
        ChartDataPoint(name=bucket, value=count, color="#6366f1")
        for bucket, count in buckets.items()
    ]

    # Task status distribution
    task_dist = [
        ChartDataPoint(name="SCHEDULED", value=counts.get("tasks_scheduled", 0), color="#3b82f6"),
        ChartDataPoint(name="IN_PROGRESS", value=counts.get("tasks_in_progress", 0), color="#f59e0b"),
        ChartDataPoint(name="COMPLETED", value=counts.get("tasks_completed", 0), color="#10b981"),
        ChartDataPoint(name="CANCELLED", value=counts.get("tasks_cancelled", 0), color="#9ca3af"),
    ]

    # Workflow execution distribution
    exec_dist = [
        ChartDataPoint(name="COMPLETED", value=counts.get("executions_completed", 0), color="#10b981"),
        ChartDataPoint(name="AWAITING_APPROVAL", value=counts.get("executions_awaiting_approval", 0), color="#f59e0b"),
        ChartDataPoint(name="RUNNING", value=counts.get("executions_running", 0), color="#3b82f6"),
        ChartDataPoint(name="FAILED", value=counts.get("executions_failed", 0), color="#ef4444"),
        ChartDataPoint(name="SKIPPED", value=counts.get("executions_skipped", 0), color="#9ca3af"),
    ]

    # Lead creation trend (aggregate by date from lead timestamps if valid)
    trend_map: dict[str, int] = {}
    for l in leads:
        ts = l.get("timestamp") or l.get("created_at")
        if ts:
            date_str = str(ts)[:10]
            if len(date_str) == 10 and "-" in date_str:
                trend_map[date_str] = trend_map.get(date_str, 0) + 1

    lead_trend = [
        {"date": date, "count": count}
        for date, count in sorted(trend_map.items())
    ]

    # Recent activity feed
    audit_logs = automation_store.list_audit_logs(limit=15)
    recent_activity: list[dict[str, Any]] = []
    for log in audit_logs:
        recent_activity.append({
            "id": log.get("id"),
            "action": log.get("action"),
            "entity_type": log.get("entity_type"),
            "entity_id": log.get("entity_id"),
            "lead_id": log.get("lead_id"),
            "actor": log.get("actor", "system"),
            "timestamp": log.get("created_at"),
            "details": log.get("details", {}),
        })

    # Gmail overview counts
    try:
        gmail_counts = gmail_intelligence_service.intelligence_store.overview_counts()
        gmail_overview = {
            "total_messages": gmail_store.count_messages(),
            "matched": gmail_counts.get("matched", 0),
            "unmatched": gmail_counts.get("unmatched", 0),
            "analyzed": gmail_counts.get("analyzed", 0),
            "pending": gmail_counts.get("pending", 0),
        }
    except Exception:
        gmail_overview = {"total_messages": 0, "matched": 0, "unmatched": 0, "analyzed": 0, "pending": 0}

    return {
        "total_leads": total_leads,
        "hot_leads": hot,
        "warm_leads": warm,
        "cold_leads": cold,
        "pending_followups": counts.get("tasks_upcoming", 0),
        "overdue_followups": counts.get("tasks_overdue", 0),
        "pending_reminders": counts.get("reminders_pending", 0),
        "pending_approvals": counts.get("approvals_pending", 0),
        "active_workflows": counts.get("rules_active", 0),
        "total_executions": counts.get("executions_total", 0),
        "worker_running": automation_worker.is_running,
        "temperature_distribution": temperature_dist,
        "score_distribution": score_dist,
        "task_status_distribution": task_dist,
        "workflow_execution_distribution": exec_dist,
        "lead_creation_trend": lead_trend,
        "recent_activity": recent_activity,
        "gmail_overview": gmail_overview,
    }
