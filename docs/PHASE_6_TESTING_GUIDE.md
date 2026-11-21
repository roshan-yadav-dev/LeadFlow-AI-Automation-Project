# Phase 6: Testing & Verification Guide

This guide outlines how to execute the automated test suite and manually verify the Phase 6 Lead Automation capabilities.

---

## 1. Automated Test Suite Execution

LeadFlow AI maintains a complete automated test suite verifying all Phase 1–5 legacy capabilities alongside Phase 6.1–6.7 automation features.

### Run All Tests
```bash
./venv/bin/pytest -v
```
Expected output:
```
============================= 86 passed in ~10s ==============================
```

### Run Phase 6 Automation Tests Only
```bash
./venv/bin/pytest -v tests/test_automation.py tests/test_automation_phase6.py
```
Expected output:
```
============================= 32 passed in ~4s ==============================
```

### Test Suite Structure

| Test File | Focus Area | Covered Cases |
|---|---|---|
| `tests/test_automation.py` | Phase 6.1 Foundation | Database initialization, WAL mode, foreign keys, idempotency collision, basic model validation, single worker lifecycle, atomic claiming. |
| `tests/test_automation_phase6.py` | Phase 6.2–6.7 Engine | Deterministic 6-factor points, HOT/WARM/COLD tiers, complaint attention flag, out-of-office neutrality, ISO-8601 validation (HTTP 422), upcoming/overdue tasks, reminder dismissal, workflow rule CRUD, approval lifecycle, persistent job handlers, full end-to-end integration. |
| `tests/test_gmail_inbox.py` | Phase 4 Gmail Sync | Base64URL parsing, HTML entity sanitization, MIME multi-part handling, sync checkpoints. |
| `tests/test_gmail_intelligence.py` | Phase 5 Intelligence | Inbound message matching, Groq AI intent classification, atomic message claims, strict JSON schema validation. |
| `tests/test_lead_service.py` | Phases 1–3 Lead Flow | Lead registration, Google Sheets CRM save, consent checks, auto email sending. |

---

## 2. Manual Verification Walkthrough (cURL / HTTP)

### Step 1: Start the Server
```bash
./venv/bin/uvicorn app.main:app --port 8001
```

### Step 2: Check Automation Health
```bash
curl -X GET http://localhost:8001/api/v1/automation/health
```
Expected Response:
```json
{"status":"healthy","database":"connected","worker_running":true,...}
```

### Step 3: Trigger Batch Score Recalculation
```bash
curl -X POST http://localhost:8001/api/v1/automation/scores/recalculate \
  -H "X-Webhook-Secret: <your_secret>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Step 4: Inspect Leaderboard
```bash
curl -X GET "http://localhost:8001/api/v1/automation/scores/leaderboard?limit=10" \
  -H "X-Webhook-Secret: <your_secret>"
```

### Step 5: Schedule a Follow-Up Task
```bash
curl -X POST http://localhost:8001/api/v1/automation/tasks \
  -H "X-Webhook-Secret: <your_secret>" \
  -H "Content-Type: application/json" \
  -d '{
    "lead_id": "LEAD-001",
    "title": "Discovery Call",
    "scheduled_for": "2026-11-25T14:30:00",
    "timezone": "Asia/Kolkata",
    "priority": "HIGH",
    "channel": "CALL"
  }'
```

### Step 6: Verify Invalid Date Rejection (HTTP 422)
```bash
curl -X POST http://localhost:8001/api/v1/automation/tasks \
  -H "X-Webhook-Secret: <your_secret>" \
  -H "Content-Type: application/json" \
  -d '{
    "lead_id": "LEAD-001",
    "title": "Invalid Call",
    "scheduled_for": "Tomorrow"
  }'
```
Expected Response: `HTTP 422 Unprocessable Entity` with a clear message indicating invalid ISO-8601 format.

### Step 7: Check Pending Approvals
```bash
curl -X GET http://localhost:8001/api/v1/automation/approvals/pending \
  -H "X-Webhook-Secret: <your_secret>"
```

### Step 8: Approve or Reject a Sensitive Action
```bash
curl -X POST http://localhost:8001/api/v1/automation/approvals/<approval_id>/decision \
  -H "X-Webhook-Secret: <your_secret>" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "APPROVE",
    "reviewed_by": "sales_lead@company.com",
    "decision_notes": "Proposal reviewed and cleared."
  }'
```
