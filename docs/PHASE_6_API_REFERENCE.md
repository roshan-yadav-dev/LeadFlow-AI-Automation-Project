# Phase 6: Automation API Reference

All automation endpoints are mounted under `/api/v1/automation`.
Protected endpoints require the `X-Webhook-Secret` HTTP header matching `settings.WEBHOOK_SECRET`.

---

## 1. System Status & Health

### `GET /api/v1/automation/health`
Unauthenticated health probe for monitoring.
- **Response `200 OK`**:
```json
{
  "status": "healthy",
  "database": "connected",
  "worker_running": true,
  "timestamp": "2026-11-20T10:50:00Z"
}
```

### `GET /api/v1/automation/status`
Protected detailed status including entity counts.
- **Headers**: `X-Webhook-Secret: <secret>`
- **Response `200 OK`**:
```json
{
  "status": "active",
  "default_timezone": "Asia/Kolkata",
  "worker_running": true,
  "counts": {
    "lead_scores": 12,
    "follow_up_tasks": 5,
    "reminders": 3,
    "workflow_rules": 4,
    "pending_approvals": 1,
    "pending_jobs": 0
  }
}
```

---

## 2. Lead Scoring Endpoints

### `POST /api/v1/automation/scores/calculate/{lead_id}`
Calculate and persist the deterministic score for a lead based on CRM and intelligence records.
- **Headers**: `X-Webhook-Secret: <secret>`
- **Response `200 OK`**:
```json
{
  "id": "score_7f8a9b1c2d3e",
  "lead_id": "LEAD-101",
  "score": 85,
  "tier": "HOT",
  "factors": {
    "customer_intent": {
      "score": 30,
      "max": 30,
      "category": "MEETING_REQUEST",
      "explanation": "Customer requested a meeting (highest conversion signal)."
    },
    "sentiment": {
      "score": 20,
      "max": 20,
      "sentiment": "POSITIVE",
      "explanation": "Positive customer sentiment detected."
    },
    "engagement": {
      "score": 10,
      "max": 15,
      "message_count": 2,
      "explanation": "Moderate engagement with 2 distinct inbound messages."
    },
    "budget": {
      "score": 15,
      "max": 15,
      "crm_budget": "$25,000",
      "explanation": "Budget indicated in CRM ($25,000)."
    },
    "follow_up_urgency": {
      "score": 0,
      "max": 10,
      "explanation": "No urgent follow-up required."
    },
    "recency": {
      "score": 10,
      "max": 10,
      "explanation": "Interaction within the last 24 hours."
    },
    "complaint_attention_flag": false
  },
  "version": "v2-deterministic",
  "idempotency_key": null,
  "created_at": "2026-11-20T10:50:00Z",
  "updated_at": "2026-11-20T10:50:00Z"
}
```

### `POST /api/v1/automation/scores/recalculate`
Batch recalculate scores for all CRM leads or a specific subset.
- **Payload (Optional)**:
```json
{
  "lead_ids": ["LEAD-101", "LEAD-102"]
}
```
- **Response `200 OK`**:
```json
{
  "recalculated": 2,
  "lead_ids": ["LEAD-101", "LEAD-102"],
  "results": [...]
}
```

### `GET /api/v1/automation/scores/leaderboard`
Retrieve ranked list of leads ordered by score descending.
- **Query params**: `limit=50&tier=HOT`
- **Response `200 OK`**:
```json
[
  {
    "lead_id": "LEAD-101",
    "name": "Alice Smith",
    "email": "alice@example.com",
    "company": "Acme Inc",
    "score": 85,
    "tier": "HOT",
    "complaint_attention_flag": false,
    "factors_summary": {
      "intent": 30,
      "sentiment": 20,
      "engagement": 10,
      "budget": 15,
      "urgency": 0,
      "recency": 10
    },
    "calculated_at": "2026-11-20T10:50:00Z"
  }
]
```

### `GET /api/v1/automation/scores/{lead_id}`
Retrieve latest score for a lead.

### `GET /api/v1/automation/scores/{lead_id}/history`
Retrieve historical scores for a lead ordered chronologically.

---

## 3. Follow-Up Task Management

### `POST /api/v1/automation/tasks`
Schedule a new follow-up task.
- **Payload**:
```json
{
  "lead_id": "LEAD-101",
  "title": "Discovery Call with Alice",
  "description": "Discuss enterprise pricing and security questions",
  "scheduled_for": "2026-11-22T14:30:00",
  "timezone": "Asia/Kolkata",
  "priority": "HIGH",
  "channel": "CALL",
  "generate_reminder": true,
  "reminder_minutes_before": 30,
  "idempotency_key": "task-call-001"
}
```
- **Response `201 Created`**:
```json
{
  "id": "task_a1b2c3d4e5f6",
  "lead_id": "LEAD-101",
  "title": "Discovery Call with Alice",
  "description": "Discuss enterprise pricing and security questions",
  "scheduled_for": "2026-11-22T09:00:00Z",
  "scheduled_for_local": "2026-11-22T14:30:00+05:30",
  "timezone": "Asia/Kolkata",
  "priority": "HIGH",
  "channel": "CALL",
  "status": "SCHEDULED",
  "metadata": {},
  "idempotency_key": "task-call-001",
  "completed_at": null,
  "created_at": "2026-11-20T10:50:00Z",
  "updated_at": "2026-11-20T10:50:00Z"
}
```

### `GET /api/v1/automation/tasks/upcoming`
List upcoming scheduled tasks sorted by target date ascending.
- **Query params**: `limit=20`

### `GET /api/v1/automation/tasks/overdue`
List tasks that are still in `SCHEDULED` status whose `scheduled_for` is in the past.
- **Query params**: `limit=20`

### `POST /api/v1/automation/tasks/{task_id}/reschedule`
- **Payload**:
```json
{
  "scheduled_for": "2026-11-24T11:00:00Z",
  "timezone": "Asia/Kolkata"
}
```

### `POST /api/v1/automation/tasks/{task_id}/complete`
Mark task as completed (`status: "COMPLETED"`).

### `POST /api/v1/automation/tasks/{task_id}/cancel`
Cancel task (`status: "CANCELLED"`).

---

## 4. Automated Reminders

### `POST /api/v1/automation/reminders`
Create a persistent reminder.
- **Payload**:
```json
{
  "lead_id": "LEAD-101",
  "task_id": "task_a1b2c3d4e5f6",
  "title": "Prepare proposal slides",
  "remind_at": "2026-11-22T08:30:00Z",
  "channel": "INTERNAL_LOG"
}
```

### `GET /api/v1/automation/reminders/pending`
Retrieve all reminders currently awaiting delivery (`status: "PENDING"`).

### `POST /api/v1/automation/reminders/{reminder_id}/dismiss`
Dismiss an open reminder so it is not processed (`status: "DISMISSED"`).

---

## 5. Workflow Rules & Executions

### `POST /api/v1/automation/rules`
Create a conditional automation rule.
- **Payload**:
```json
{
  "name": "Hot Lead Meeting Followup",
  "trigger_type": "INTENT_CLASSIFIED",
  "conditions": {
    "intent_category": "MEETING_REQUEST",
    "min_score": 75
  },
  "actions": [
    {
      "type": "SEND_EMAIL",
      "params": {
        "template": "meeting_confirmation"
      }
    }
  ],
  "requires_approval": true,
  "is_active": true
}
```

### `PATCH /api/v1/automation/rules/{rule_id}`
Enable, disable, or modify rule attributes.

### `DELETE /api/v1/automation/rules/{rule_id}`
Delete a workflow rule and clean up associated executions safely.

### `POST /api/v1/automation/rules/{rule_id}/trigger`
Manually trigger execution of a specific rule.
- **Payload**:
```json
{
  "lead_id": "LEAD-101",
  "context_data": {"source": "manual_review"}
}
```

### `POST /api/v1/automation/workflows/trigger`
Broadcast an event across all active rules matching a trigger type.

---

## 6. Human Approvals

### `GET /api/v1/automation/approvals/pending`
Retrieve all approvals awaiting review.

### `POST /api/v1/automation/approvals/{approval_id}/decision`
Submit human decision.
- **Payload**:
```json
{
  "action": "APPROVE",
  "reviewed_by": "lead_manager@example.com",
  "decision_notes": "Pricing approved by executive team."
}
```
Or to reject:
```json
{
  "action": "REJECT",
  "reviewed_by": "lead_manager@example.com",
  "rejection_reason": "Lead requested phone call only."
}
```

### `POST /api/v1/automation/approvals/expire-stale`
Sweep and mark expired requests (`status: "EXPIRED"`).

---

## 7. Background Job Management

### `GET /api/v1/automation/jobs`
List persistent jobs with status filtering.

### `POST /api/v1/automation/jobs/process`
Trigger immediate processing of due background jobs.
- **Query params**: `batch_size=10`
