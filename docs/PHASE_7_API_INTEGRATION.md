# Phase 7: API Integration Specification

This document details every backend endpoint integrated into the LeadFlow AI frontend dashboard.

---

## 1. Authentication & Session Endpoints

### `POST /api/v1/auth/login`
- **Method:** `POST`
- **Purpose:** Authenticates an operator, sets an HttpOnly `leadflow_session` cookie, and returns the CSRF token.
- **Rate Limit:** 5 failed attempts per 15-minute sliding window per client IP.
- **Request Body:**
  ```json
  {
    "username": "admin",
    "password": "your_password"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "status": "success",
    "user": {
      "username": "admin",
      "role": "admin"
    },
    "csrf_token": "random_token_string"
  }
  ```

### `POST /api/v1/auth/logout`
- **Method:** `POST`
- **Purpose:** Invalidates the operator session on the server and expires the cookie.
- **Response (200 OK):** `{"status": "logged_out"}`

### `GET /api/v1/auth/me`
- **Method:** `GET`
- **Purpose:** Verifies whether the incoming request has a valid active session.
- **Response (200 OK):**
  ```json
  {
    "authenticated": true,
    "user": { "username": "admin", "role": "admin" },
    "csrf_token": "token_string"
  }
  ```

---

## 2. Dashboard Executive Overview

### `GET /api/v1/dashboard/overview`
- **Method:** `GET`
- **Purpose:** Aggregates real-time counts, chart distributions, and recent audit activity.
- **Response (200 OK):**
  ```json
  {
    "total_leads": 42,
    "hot_leads": 12,
    "warm_leads": 18,
    "cold_leads": 12,
    "pending_followups": 7,
    "overdue_followups": 2,
    "pending_reminders": 4,
    "pending_approvals": 3,
    "active_workflows": 5,
    "total_executions": 88,
    "worker_running": true,
    "temperature_distribution": [
      { "name": "HOT", "value": 12, "color": "#ef4444" },
      { "name": "WARM", "value": 18, "color": "#f59e0b" },
      { "name": "COLD", "value": 12, "color": "#3b82f6" }
    ],
    "score_distribution": [
      { "name": "0-25", "value": 5 },
      { "name": "26-50", "value": 7 },
      { "name": "51-75", "value": 18 },
      { "name": "76-100", "value": 12 }
    ],
    "task_status_distribution": [
      { "name": "SCHEDULED", "value": 7 },
      { "name": "OVERDUE", "value": 2 }
    ],
    "workflow_execution_distribution": [
      { "name": "SUCCESS", "value": 80 },
      { "name": "FAILED", "value": 8 }
    ],
    "lead_creation_trend": [
      { "date": "2026-11-18", "count": 6 },
      { "date": "2026-11-19", "count": 10 }
    ],
    "recent_activity": [
      {
        "id": "audit-1",
        "action": "LEAD_SCORE_CALCULATED",
        "actor": "scoring-service",
        "timestamp": "2026-11-20T10:30:00Z",
        "details": { "score": 85, "tier": "HOT" }
      }
    ]
  }
  ```

---

## 3. Lead Management

### `GET /api/v1/leads`
- **Method:** `GET`
- **Query Params:** `search`, `status`, `tier`, `sort_by`, `sort_order`, `page`, `page_size`.
- **Response:**
  ```json
  {
    "leads": [
      {
        "lead_id": "lead-001",
        "name": "Jane Smith",
        "email": "jane@example.com",
        "phone": "+91 9876543210",
        "company": "Acme Corp",
        "service": "Enterprise AI",
        "lead_status": "NEW",
        "budget": "$50,000",
        "score": 85,
        "tier": "HOT",
        "intent": "PRICING_INQUIRY",
        "created_at": "2026-11-20T10:00:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "crm_synced": true
  }
  ```

### `GET /api/v1/leads/{lead_id}`
- **Method:** `GET`
- **Purpose:** Returns comprehensive lead data spanning all 5 profile tabs (Overview, Communications, AI Intelligence, Tasks, Timeline).

### `POST /api/v1/leads`
- **Method:** `POST`
- **Purpose:** Inbound lead registration with duplicate detection.
- **Request Body:**
  ```json
  {
    "name": "Alex Vance",
    "email": "alex@blackmesa.org",
    "phone": "+1 555-0199",
    "company": "Black Mesa",
    "service": "Automation Consulting",
    "requirements": "Need pipeline automation",
    "consent": true
  }
  ```

---

## 4. AI Lead Scoring

- `GET /api/v1/automation/scores/leaderboard?limit=50`: Returns ranked leads by score.
- `GET /api/v1/automation/scores/{lead_id}`: Retrieves score breakdown and version.
- `GET /api/v1/automation/scores/{lead_id}/history`: Returns historical score revisions.
- `POST /api/v1/automation/scores/calculate/{lead_id}`: Triggers algorithmic scoring for a lead.
- `POST /api/v1/automation/scores/recalculate`: Recalculates all scores across the database.

---

## 5. Tasks, Reminders & Workflows

- `GET /api/v1/automation/tasks/upcoming?days=7`: Upcoming scheduled follow-ups.
- `GET /api/v1/automation/tasks/overdue`: Overdue tasks.
- `POST /api/v1/automation/tasks/{task_id}/reschedule`: Reschedules task with a new datetime.
- `POST /api/v1/automation/tasks/{task_id}/complete`: Marks task completed.
- `POST /api/v1/automation/tasks/{task_id}/cancel`: Cancels task.
- `GET /api/v1/automation/reminders/pending`: Pending reminder alerts.
- `POST /api/v1/automation/reminders/{reminder_id}/dismiss`: Dismisses reminder.
- `GET /api/v1/automation/rules`: Lists active and soft-deleted rules.
- `POST /api/v1/automation/rules`: Creates a workflow rule with trigger, conditions, and actions.
- `POST /api/v1/automation/rules/{rule_id}/trigger`: Manually triggers a rule.
- `GET /api/v1/automation/executions`: Execution history with status and error details.

---

## 6. Approvals & System Operations

- `GET /api/v1/automation/approvals/pending`: Pending authorization requests.
- `POST /api/v1/automation/approvals/{approval_id}/decision`: Records `APPROVE` or `REJECT` decision (with mandatory reason on rejection).
- `POST /api/v1/automation/approvals/expire-stale`: Expires unreviewed requests older than 72 hours.
- `GET /api/v1/automation/worker/health`: Worker state and health status.
- `POST /api/v1/automation/worker/tick`: Manually triggers a worker execution batch.
- `GET /api/v1/automation/audit`: Filterable read-only audit log stream.
