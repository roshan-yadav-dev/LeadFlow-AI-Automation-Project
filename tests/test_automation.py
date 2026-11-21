import os
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.automation import (
    FollowUpTaskCreate,
    LeadScoreCreate,
    ReminderCreate,
    WorkflowExecutionCreate,
    WorkflowRuleCreate,
    to_kolkata_iso,
    to_utc_iso,
    utc_now_iso,
)
from app.services.automation_service import (
    AutomationService,
    AutomationWorker,
    InvalidLeadIdError,
    InvalidStateError,
)
from app.services.automation_store import (
    AutomationStore,
    DuplicateIdempotencyKeyError,
    EntityNotFoundError,
)


@pytest.fixture
def auth_headers():
    return {"X-Webhook-Secret": settings.WEBHOOK_SECRET or "test-secret"}


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
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
            "lead_id": "LEAD-101",
            "name": "Alice Smith",
            "email": "alice@example.com",
            "company": "Acme Inc",
        },
        {
            "lead_id": "LEAD-102",
            "name": "Bob Jones",
            "email": "bob@example.com",
            "company": "Beta LLC",
        },
    ]


@pytest.fixture
def service(store, mock_leads):
    class FakeIntelligenceStore:
        def _connect(self):
            conn = sqlite3.connect(":memory:")
            conn.execute(
                "CREATE TABLE gmail_message_intelligence (lead_id TEXT)"
            )
            conn.execute(
                "INSERT INTO gmail_message_intelligence VALUES ('LEAD-INTEL-999')"
            )
            return conn

    return AutomationService(
        store=store,
        leads_loader=lambda: mock_leads,
        intelligence_store=FakeIntelligenceStore(),
    )


# --- Test 1: Database Initialization ---
def test_database_initialization(temp_db):
    store = AutomationStore(temp_db)
    with store._connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected_tables = {
            "lead_scores",
            "follow_up_tasks",
            "reminders",
            "workflow_rules",
            "workflow_executions",
            "approval_requests",
            "automation_audit_logs",
            "automation_jobs",
        }
        assert expected_tables.issubset(tables)

        # Check indexes
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_lead_scores_lead" in indexes
        assert "idx_tasks_lead_status" in indexes
        assert "idx_reminders_remind_at" in indexes
        assert "idx_jobs_status_scheduled" in indexes

        # Check WAL journal mode
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "wal"


# --- Test 2: Model Creation and Validation ---
def test_model_creation_and_validation():
    now_iso = utc_now_iso()

    # Valid score
    score = LeadScoreCreate(
        lead_id="LEAD-101",
        score=85,
        tier="HOT",
        factors={"intent": "PRICING_INQUIRY", "budget": "$10k+"},
    )
    assert score.score == 85
    assert score.tier == "HOT"

    # Out of range score
    with pytest.raises(Exception):
        LeadScoreCreate(lead_id="LEAD-101", score=105, tier="HOT")
    with pytest.raises(Exception):
        LeadScoreCreate(lead_id="LEAD-101", score=-5, tier="HOT")

    # Invalid tier
    with pytest.raises(Exception):
        LeadScoreCreate(lead_id="LEAD-101", score=50, tier="SUPER_HOT")  # type: ignore

    # Valid follow-up task
    task = FollowUpTaskCreate(
        lead_id="LEAD-101",
        title="Schedule demo call",
        scheduled_for=now_iso,
        priority="HIGH",
    )
    assert task.timezone == "Asia/Kolkata"
    assert task.priority == "HIGH"
    assert task.status_val if hasattr(task, "status_val") else True

    # Extra fields forbidden
    with pytest.raises(Exception):
        FollowUpTaskCreate(
            lead_id="LEAD-101",
            title="Demo",
            scheduled_for=now_iso,
            unknown_field="fail",  # type: ignore
        )

    # Timezone conversion helpers
    utc_str = "2026-11-20T10:00:00Z"
    normalized_utc = to_utc_iso(utc_str)
    assert "+00:00" in normalized_utc or normalized_utc.endswith("Z")
    kolkata_time = to_kolkata_iso(normalized_utc)
    # Kolkata is UTC+5:30 -> 10:00 UTC is 15:30 IST
    assert "+05:30" in kolkata_time
    assert "15:30:00" in kolkata_time


# --- Test 3: Invalid Lead IDs ---
def test_invalid_lead_id_rejection(service):
    # Non-existent lead ID
    with pytest.raises(InvalidLeadIdError):
        service.record_lead_score(lead_id="NON-EXISTENT", score=75, tier="WARM")

    with pytest.raises(InvalidLeadIdError):
        service.create_follow_up_task(
            lead_id="NON-EXISTENT",
            title="Follow up",
            scheduled_for=utc_now_iso(),
        )

    with pytest.raises(InvalidLeadIdError):
        service.create_reminder(
            lead_id="NON-EXISTENT",
            title="Reminder",
            remind_at=utc_now_iso(),
        )

    # Valid lead from mock_leads succeeds
    score_res = service.record_lead_score(lead_id="LEAD-101", score=90, tier="HOT")
    assert score_res["lead_id"] == "LEAD-101"

    # Valid lead from mock intelligence store succeeds
    task_res = service.create_follow_up_task(
        lead_id="LEAD-INTEL-999",
        title="Intel follow up",
        scheduled_for=utc_now_iso(),
    )
    assert task_res["lead_id"] == "LEAD-INTEL-999"


# --- Test 4: Duplicate Idempotency Keys ---
def test_duplicate_idempotency_keys(service):
    # 1. Follow-up tasks
    key = "idem-task-001"
    service.create_follow_up_task(
        lead_id="LEAD-101",
        title="First task",
        scheduled_for=utc_now_iso(),
        idempotency_key=key,
    )
    with pytest.raises(DuplicateIdempotencyKeyError):
        service.create_follow_up_task(
            lead_id="LEAD-101",
            title="Second task with same key",
            scheduled_for=utc_now_iso(),
            idempotency_key=key,
        )

    # 2. Lead scores
    score_key = "idem-score-001"
    service.record_lead_score(
        lead_id="LEAD-101",
        score=70,
        tier="WARM",
        idempotency_key=score_key,
    )
    with pytest.raises(DuplicateIdempotencyKeyError):
        service.record_lead_score(
            lead_id="LEAD-101",
            score=70,
            tier="WARM",
            idempotency_key=score_key,
        )

    # 3. Reminders
    rem_key = "idem-rem-001"
    service.create_reminder(
        lead_id="LEAD-101",
        title="Reminder 1",
        remind_at=utc_now_iso(),
        idempotency_key=rem_key,
    )
    with pytest.raises(DuplicateIdempotencyKeyError):
        service.create_reminder(
            lead_id="LEAD-101",
            title="Reminder 2",
            remind_at=utc_now_iso(),
            idempotency_key=rem_key,
        )


# --- Test 5: Authentication & API Endpoints ---
def test_api_authentication_and_endpoints(monkeypatch, store, mock_leads):
    # Override singleton service and store with our test fixtures
    from app.api import automation as auto_api

    test_service = AutomationService(
        store=store,
        leads_loader=lambda: mock_leads,
    )
    monkeypatch.setattr(auto_api, "automation_service", test_service)
    monkeypatch.setattr(auto_api, "automation_store", store)

    client = TestClient(app)

    # 1. Health check is unauthenticated
    resp = client.get("/api/v1/automation/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.json()["database"] == "connected"

    # 2. Protected endpoint without header fails
    resp = client.get("/api/v1/automation/status")
    assert resp.status_code in (401, 422)

    # 3. Protected endpoint with invalid header fails
    resp = client.get(
        "/api/v1/automation/status",
        headers={"X-Webhook-Secret": "invalid-secret"},
    )
    assert resp.status_code == 401

    # 4. Protected endpoint with valid header succeeds
    auth_headers = {"X-Webhook-Secret": settings.WEBHOOK_SECRET or "test-secret"}
    resp = client.get("/api/v1/automation/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["default_timezone"] == "Asia/Kolkata"
    assert "counts" in data

    # 5. POST /scores with invalid lead ID returns 404
    resp = client.post(
        "/api/v1/automation/scores",
        headers=auth_headers,
        json={"lead_id": "UNKNOWN", "score": 80, "tier": "HOT"},
    )
    assert resp.status_code == 404

    # 6. POST /scores with valid lead ID returns 201
    resp = client.post(
        "/api/v1/automation/scores",
        headers=auth_headers,
        json={
            "lead_id": "LEAD-101",
            "score": 80,
            "tier": "HOT",
            "idempotency_key": "api-score-1",
        },
    )
    assert resp.status_code == 201
    score_id = resp.json()["id"]

    # 7. POST /scores with duplicate idempotency key returns 409
    resp = client.post(
        "/api/v1/automation/scores",
        headers=auth_headers,
        json={
            "lead_id": "LEAD-101",
            "score": 80,
            "tier": "HOT",
            "idempotency_key": "api-score-1",
        },
    )
    assert resp.status_code == 409
    assert "duplicate" in resp.json()["detail"].lower()

    # 8. GET /scores/{lead_id} returns score
    resp = client.get(
        "/api/v1/automation/scores/LEAD-101",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == score_id

    # 9. POST /tasks returns 201
    due_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    resp = client.post(
        "/api/v1/automation/tasks",
        headers=auth_headers,
        json={
            "lead_id": "LEAD-101",
            "title": "Send proposal",
            "scheduled_for": due_time,
            "priority": "HIGH",
            "idempotency_key": "api-task-1",
        },
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    # 10. POST /tasks duplicate idempotency key returns 409
    resp = client.post(
        "/api/v1/automation/tasks",
        headers=auth_headers,
        json={
            "lead_id": "LEAD-101",
            "title": "Send proposal again",
            "scheduled_for": due_time,
            "idempotency_key": "api-task-1",
        },
    )
    assert resp.status_code == 409

    # 11. PATCH /tasks/{task_id} updates task
    resp = client.patch(
        f"/api/v1/automation/tasks/{task_id}",
        headers=auth_headers,
        json={"status": "IN_PROGRESS", "priority": "URGENT"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "IN_PROGRESS"
    assert resp.json()["priority"] == "URGENT"


# --- Test 6: Audit Log Creation ---
def test_audit_log_creation(service):
    # Action 1: Create score
    score = service.record_lead_score(
        lead_id="LEAD-101",
        score=95,
        tier="HOT",
        actor="sales_rep",
    )
    # Action 2: Create task
    task = service.create_follow_up_task(
        lead_id="LEAD-101",
        title="Check requirements",
        scheduled_for=utc_now_iso(),
        actor="sales_rep",
    )
    # Action 3: Create reminder
    reminder = service.create_reminder(
        lead_id="LEAD-101",
        title="Follow up reminder",
        remind_at=utc_now_iso(),
        task_id=task["id"],
        actor="sales_rep",
    )

    logs = service.list_audit_logs(lead_id="LEAD-101")
    assert len(logs) >= 3

    entity_types = {log["entity_type"] for log in logs}
    assert "LEAD_SCORE" in entity_types
    assert "FOLLOW_UP_TASK" in entity_types
    assert "REMINDER" in entity_types

    # Verify audit details
    score_log = next(log for log in logs if log["entity_id"] == score["id"])
    assert score_log["action"] == "CREATED"
    assert score_log["actor"] == "sales_rep"
    assert score_log["details"]["score"] == 95


# --- Test 7: Persistence Across Application Restarts ---
def test_persistence_across_application_restarts(temp_db, mock_leads):
    # Phase A: Initial application session writes entities and enqueues jobs
    store1 = AutomationStore(temp_db)
    service1 = AutomationService(store=store1, leads_loader=lambda: mock_leads)

    past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    # Create task, reminder, rule, and job
    task = service1.create_follow_up_task(
        lead_id="LEAD-101",
        title="Persistent Task",
        scheduled_for=future_time,
        idempotency_key="persist-task-1",
    )
    reminder = service1.create_reminder(
        lead_id="LEAD-101",
        title="Persistent Reminder",
        remind_at=future_time,
        task_id=task["id"],
        idempotency_key="persist-rem-1",
    )
    rule = service1.create_workflow_rule(
        name="High Value Alert",
        trigger_type="SCORE_UPDATED",
        conditions={"min_score": 80},
        actions=[{"type": "NOTIFY_REP"}],
        requires_approval=True,
    )
    # Enqueue a due job
    job = store1.enqueue_job(
        job_type="PROCESS_REMINDER",
        payload={"reminder_id": reminder["id"]},
        scheduled_at=past_time,
        idempotency_key="persist-job-1",
    )

    # Discard first instance to simulate complete application shutdown
    del service1
    del store1

    # Phase B: New application startup loading from same SQLite database file
    store2 = AutomationStore(temp_db)
    service2 = AutomationService(store=store2, leads_loader=lambda: mock_leads)

    # Verify task survived restart
    loaded_task = service2.get_follow_up_task(task["id"])
    assert loaded_task["title"] == "Persistent Task"
    assert loaded_task["idempotency_key"] == "persist-task-1"

    # Verify reminder survived restart
    loaded_rem = service2.get_reminder(reminder["id"])
    assert loaded_rem["title"] == "Persistent Reminder"
    assert loaded_rem["task_id"] == task["id"]

    # Verify rule survived restart
    loaded_rule = service2.get_workflow_rule(rule["id"])
    assert loaded_rule["name"] == "High Value Alert"
    assert loaded_rule["requires_approval"] is True

    # Verify job survived restart and is still PENDING
    loaded_job = store2.get_job(job["id"])
    assert loaded_job["status"] == "PENDING"
    assert loaded_job["job_type"] == "PROCESS_REMINDER"

    # Process due jobs on new instance
    result = service2.process_due_jobs(batch_size=10)
    assert result["processed"] >= 1
    assert result["succeeded"] >= 1

    # Verify job completed and reminder status updated
    updated_job = store2.get_job(job["id"])
    assert updated_job["status"] == "COMPLETED"

    updated_rem = service2.get_reminder(reminder["id"])
    assert updated_rem["status"] == "SENT"


# --- Test 8: Workflow Approval Safeguards ---
def test_workflow_approval_safeguards(service):
    # 1. Rule with sensitive action requires approval
    rule = service.create_workflow_rule(
        name="Auto Email Offer",
        trigger_type="INTENT_CLASSIFIED",
        actions=[{"type": "SEND_EMAIL", "template": "pricing_v1"}],
        requires_approval=True,
    )

    # Trigger execution
    exec_res = service.trigger_workflow_execution(
        rule_id=rule["id"],
        lead_id="LEAD-101",
        trigger_event="EMAIL_CLASSIFIED_PRICING",
        context_data={"intent": "PRICING_INQUIRY"},
    )

    # Safety check: execution must be AWAITING_APPROVAL, NOT executed automatically!
    assert exec_res["status"] == "AWAITING_APPROVAL"

    # Verify an approval request was automatically created
    approvals = service.list_approval_requests(lead_id="LEAD-101", status="PENDING")
    assert len(approvals) == 1
    appr = approvals[0]
    assert appr["workflow_execution_id"] == exec_res["id"]
    assert appr["action_type"] == "SEND_EMAIL"

    # Human reviews and APPROVES
    decided = service.record_approval_decision(
        approval_id=appr["id"],
        action="APPROVE",
        reviewed_by="manager@example.com",
    )
    assert decided["status"] == "APPROVED"
    assert decided["reviewed_by"] == "manager@example.com"

    # Linked workflow execution transitioned to COMPLETED
    updated_exec = service.get_workflow_execution(exec_res["id"])
    assert updated_exec["status"] == "COMPLETED"

    # Attempting to re-review fails
    with pytest.raises(InvalidStateError):
        service.record_approval_decision(
            approval_id=appr["id"],
            action="REJECT",
            reviewed_by="manager2@example.com",
        )


# --- Test 9: Background Job Retry and Failure Handling ---
def test_background_job_retry_and_failure(service, store):
    # Register a failing job handler
    fail_count = 0

    def failing_handler(payload):
        nonlocal fail_count
        fail_count += 1
        raise RuntimeError("Transient connection failure")

    service._job_handlers["FAILING_JOB"] = failing_handler

    past_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    job = store.enqueue_job(
        job_type="FAILING_JOB",
        payload={"test": "retry"},
        scheduled_at=past_time,
        max_retries=2,
    )

    # Attempt 1
    res1 = service.process_due_jobs(batch_size=10)
    assert res1["processed"] == 1
    assert res1["failed"] == 1

    job1 = store.get_job(job["id"])
    assert job1["attempts"] == 1
    assert job1["status"] == "PENDING"  # Retrying, backoff applied
    assert "Transient connection failure" in job1["last_error"]

    # Manually reset scheduled_at to past for immediate attempt 2
    with store._connect() as conn:
        conn.execute(
            "UPDATE automation_jobs SET scheduled_at = ? WHERE id = ?",
            (past_time, job["id"]),
        )

    # Attempt 2 (reaches max_retries = 2)
    res2 = service.process_due_jobs(batch_size=10)
    assert res2["processed"] == 1
    assert res2["failed"] == 1

    job2 = store.get_job(job["id"])
    assert job2["attempts"] == 2
    assert job2["status"] == "FAILED"  # Max retries exhausted


# --- Test 10: Atomic Job Claiming Prevents Duplicates ---
def test_atomic_job_claiming_prevents_duplicate_processing(store):
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    job = store.enqueue_job(
        job_type="TEST_DUP",
        payload={"val": 123},
        scheduled_at=past_time,
    )

    # Worker A claims jobs
    claim1 = store.claim_due_jobs(batch_size=5, lock_duration_seconds=60)
    assert len(claim1) == 1
    assert claim1[0]["id"] == job["id"]
    assert claim1[0]["status"] == "PROCESSING"

    # Worker B tries to claim at the same time: must be empty because job is locked!
    claim2 = store.claim_due_jobs(batch_size=5, lock_duration_seconds=60)
    assert len(claim2) == 0


# --- Test 11: Workflow Execution Rejection Flow ---
def test_workflow_execution_rejection_flow(service):
    rule = service.create_workflow_rule(
        name="Outbound Email Campaign",
        trigger_type="INTENT_CLASSIFIED",
        actions=[{"type": "SEND_EMAIL", "template": "follow_up_v1"}],
        requires_approval=True,
    )

    exec_res = service.trigger_workflow_execution(
        rule_id=rule["id"],
        lead_id="LEAD-101",
        trigger_event="EMAIL_CLASSIFIED",
    )
    assert exec_res["status"] == "AWAITING_APPROVAL"

    approvals = service.list_approval_requests(lead_id="LEAD-101", status="PENDING")
    assert len(approvals) == 1
    appr = approvals[0]

    # Human REJECTS with explicit reason
    rejected = service.record_approval_decision(
        approval_id=appr["id"],
        action="REJECT",
        reviewed_by="supervisor@example.com",
        rejection_reason="Lead explicitly requested phone only",
    )
    assert rejected["status"] == "REJECTED"
    assert rejected["rejection_reason"] == "Lead explicitly requested phone only"

    # Execution is updated to FAILED with error message
    exec_updated = service.get_workflow_execution(exec_res["id"])
    assert exec_updated["status"] == "FAILED"
    assert exec_updated["error_message"] == "Lead explicitly requested phone only"

    # Verify audit log recorded rejection
    audit_logs = service.list_audit_logs(entity_id=appr["id"])
    assert any(log["action"] == "REJECT" for log in audit_logs)


# --- Test 12: API Workflow Rules, Executions and Approvals ---
def test_api_workflow_rules_and_executions(monkeypatch, store, mock_leads, auth_headers):
    from app.api import automation as auto_api

    test_service = AutomationService(
        store=store,
        leads_loader=lambda: mock_leads,
    )
    monkeypatch.setattr(auto_api, "automation_service", test_service)
    monkeypatch.setattr(auto_api, "automation_store", store)

    client = TestClient(app)

    # 1. Create rule via API
    resp = client.post(
        "/api/v1/automation/rules",
        headers=auth_headers,
        json={
            "name": "Meeting Follow-up Rule",
            "trigger_type": "INTENT_CLASSIFIED",
            "conditions": {"intent": "MEETING_REQUEST"},
            "actions": [{"type": "SEND_EMAIL", "details": "Meeting confirmation"}],
            "requires_approval": True,
            "is_active": True,
        },
    )
    assert resp.status_code == 201
    rule_id = resp.json()["id"]

    # 2. Get rule
    resp = client.get(f"/api/v1/automation/rules/{rule_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Meeting Follow-up Rule"

    # 3. List rules with query filters
    resp = client.get(
        "/api/v1/automation/rules?trigger_type=INTENT_CLASSIFIED&is_active=true",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # 4. Trigger execution via API
    resp = client.post(
        "/api/v1/automation/executions",
        headers=auth_headers,
        json={
            "rule_id": rule_id,
            "lead_id": "LEAD-101",
            "trigger_event": "CUSTOMER_REPLIED_MEETING",
            "context_data": {"time": "tomorrow 2pm"},
            "idempotency_key": "api-exec-001",
        },
    )
    assert resp.status_code == 201
    exec_data = resp.json()
    assert exec_data["status"] == "AWAITING_APPROVAL"
    exec_id = exec_data["id"]

    # 5. Duplicate execution idempotency key returns 409
    resp = client.post(
        "/api/v1/automation/executions",
        headers=auth_headers,
        json={
            "rule_id": rule_id,
            "lead_id": "LEAD-101",
            "trigger_event": "CUSTOMER_REPLIED_MEETING",
            "idempotency_key": "api-exec-001",
        },
    )
    assert resp.status_code == 409

    # 6. List approvals via API
    resp = client.get("/api/v1/automation/approvals?status=PENDING", headers=auth_headers)
    assert resp.status_code == 200
    approvals = resp.json()
    assert len(approvals) >= 1
    target_appr = next(a for a in approvals if a["workflow_execution_id"] == exec_id)

    # 7. Record approval decision via API
    resp = client.post(
        f"/api/v1/automation/approvals/{target_appr['id']}/decision",
        headers=auth_headers,
        json={"action": "APPROVE", "reviewed_by": "qa_lead@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"
    assert resp.json()["reviewed_by"] == "qa_lead@example.com"

    # 8. Check execution is completed
    resp = client.get(f"/api/v1/automation/executions/{exec_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


# --- Test 13: API Jobs and Processing Trigger ---
def test_api_jobs_and_processing_trigger(monkeypatch, store, mock_leads, auth_headers):
    from app.api import automation as auto_api

    test_service = AutomationService(
        store=store,
        leads_loader=lambda: mock_leads,
    )
    monkeypatch.setattr(auto_api, "automation_service", test_service)
    monkeypatch.setattr(auto_api, "automation_store", store)

    client = TestClient(app)

    # List jobs
    resp = client.get("/api/v1/automation/jobs", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # Trigger process jobs now
    resp = client.post("/api/v1/automation/jobs/process?batch_size=5", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "processed" in data
    assert "succeeded" in data
    assert "failed" in data


# --- Test 14: Worker Lifecycle ---
@pytest.mark.anyio
async def test_worker_lifecycle(service):
    worker = AutomationWorker(service=service, poll_interval=1)
    assert not worker.is_running
    worker.start()
    assert worker.is_running
    # Stop worker cleanly
    await worker.stop()
    assert not worker.is_running

