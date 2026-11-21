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
    FollowUpTaskCreate,
    FollowUpTaskReschedule,
    LeadScoreCreate,
    ReminderCreate,
    WorkflowRuleCreate,
    to_kolkata_iso,
    to_utc_iso,
    utc_now_iso,
)
from app.services.automation_service import (
    AutomationService,
    InvalidLeadIdError,
    InvalidStateError,
)
from app.services.automation_store import AutomationStore, DuplicateIdempotencyKeyError
from app.services.lead_scoring_service import (
    DeterministicLeadScorer,
    LeadScoringEngine,
    compute_lead_score,
)


# --- Shared Fixtures ---

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
def intel_db():
    fd, path = tempfile.mkstemp(suffix="_intel.sqlite3")
    os.close(fd)
    # Initialize the schema
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE gmail_message_intelligence (
            message_id TEXT PRIMARY KEY,
            lead_id TEXT,
            match_status TEXT DEFAULT 'MATCHED',
            classification_status TEXT DEFAULT 'SUCCESS',
            intent_category TEXT,
            sentiment TEXT,
            confidence REAL,
            summary TEXT,
            extracted_information TEXT NOT NULL DEFAULT '{}',
            action_items TEXT NOT NULL DEFAULT '[]',
            suggested_next_step TEXT,
            received_timestamp TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def store(temp_db):
    return AutomationStore(temp_db)


@pytest.fixture
def mock_crm_leads():
    return [
        {
            "lead_id": "LEAD-201",
            "name": "David Miller",
            "email": "david@acme.com",
            "company": "Acme Corp",
            "service": "AI Integration",
            "budget": "$15,000",
            "consent": True,
        },
        {
            "lead_id": "LEAD-202",
            "name": "Sarah Connor",
            "email": "sarah@cyberdyne.com",
            "company": "Cyberdyne Systems",
            "service": "Automation",
            "budget": "None",
            "consent": True,
        },
    ]


@pytest.fixture
def mock_intel_store(intel_db):
    class FakeIntelligenceStore:
        def __init__(self, db_path):
            self.db_path = db_path

        def _connect(self):
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

        def add_analysis(
            self,
            message_id: str,
            lead_id: str,
            intent_category: str = "INTERESTED",
            sentiment: str = "POSITIVE",
            confidence: float = 0.95,
            extracted_budget: str = "$15,000",
            received_timestamp: str | None = None,
        ):
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO gmail_message_intelligence
                    (message_id, lead_id, match_status, classification_status,
                     intent_category, sentiment, confidence, summary,
                     extracted_information, action_items, suggested_next_step,
                     received_timestamp, created_at)
                    VALUES (?, ?, 'MATCHED', 'SUCCESS', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        lead_id,
                        intent_category,
                        sentiment,
                        confidence,
                        "Inbound discussion regarding AI integration",
                        json.dumps({"mentioned_budget": extracted_budget, "mentioned_timeline": "asap"}),
                        json.dumps(["Schedule demo call"]),
                        "Schedule product demonstration",
                        received_timestamp or utc_now_iso(),
                        utc_now_iso(),
                    ),
                )
                conn.commit()

    return FakeIntelligenceStore(intel_db)


@pytest.fixture
def service(store, mock_crm_leads, mock_intel_store):
    return AutomationService(
        store=store,
        leads_loader=lambda: mock_crm_leads,
        intelligence_store=mock_intel_store,
    )


# ==============================================================================
# 1. PHASE 6.2 — DETERMINISTIC LEAD SCORING TESTS
# ==============================================================================

def test_lead_scoring_factor_points_and_max_boundary():
    """Verify maximum points for all 6 factors and 100 pt total cap."""
    engine = DeterministicLeadScorer()
    crm_lead = {
        "lead_id": "LEAD-201",
        "name": "David",
        "company": "Acme",
        "budget": "$50,000",
        "service": "Enterprise AI",
    }
    intel_history = [
        {
            "message_id": "msg-001",
            "intent_category": "MEETING_REQUEST",  # Intent: 30 pts
            "sentiment": "POSITIVE",               # Sentiment: 20 pts
            "extracted_information": json.dumps({"mentioned_budget": "$50,000", "mentioned_timeline": "asap"}),
            "received_timestamp": utc_now_iso(),   # Recency: 10 pts
            "classification_status": "SUCCESS",
        },
        {
            "message_id": "msg-002",
            "intent_category": "INTERESTED",
            "sentiment": "POSITIVE",
            "received_timestamp": utc_now_iso(),
            "classification_status": "SUCCESS",
        },
        {
            "message_id": "msg-003",
            "intent_category": "NEGOTIATION",
            "sentiment": "POSITIVE",
            "received_timestamp": utc_now_iso(),
            "classification_status": "SUCCESS",
        },
    ]

    calc = engine.calculate_score("LEAD-201", crm_lead, intel_history)
    assert calc["score"] <= 100
    assert calc["tier"] == "HOT"
    assert calc["version"] == "v2-deterministic"

    factors = calc["factors"]
    assert factors["customer_intent"]["score"] <= 30
    assert factors["sentiment"]["score"] <= 20
    assert factors["engagement"]["score"] <= 15
    assert factors["budget"]["score"] <= 15
    assert factors["follow_up_urgency"]["score"] <= 10
    assert factors["recency"]["score"] <= 10


def test_lead_scoring_tier_thresholds():
    """HOT: 75-100, WARM: 40-74, COLD: 0-39."""
    engine = DeterministicLeadScorer()

    # Cold lead (no budget, NOT_INTERESTED or neutral inquiry long ago)
    past_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    cold_calc = engine.calculate_score(
        lead_id="L1",
        crm_lead={"lead_id": "L1", "budget": "None"},
        intelligence_records=[{
            "message_id": "m1",
            "intent_category": "NOT_INTERESTED",
            "sentiment": "NEGATIVE",
            "received_timestamp": past_date,
            "classification_status": "SUCCESS",
        }],
    )
    assert cold_calc["score"] < 40
    assert cold_calc["tier"] == "COLD"

    # Warm lead
    warm_calc = engine.calculate_score(
        lead_id="L2",
        crm_lead={"lead_id": "L2", "budget": "$2,000"},
        intelligence_records=[{
            "message_id": "m2",
            "intent_category": "INFORMATION_REQUEST",
            "sentiment": "NEUTRAL",
            "received_timestamp": utc_now_iso(),
            "classification_status": "SUCCESS",
        }],
    )
    assert 40 <= warm_calc["score"] <= 74
    assert warm_calc["tier"] == "WARM"

    # Hot lead
    now_ts = utc_now_iso()
    past_10m = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    hot_calc = engine.calculate_score(
        lead_id="L3",
        crm_lead={"lead_id": "L3", "budget": "$20,000"},
        intelligence_records=[
            {
                "message_id": "m3",
                "intent_category": "MEETING_REQUEST",
                "sentiment": "POSITIVE",
                "received_timestamp": now_ts,
                "classification_status": "SUCCESS",
            },
            {
                "message_id": "m4",
                "intent_category": "INTERESTED",
                "sentiment": "POSITIVE",
                "received_timestamp": past_10m,
                "classification_status": "SUCCESS",
            },
        ],
    )
    assert hot_calc["score"] >= 75
    assert hot_calc["tier"] == "HOT"


def test_lead_scoring_complaint_attention_flag_not_forcing_cold():
    """A complaint must set attention flag without automatically classifying as COLD."""
    engine = DeterministicLeadScorer()
    crm_lead = {"lead_id": "L-COMPLAINT", "budget": "$30,000"}
    intel_history = [{
        "message_id": "m-comp",
        "intent_category": "COMPLAINT",
        "sentiment": "NEGATIVE",
        "received_timestamp": utc_now_iso(),
        "classification_status": "SUCCESS",
    }]

    calc = engine.calculate_score("L-COMPLAINT", crm_lead, intel_history)
    assert calc["factors"]["complaint_attention_flag"] is True
    # Has budget points + recency points + complaint intent points, so not 0
    assert calc["score"] >= 20


def test_lead_scoring_out_of_office_is_neutral():
    """Out-of-office messages must not be penalized as disinterest."""
    engine = DeterministicLeadScorer()
    crm_lead = {"lead_id": "L-OOO", "budget": "$10,000"}
    intel_history = [{
        "message_id": "m-ooo",
        "intent_category": "OUT_OF_OFFICE",
        "sentiment": "NEUTRAL",
        "received_timestamp": utc_now_iso(),
        "classification_status": "SUCCESS",
    }]

    calc = engine.calculate_score("L-OOO", crm_lead, intel_history)
    assert calc["factors"]["customer_intent"]["score"] >= 0
    assert calc["tier"] in ("WARM", "COLD")


def test_lead_scoring_missing_info_does_not_produce_negative_scores():
    """Missing fields should produce 0 points for that factor, not negative scores."""
    engine = DeterministicLeadScorer()
    calc = engine.calculate_score("EMPTY", crm_lead={}, intelligence_records=[])
    assert calc["score"] >= 0
    assert calc["tier"] == "COLD"
    assert calc["factors"]["customer_intent"]["score"] == 0
    assert calc["factors"]["sentiment"]["score"] == 0
    assert calc["factors"]["budget"]["score"] == 0


def test_lead_scoring_deduplication_of_same_gmail_message():
    """Avoid double-counting identical message IDs."""
    engine = DeterministicLeadScorer()
    crm_lead = {"lead_id": "L-DUP"}
    dup_msg = {
        "message_id": "msg-duplicate-1",
        "intent_category": "INTERESTED",
        "sentiment": "POSITIVE",
        "received_timestamp": utc_now_iso(),
        "classification_status": "SUCCESS",
    }
    calc = engine.calculate_score("L-DUP", crm_lead, [dup_msg, dup_msg])
    assert calc["factors"]["engagement"]["distinct_messages"] == 1


def test_lead_scoring_service_and_api(monkeypatch, store, mock_crm_leads, mock_intel_store, auth_headers):
    """Test calculate, recalculate, leaderboard, and history endpoints."""
    from app.api import automation as auto_api

    test_service = AutomationService(
        store=store,
        leads_loader=lambda: mock_crm_leads,
        intelligence_store=mock_intel_store,
    )
    monkeypatch.setattr(auto_api, "automation_service", test_service)
    monkeypatch.setattr(auto_api, "automation_store", store)

    client = TestClient(app)

    # Add intel for LEAD-201
    mock_intel_store.add_analysis(
        message_id="msg-201",
        lead_id="LEAD-201",
        intent_category="MEETING_REQUEST",
        sentiment="POSITIVE",
    )

    # 1. POST /scores/calculate/{lead_id}
    resp = client.post("/api/v1/automation/scores/calculate/LEAD-201", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["lead_id"] == "LEAD-201"
    assert data["score"] >= 50
    assert data["tier"] in ("HOT", "WARM")

    # 2. GET /scores/{lead_id}
    resp = client.get("/api/v1/automation/scores/LEAD-201", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["score"] == data["score"]

    # 3. GET /scores/{lead_id}/history
    resp = client.get("/api/v1/automation/scores/LEAD-201/history", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # 4. POST /scores/recalculate (batch recalculation)
    resp = client.post("/api/v1/automation/scores/recalculate", headers=auth_headers, json={})
    assert resp.status_code == 200
    recalc_data = resp.json()
    assert recalc_data["recalculated"] >= 1

    # 5. GET /scores/leaderboard
    resp = client.get("/api/v1/automation/scores/leaderboard", headers=auth_headers)
    assert resp.status_code == 200
    board = resp.json()
    assert len(board) >= 1
    assert board[0]["lead_id"] == "LEAD-201"


# ==============================================================================
# 2. PHASE 6.3 — FOLLOW-UP SCHEDULING TESTS
# ==============================================================================

def test_follow_up_invalid_date_returns_422(monkeypatch, store, mock_crm_leads, auth_headers):
    """Ensure invalid date strings like 'Tomorrow' return HTTP 422, never 500."""
    from app.api import automation as auto_api

    test_service = AutomationService(store=store, leads_loader=lambda: mock_crm_leads)
    monkeypatch.setattr(auto_api, "automation_service", test_service)
    monkeypatch.setattr(auto_api, "automation_store", store)

    client = TestClient(app)

    # Test "Tomorrow"
    resp = client.post(
        "/api/v1/automation/tasks",
        headers=auth_headers,
        json={"lead_id": "LEAD-201", "title": "Call", "scheduled_for": "Tomorrow"},
    )
    assert resp.status_code == 422

    # Test "10:10"
    resp = client.post(
        "/api/v1/automation/tasks",
        headers=auth_headers,
        json={"lead_id": "LEAD-201", "title": "Call", "scheduled_for": "10:10"},
    )
    assert resp.status_code == 422

    # Test invalid timezone
    resp = client.post(
        "/api/v1/automation/tasks",
        headers=auth_headers,
        json={
            "lead_id": "LEAD-201",
            "title": "Call",
            "scheduled_for": "2026-11-25T10:00:00",
            "timezone": "Invalid/Timezone_Name",
        },
    )
    assert resp.status_code == 422


def test_follow_up_timezone_naive_and_aware_handling(service):
    """Test naive datetimes are interpreted as Asia/Kolkata, stored in UTC, and localized in local field."""
    # 1. Timezone naive string: "2026-11-25T15:30:00" in Asia/Kolkata (+05:30) -> 10:00:00 UTC
    task = service.create_follow_up_task(
        lead_id="LEAD-201",
        title="Naive datetime task",
        scheduled_for="2026-11-25T15:30:00",
        timezone_str="Asia/Kolkata",
    )
    assert "10:00:00" in task["scheduled_for"]
    assert "+00:00" in task["scheduled_for"] or task["scheduled_for"].endswith("Z")
    assert "+05:30" in task["scheduled_for_local"]
    assert "15:30:00" in task["scheduled_for_local"]

    # 2. Timezone aware UTC string: "2026-11-25T10:00:00Z" -> 15:30:00 IST
    task_aware = service.create_follow_up_task(
        lead_id="LEAD-201",
        title="Aware datetime task",
        scheduled_for="2026-11-25T10:00:00Z",
    )
    assert "10:00:00" in task_aware["scheduled_for"]
    assert "15:30:00" in task_aware["scheduled_for_local"]


def test_follow_up_upcoming_and_overdue_endpoints(monkeypatch, store, mock_crm_leads, auth_headers):
    """Test filtering upcoming vs overdue tasks."""
    from app.api import automation as auto_api

    test_service = AutomationService(store=store, leads_loader=lambda: mock_crm_leads)
    monkeypatch.setattr(auto_api, "automation_service", test_service)
    monkeypatch.setattr(auto_api, "automation_store", store)

    client = TestClient(app)

    past_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    future_time = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

    # Create an overdue task
    resp_overdue = client.post(
        "/api/v1/automation/tasks",
        headers=auth_headers,
        json={"lead_id": "LEAD-201", "title": "Overdue task", "scheduled_for": past_time},
    )
    assert resp_overdue.status_code == 201

    # Create an upcoming task
    resp_upcoming = client.post(
        "/api/v1/automation/tasks",
        headers=auth_headers,
        json={"lead_id": "LEAD-201", "title": "Upcoming task", "scheduled_for": future_time},
    )
    assert resp_upcoming.status_code == 201

    # Query upcoming
    res_up = client.get("/api/v1/automation/tasks/upcoming", headers=auth_headers)
    assert res_up.status_code == 200
    up_titles = [t["title"] for t in res_up.json()]
    assert "Upcoming task" in up_titles
    assert "Overdue task" not in up_titles

    # Query overdue
    res_ov = client.get("/api/v1/automation/tasks/overdue", headers=auth_headers)
    assert res_ov.status_code == 200
    ov_titles = [t["title"] for t in res_ov.json()]
    assert "Overdue task" in ov_titles
    assert "Upcoming task" not in ov_titles


def test_follow_up_reschedule_complete_cancel_endpoints(monkeypatch, store, mock_crm_leads, auth_headers):
    """Test task lifecycle transitions: reschedule, complete, cancel."""
    from app.api import automation as auto_api

    test_service = AutomationService(store=store, leads_loader=lambda: mock_crm_leads)
    monkeypatch.setattr(auto_api, "automation_service", test_service)
    monkeypatch.setattr(auto_api, "automation_store", store)

    client = TestClient(app)

    due_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    resp = client.post(
        "/api/v1/automation/tasks",
        headers=auth_headers,
        json={"lead_id": "LEAD-201", "title": "Task to manage", "scheduled_for": due_time},
    )
    task_id = resp.json()["id"]

    # 1. Reschedule
    new_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    resp_resched = client.post(
        f"/api/v1/automation/tasks/{task_id}/reschedule",
        headers=auth_headers,
        json={"scheduled_for": new_time},
    )
    assert resp_resched.status_code == 200
    assert resp_resched.json()["status"] == "SCHEDULED"

    # 2. Complete
    resp_comp = client.post(f"/api/v1/automation/tasks/{task_id}/complete", headers=auth_headers)
    assert resp_comp.status_code == 200
    assert resp_comp.json()["status"] == "COMPLETED"

    # 3. Cancel another task
    resp2 = client.post(
        "/api/v1/automation/tasks",
        headers=auth_headers,
        json={"lead_id": "LEAD-201", "title": "Task to cancel", "scheduled_for": due_time},
    )
    task2_id = resp2.json()["id"]
    resp_canc = client.post(f"/api/v1/automation/tasks/{task2_id}/cancel", headers=auth_headers)
    assert resp_canc.status_code == 200
    assert resp_canc.json()["status"] == "CANCELLED"


# ==============================================================================
# 3. PHASE 6.4 — AUTOMATED REMINDERS TESTS
# ==============================================================================

def test_reminders_dismiss_and_pending_endpoint(monkeypatch, store, mock_crm_leads, auth_headers):
    """Test listing pending reminders and dismissing them."""
    from app.api import automation as auto_api

    test_service = AutomationService(store=store, leads_loader=lambda: mock_crm_leads)
    monkeypatch.setattr(auto_api, "automation_service", test_service)
    monkeypatch.setattr(auto_api, "automation_store", store)

    client = TestClient(app)

    rem_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    resp = client.post(
        "/api/v1/automation/reminders",
        headers=auth_headers,
        json={"lead_id": "LEAD-201", "title": "Check RFP", "remind_at": rem_time},
    )
    assert resp.status_code == 201
    reminder_id = resp.json()["id"]

    # List pending
    resp_pend = client.get("/api/v1/automation/reminders/pending", headers=auth_headers)
    assert resp_pend.status_code == 200
    assert any(r["id"] == reminder_id for r in resp_pend.json())

    # Dismiss reminder
    resp_diss = client.post(f"/api/v1/automation/reminders/{reminder_id}/dismiss", headers=auth_headers)
    assert resp_diss.status_code == 200
    assert resp_diss.json()["status"] == "DISMISSED"

    # Verify no longer in pending list
    resp_pend2 = client.get("/api/v1/automation/reminders/pending", headers=auth_headers)
    assert not any(r["id"] == reminder_id for r in resp_pend2.json())


def test_reminders_prevent_duplicate_processing_when_completed(service, store):
    """Completed or dismissed reminders must not be processed again by the worker."""
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    rem = service.create_reminder(
        lead_id="LEAD-201",
        title="Test Reminder",
        remind_at=past_time,
    )
    # Manually dismiss
    service.dismiss_reminder(rem["id"])

    # Enqueue a job pointing to the dismissed reminder
    job = store.enqueue_job(
        job_type="PROCESS_REMINDER",
        payload={"reminder_id": rem["id"]},
        scheduled_at=past_time,
    )

    # Process due jobs
    res = service.process_due_jobs()
    assert res["processed"] >= 1
    # Check that job completed without error, but reminder was skipped
    updated_job = store.get_job(job["id"])
    assert updated_job["status"] == "COMPLETED"
    updated_rem = service.get_reminder(rem["id"])
    assert updated_rem["status"] == "DISMISSED"


# ==============================================================================
# 4. PHASE 6.5 — CONDITIONAL WORKFLOW ENGINE TESTS
# ==============================================================================

def test_workflow_rule_crud_and_manual_trigger(monkeypatch, store, mock_crm_leads, auth_headers):
    """Test creating, updating, deleting, and manually triggering workflow rules."""
    from app.api import automation as auto_api

    test_service = AutomationService(store=store, leads_loader=lambda: mock_crm_leads)
    monkeypatch.setattr(auto_api, "automation_service", test_service)
    monkeypatch.setattr(auto_api, "automation_store", store)

    client = TestClient(app)

    # 1. Create rule
    resp = client.post(
        "/api/v1/automation/rules",
        headers=auth_headers,
        json={
            "name": "Hot Lead Alert",
            "trigger_type": "SCORE_UPDATED",
            "conditions": {"min_score": 80},
            "actions": [{"type": "CREATE_INTERNAL_NOTIFICATION", "params": {"message": "High value lead!"}}],
            "requires_approval": False,
            "is_active": True,
        },
    )
    assert resp.status_code == 201
    rule_id = resp.json()["id"]

    # 2. Update rule
    resp_patch = client.patch(
        f"/api/v1/automation/rules/{rule_id}",
        headers=auth_headers,
        json={"is_active": False},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["is_active"] is False

    # Reactivate
    client.patch(
        f"/api/v1/automation/rules/{rule_id}",
        headers=auth_headers,
        json={"is_active": True},
    )

    # 3. Manually trigger rule
    resp_trig = client.post(
        f"/api/v1/automation/rules/{rule_id}/trigger",
        headers=auth_headers,
        json={"lead_id": "LEAD-201", "context_data": {"score": 85}},
    )
    assert resp_trig.status_code == 200
    assert resp_trig.json()["rule_id"] == rule_id

    # 4. Delete rule
    resp_del = client.delete(f"/api/v1/automation/rules/{rule_id}", headers=auth_headers)
    assert resp_del.status_code == 200
    assert resp_del.json()["deleted"] is True


def test_workflow_conditions_matching(service):
    """Verify various rule conditions (score, sentiment, complaint, crm)."""
    rule = {
        "conditions": {
            "min_score": 50,
            "sentiment": ["POSITIVE", "NEUTRAL"],
            "complaint_attention_flag": False,
            "crm_has_budget": True,
        }
    }

    # Record matching score for LEAD-201 (budget $15,000)
    service.record_lead_score(lead_id="LEAD-201", score=70, tier="WARM")

    # Positive match
    assert service.evaluate_rule_conditions(
        rule=rule,
        lead_id="LEAD-201",
        context_data={"sentiment": "POSITIVE"},
    ) is True

    # Negative match: sentiment negative
    assert service.evaluate_rule_conditions(
        rule=rule,
        lead_id="LEAD-201",
        context_data={"sentiment": "NEGATIVE"},
    ) is False


# ==============================================================================
# 5. PHASE 6.6 — HUMAN APPROVAL SYSTEM TESTS
# ==============================================================================

def test_human_approval_lifecycle_and_expiry(service, store):
    """Test approval pending list, decision, and expiry of stale requests."""
    # Create rule requiring approval with sensitive action SEND_EMAIL
    rule = service.create_workflow_rule(
        name="Outbound Email Rule",
        trigger_type="INTENT_CLASSIFIED",
        actions=[{"type": "SEND_EMAIL", "template": "offer"}],
        requires_approval=True,
    )

    # Trigger execution
    exec_res = service.trigger_workflow_execution(
        rule_id=rule["id"],
        lead_id="LEAD-201",
        trigger_event="EMAIL_CLASSIFIED",
    )
    assert exec_res["status"] == "AWAITING_APPROVAL"

    # Pending approvals query
    pending = service.list_approval_requests(status="PENDING")
    assert len(pending) >= 1
    appr = next(a for a in pending if a["workflow_execution_id"] == exec_res["id"])

    # Simulate expiring stale approval
    past_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with store._connect() as conn:
        conn.execute(
            "UPDATE approval_requests SET expires_at = ? WHERE id = ?",
            (past_iso, appr["id"]),
        )

    # Run expiry check
    expired_list = service.expire_stale_approvals()
    assert len(expired_list) >= 1

    # Check approval status
    updated_appr = service.get_approval_request(appr["id"])
    assert updated_appr["status"] == "EXPIRED"


# ==============================================================================
# 6. PHASE 6.7 — PERSISTENT BACKGROUND WORKER & JOB HANDLERS TESTS
# ==============================================================================

def test_persistent_job_handlers_execution(service, store):
    """Test execution of RECALCULATE_LEAD_SCORE and PROCESS_APPROVAL_EXPIRY jobs."""
    # 1. Enqueue RECALCULATE_LEAD_SCORE job
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    job1 = store.enqueue_job(
        job_type="RECALCULATE_LEAD_SCORE",
        payload={"lead_id": "LEAD-201"},
        scheduled_at=past_time,
    )

    # 2. Enqueue PROCESS_APPROVAL_EXPIRY job
    job2 = store.enqueue_job(
        job_type="PROCESS_APPROVAL_EXPIRY",
        payload={},
        scheduled_at=past_time,
    )

    res = service.process_due_jobs(batch_size=10)
    assert res["processed"] >= 2
    assert res["succeeded"] >= 2

    assert store.get_job(job1["id"])["status"] == "COMPLETED"
    assert store.get_job(job2["id"])["status"] == "COMPLETED"


# ==============================================================================
# 7. END-TO-END INTEGRATION TEST: CRM + INTEL + AUTOMATION + APPROVAL
# ==============================================================================

def test_end_to_end_automation_integration(service, store, mock_crm_leads, mock_intel_store):
    """
    End-to-End Workflow:
    1. LEAD_CREATED event -> evaluates rules -> creates follow-up task.
    2. INTENT_CLASSIFIED event -> auto recalculates lead score to HOT -> evaluates rule.
    3. Workflow triggers sensitive SEND_EMAIL action -> requires human approval.
    4. Reviewer approves -> execution completes.
    5. Background worker processes due reminders and jobs.
    6. Verify audit logs and persistence.
    """
    # Step A: Setup automated rules
    # Rule 1: On LEAD_CREATED, schedule a follow-up task
    rule_created = service.create_workflow_rule(
        name="Welcome Follow-up",
        trigger_type="LEAD_CREATED",
        actions=[{
            "type": "CREATE_FOLLOW_UP",
            "params": {"title": "Initial intro call", "delay_hours": 24, "priority": "HIGH"},
        }],
        requires_approval=False,
    )

    # Rule 2: On SCORE_UPDATED for HOT leads, prepare email offer requiring approval
    rule_hot = service.create_workflow_rule(
        name="Hot Lead Outreach",
        trigger_type="SCORE_UPDATED",
        conditions={"min_score": 60, "tier": ["HOT", "WARM"]},
        actions=[{"type": "SEND_EMAIL", "params": {"template": "executive_intro"}}],
        requires_approval=True,
    )

    # Step B: Emit LEAD_CREATED
    execs1 = service.emit_event(
        trigger_type="LEAD_CREATED",
        lead_id="LEAD-201",
        context_data={"name": "David Miller", "service": "AI Integration"},
    )
    assert len(execs1) >= 1
    assert execs1[0]["status"] == "COMPLETED"

    # Verify follow-up task was automatically created
    tasks = service.list_follow_up_tasks(lead_id="LEAD-201")
    assert any("Initial intro call" in t["title"] for t in tasks)

    # Step C: Customer replies with meeting request -> INTENT_CLASSIFIED
    mock_intel_store.add_analysis(
        message_id="msg-e2e-1",
        lead_id="LEAD-201",
        intent_category="MEETING_REQUEST",
        sentiment="POSITIVE",
        confidence=0.95,
        extracted_budget="$25,000",
    )

    # Emit INTENT_CLASSIFIED event (this also triggers score recalculation and SCORE_UPDATED event)
    service.emit_event(
        trigger_type="INTENT_CLASSIFIED",
        lead_id="LEAD-201",
        context_data={"message_id": "msg-e2e-1", "intent_category": "MEETING_REQUEST", "sentiment": "POSITIVE"},
    )

    # Verify score recalculated
    latest_score = store.get_latest_lead_score("LEAD-201")
    assert latest_score is not None
    assert latest_score["score"] >= 50

    # Step D: Emit SCORE_UPDATED -> triggers Hot Lead Outreach rule
    execs_score = service.emit_event(
        trigger_type="SCORE_UPDATED",
        lead_id="LEAD-201",
        context_data={"score": latest_score["score"], "tier": latest_score["tier"]},
    )
    assert len(execs_score) >= 1
    hot_exec = next(e for e in execs_score if e["rule_id"] == rule_hot["id"])
    assert hot_exec["status"] == "AWAITING_APPROVAL"

    # Step E: Human reviews and approves request
    pending = service.list_approval_requests(lead_id="LEAD-201", status="PENDING")
    assert len(pending) >= 1
    appr_target = next(a for a in pending if a["workflow_execution_id"] == hot_exec["id"])

    decision = service.record_approval_decision(
        approval_id=appr_target["id"],
        action="APPROVE",
        reviewed_by="sales_director@leadflow.ai",
        decision_notes="Lead confirmed budget in meeting request.",
    )
    assert decision["status"] == "APPROVED"

    # Execution transitioned to COMPLETED
    updated_exec = service.get_workflow_execution(hot_exec["id"])
    assert updated_exec["status"] == "COMPLETED"

    # Step F: Verify audit trail
    logs = service.list_audit_logs(lead_id="LEAD-201")
    entity_types = {l["entity_type"] for l in logs}
    assert "FOLLOW_UP_TASK" in entity_types
    assert "LEAD_SCORE" in entity_types
    assert "WORKFLOW_EXECUTION" in entity_types
    assert "APPROVAL_REQUEST" in entity_types

    # Step G: Process jobs
    job_res = service.process_due_jobs()
    assert job_res["failed"] == 0
