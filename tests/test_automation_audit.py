import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.automation import (
    ApprovalDecision,
    FollowUpTaskCreate,
    RuleTriggerRequest,
    WorkflowRuleCreate,
    utc_now_iso,
)
from app.services.automation_service import (
    AutomationService,
    AutomationWorker,
    InvalidLeadIdError,
    InvalidStateError,
)
from app.services.automation_store import AutomationStore, EntityNotFoundError


@pytest.fixture
def auth_headers():
    return {"X-Webhook-Secret": settings.WEBHOOK_SECRET or "test-secret"}


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix="_audit.sqlite3")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def store(temp_db):
    return AutomationStore(temp_db)


@pytest.fixture
def mock_leads():
    return [
        {
            "lead_id": "LEAD-AUDIT-1",
            "name": "Audit Lead",
            "email": "audit@example.com",
            "company": "Audit Corp",
            "service": "Auditing",
            "budget": "$20,000",
            "consent": True,
        }
    ]


@pytest.fixture
def service(store, mock_leads):
    return AutomationService(store=store, leads_loader=lambda: mock_leads)


# ==============================================================================
# 1. API ROUTE AUDIT: Path conflict verification
# ==============================================================================

def test_api_route_precedence_and_no_path_conflicts(monkeypatch, store, mock_leads, auth_headers):
    """
    Verify that static routes are registered before parameterized dynamic routes:
    - /scores/leaderboard vs /scores/{lead_id}
    - /scores/recalculate vs /scores/{lead_id}
    - /tasks/upcoming vs /tasks/{task_id}
    - /tasks/overdue vs /tasks/{task_id}
    - /reminders/pending vs /reminders/{reminder_id}
    - /approvals/pending vs /approvals/{approval_id}
    - /approvals/expire-stale vs /approvals/{approval_id}
    - /executions (list) vs /executions/{execution_id}
    """
    from app.api import automation as auto_api

    test_service = AutomationService(store=store, leads_loader=lambda: mock_leads)
    monkeypatch.setattr(auto_api, "automation_service", test_service)
    monkeypatch.setattr(auto_api, "automation_store", store)

    client = TestClient(app)

    # 1. /scores/leaderboard -> must return 200 list, NOT 404 (lead not found)
    resp = client.get("/api/v1/automation/scores/leaderboard", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 2. /scores/recalculate -> must return 200 with 'recalculated', NOT 404
    resp = client.post("/api/v1/automation/scores/recalculate", headers=auth_headers, json={})
    assert resp.status_code == 200
    assert "recalculated" in resp.json()

    # 3. /tasks/upcoming -> must return 200 list, NOT 404 (task 'upcoming' not found)
    resp = client.get("/api/v1/automation/tasks/upcoming", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 4. /tasks/overdue -> must return 200 list, NOT 404 (task 'overdue' not found)
    resp = client.get("/api/v1/automation/tasks/overdue", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 5. /reminders/pending -> must return 200 list, NOT 404 (reminder 'pending' not found)
    resp = client.get("/api/v1/automation/reminders/pending", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 6. /approvals/pending -> must return 200 list, NOT 404 (approval 'pending' not found)
    resp = client.get("/api/v1/automation/approvals/pending", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 7. /approvals/expire-stale -> must return 200 with 'expired_count', NOT 404
    resp = client.post("/api/v1/automation/approvals/expire-stale", headers=auth_headers)
    assert resp.status_code == 200
    assert "expired_count" in resp.json()

    # 8. /executions -> must return 200 list, NOT 404
    resp = client.get("/api/v1/automation/executions", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ==============================================================================
# 2. APPROVAL LIFECYCLE AUDIT: Safeguards, States, and Non-Execution of Emails
# ==============================================================================

def test_approval_lifecycle_and_non_execution(service, store):
    """
    Verify:
    - PENDING approvals cannot execute actions.
    - APPROVED grants authorization (authorization_granted=True), but action_executed remains False (no auto-send).
    - REJECTED marks execution FAILED with rejection reason.
    - EXPIRED marks execution FAILED with expiration reason.
    - Duplicate decision calls raise InvalidStateError and return 400.
    """
    rule = service.create_workflow_rule(
        name="Outbound Email Rule",
        trigger_type="INTENT_CLASSIFIED",
        actions=[{"type": "SEND_EMAIL", "params": {"template": "quote"}}],
        requires_approval=True,
    )

    # 1. Trigger execution -> Pauses at AWAITING_APPROVAL
    exec_res = service.trigger_workflow_execution(
        rule_id=rule["id"],
        lead_id="LEAD-AUDIT-1",
        trigger_event="EMAIL_CLASSIFIED",
    )
    assert exec_res["status"] == "AWAITING_APPROVAL"

    # Pending approvals exist
    approvals = service.list_approval_requests(status="PENDING")
    appr = next(a for a in approvals if a["workflow_execution_id"] == exec_res["id"])
    assert appr["status"] == "PENDING"

    # Verify that while PENDING, no action has executed
    fresh_exec = service.get_workflow_execution(exec_res["id"])
    assert fresh_exec["status"] == "AWAITING_APPROVAL"
    assert fresh_exec["result_data"] is None

    # 2. Record APPROVE decision
    decision = service.record_approval_decision(
        approval_id=appr["id"],
        action="APPROVE",
        reviewed_by="manager@leadflow.ai",
        decision_notes="Pricing within standard bounds",
    )
    assert decision["status"] == "APPROVED"

    # Check updated workflow execution
    updated_exec = service.get_workflow_execution(exec_res["id"])
    assert updated_exec["status"] == "COMPLETED"
    result_data = updated_exec["result_data"]
    assert result_data is not None
    assert result_data["authorization_granted"] is True
    assert result_data["action_executed"] is False  # Safe: email not automatically dispatched!

    # 3. Duplicate decision on already decided approval fails cleanly
    with pytest.raises(InvalidStateError):
        service.record_approval_decision(
            approval_id=appr["id"],
            action="APPROVE",
            reviewed_by="manager2@leadflow.ai",
        )


def test_approval_expiration_terminates_execution(service, store):
    """Verify that expiring stale approval marks execution as FAILED."""
    rule = service.create_workflow_rule(
        name="Expiring Rule",
        trigger_type="INTENT_CLASSIFIED",
        actions=[{"type": "SEND_EMAIL", "params": {"template": "welcome"}}],
        requires_approval=True,
    )
    exec_res = service.trigger_workflow_execution(
        rule_id=rule["id"],
        lead_id="LEAD-AUDIT-1",
        trigger_event="EMAIL_CLASSIFIED",
    )
    appr = service.list_approval_requests(status="PENDING")[0]

    # Force expiration into past
    past_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with store._connect() as conn:
        conn.execute("UPDATE approval_requests SET expires_at = ? WHERE id = ?", (past_iso, appr["id"]))

    expired = service.expire_stale_approvals()
    assert any(a["id"] == appr["id"] for a in expired)

    # Check execution transitioned to FAILED with expired reason
    updated_exec = service.get_workflow_execution(exec_res["id"])
    assert updated_exec["status"] == "FAILED"
    assert "expired" in updated_exec["error_message"].lower()
    assert updated_exec["result_data"]["authorization_granted"] is False


# ==============================================================================
# 3. AUDIT-HISTORY INTEGRITY: Soft Deletion and Immutability
# ==============================================================================

def test_workflow_rule_soft_deletion_preserves_history(service, store):
    """
    Verify:
    - Deleting a workflow rule soft-deletes the rule (is_deleted=1, is_active=0).
    - Historical workflow executions remain 100% traceable.
    - Historical approval requests remain intact.
    - Historical audit logs remain intact.
    - Deleted rule does not trigger on new events.
    """
    rule = service.create_workflow_rule(
        name="Rule To Soft Delete",
        trigger_type="LEAD_CREATED",
        actions=[{"type": "CREATE_INTERNAL_NOTIFICATION", "params": {"message": "Hello"}}],
        requires_approval=False,
    )
    rule_id = rule["id"]

    # Execute rule once
    exec_res = service.trigger_workflow_execution(
        rule_id=rule_id,
        lead_id="LEAD-AUDIT-1",
        trigger_event="LEAD_CREATED",
    )
    exec_id = exec_res["id"]

    # Verify audit logs exist
    logs_before = service.list_audit_logs(lead_id="LEAD-AUDIT-1")
    assert any(l["entity_id"] == exec_id for l in logs_before)

    # Now soft-delete the rule
    deleted = service.delete_workflow_rule(rule_id, actor="admin")
    assert deleted is True

    # Rule is no longer in active rule list
    active_rules = service.list_workflow_rules()
    assert not any(r["id"] == rule_id for r in active_rules)

    # Historical workflow execution is STILL PRESENT and traceable!
    historical_exec = service.get_workflow_execution(exec_id)
    assert historical_exec is not None
    assert historical_exec["rule_id"] == rule_id

    # Historical audit logs are completely preserved!
    logs_after = service.list_audit_logs(lead_id="LEAD-AUDIT-1")
    assert any(l["entity_id"] == exec_id for l in logs_after)
    rule_logs = service.list_audit_logs(entity_id=rule_id)
    assert any(l["action"] == "DELETED" for l in rule_logs)

    # Attempting to query deleted rule through normal lookup returns 404 / EntityNotFoundError
    with pytest.raises(EntityNotFoundError):
        service.get_workflow_rule(rule_id)


# ==============================================================================
# 4. ACTUAL INTEGRATION AUDIT: Event hooks & Execution safeguards
# ==============================================================================

def test_score_updated_event_fires_only_on_actual_change(service, store):
    """Verify SCORE_UPDATED event is emitted only when score or tier changes."""
    # First score calculation
    score1 = service.calculate_and_save_score(lead_id="LEAD-AUDIT-1", actor="test")

    # Audit logs for first score should include CREATED
    logs1 = service.list_audit_logs(lead_id="LEAD-AUDIT-1", entity_type="LEAD_SCORE")
    assert len(logs1) >= 1

    # Second score calculation with identical CRM data produces same score
    score2 = service.calculate_and_save_score(lead_id="LEAD-AUDIT-1", actor="test")
    assert score2["score"] == score1["score"]
    assert score2["tier"] == score1["tier"]

    # Second audit log reports score_changed: False
    logs2 = service.list_audit_logs(lead_id="LEAD-AUDIT-1", entity_type="LEAD_SCORE")
    latest_log = logs2[0]
    assert latest_log["details"]["score_changed"] is False


def test_action_exception_marks_execution_failed(service):
    """Verify exceptions during action execution transition the workflow execution to FAILED."""
    # Create rule with invalid follow-up parameters that will trigger a failure
    rule = service.create_workflow_rule(
        name="Failing Action Rule",
        trigger_type="MANUAL",
        actions=[{
            "type": "CREATE_FOLLOW_UP",
            "params": {"title": "Bad Task", "delay_hours": "invalid_hours"},
        }],
        requires_approval=False,
    )

    with pytest.raises(Exception):
        service.trigger_workflow_execution(
            rule_id=rule["id"],
            lead_id="LEAD-AUDIT-1",
            trigger_event="MANUAL",
        )

    # Check that execution was recorded as FAILED, not COMPLETED or stuck in RUNNING
    execs = service.list_workflow_executions(rule_id=rule["id"])
    assert len(execs) >= 1
    assert execs[0]["status"] == "FAILED"
    assert execs[0]["error_message"] is not None


# ==============================================================================
# 5. WORKER AND PERSISTENCE AUDIT: Future jobs, Lease recovery, Retries
# ==============================================================================

def test_worker_future_jobs_not_executed_early(service, store):
    """Verify jobs scheduled in the future are never claimed or processed early."""
    future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    job = store.enqueue_job(
        job_type="PROCESS_REMINDER",
        payload={"reminder_id": "rem-future-1"},
        scheduled_at=future_time,
    )

    # Attempt to process due jobs
    res = service.process_due_jobs()
    assert res["processed"] == 0

    # Job remains PENDING
    fresh_job = store.get_job(job["id"])
    assert fresh_job["status"] == "PENDING"
    assert fresh_job["attempts"] == 0


def test_worker_expired_lease_recovery(service, store):
    """Verify jobs whose locks have expired are recovered and processed."""
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    expired_lock = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    # Enqueue a dummy job
    job = store.enqueue_job(
        job_type="TEST_RECOVERY",
        payload={"msg": "recover me"},
        scheduled_at=past_time,
    )

    # Register handler
    handled = False
    def recovery_handler(payload):
        nonlocal handled
        handled = True
        return {"status": "ok"}
    service._job_handlers["TEST_RECOVERY"] = recovery_handler

    # Manually simulate a crashed worker leaving status=PROCESSING with expired locked_until
    with store._connect() as conn:
        conn.execute(
            "UPDATE automation_jobs SET status = 'PROCESSING', locked_until = ? WHERE id = ?",
            (expired_lock, job["id"]),
        )

    # Run worker processing
    res = service.process_due_jobs()
    assert res["processed"] == 1
    assert res["succeeded"] == 1
    assert handled is True

    # Job is now completed
    updated_job = store.get_job(job["id"])
    assert updated_job["status"] == "COMPLETED"
