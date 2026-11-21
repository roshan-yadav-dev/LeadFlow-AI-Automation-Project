# Phase 6.1: Automation Foundation

## Architecture Overview

Phase 6.1 establishes the foundational architecture for lead automation in LeadFlow AI, covering:
1. **Follow-up scheduling**: Managing upcoming and scheduled communications.
2. **Lead prioritization and scoring**: Multi-tier scoring (HOT, WARM, COLD) with factor analysis.
3. **Automated reminders**: Alerting internal operators/reps before tasks are due.
4. **Conditional workflow triggers**: Defining rules and logging execution history.
5. **Human approval safeguards**: Enforcing approval before sensitive actions.
6. **Persistent background processing**: A SQLite-backed job queue running on the single-Uvicorn-worker deployment without external message brokers.

All timestamps are stored in **UTC** in ISO-8601 format, while **Asia/Kolkata** (IST, UTC+5:30) is the default user-facing timezone.

---

## Safety Rules and Policies

The automation foundation strictly adheres to the following safeguards:
- **No modification of existing Google Sheets CRM records**: The automation service treats CRM rows strictly as read-only reference data for validating lead existence.
- **No changes to Gmail OAuth scopes**: Gmail send and readonly scopes remain unchanged.
- **No automatic external email sends**: Scheduled tasks and reminders do not send emails to customers automatically.
- **No modifications to Gmail message read/unread status**: Gmail sync integrity remains untouched.
- **Human approval required for sensitive actions**: Actions like `SEND_EMAIL`, `UPDATE_CRM`, or `EXTERNAL_WEBHOOK` transition workflow executions to `AWAITING_APPROVAL` and generate an `ApprovalRequest`.
- **Validation of every Lead ID**: Every operation validates that the lead exists in either Google Sheets CRM or the SQLite Gmail Intelligence database before proceeding.
- **Duplicate prevention via Idempotency Keys**: Unique idempotency constraints prevent duplicate tasks, scores, reminders, executions, and jobs.
- **Comprehensive Audit Logging**: All automation lifecycle events are recorded in `automation_audit_logs`.

---

## Database Architecture and Schema

The automation system uses a dedicated SQLite database configured via `settings.AUTOMATION_DB_FILE` (defaults to `credentials/automation.sqlite3`), with owner-only file permissions (`0600`), WAL journal mode, and foreign keys enabled.

### Tables

1. **`lead_scores`**:
   - `id TEXT PRIMARY KEY`: Prefixed UUID (`score_...`).
   - `lead_id TEXT NOT NULL`: Associated CRM lead.
   - `score INTEGER NOT NULL`: Numerical score (0–100).
   - `tier TEXT NOT NULL`: Category (`HOT`, `WARM`, `COLD`).
   - `factors TEXT NOT NULL`: JSON object detailing score contributors.
   - `version TEXT NOT NULL`: Scoring model version (default `v1`).
   - `idempotency_key TEXT UNIQUE`: Optional deduplication key.
   - `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`: UTC timestamps.
   - *Indexes*: `(lead_id, created_at DESC)`, `(tier)`.

2. **`follow_up_tasks`**:
   - `id TEXT PRIMARY KEY`: Prefixed UUID (`task_...`).
   - `lead_id TEXT NOT NULL`: Associated CRM lead.
   - `title TEXT NOT NULL`, `description TEXT NOT NULL`: Task information.
   - `scheduled_for TEXT NOT NULL`: Target time in UTC.
   - `timezone TEXT NOT NULL`: Default `Asia/Kolkata`.
   - `priority TEXT NOT NULL`: `LOW`, `MEDIUM`, `HIGH`, `URGENT`.
   - `status TEXT NOT NULL`: `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`.
   - `channel TEXT NOT NULL`: `EMAIL`, `CALL`, `MEETING`, `MANUAL`.
   - `metadata TEXT NOT NULL`: JSON object.
   - `idempotency_key TEXT UNIQUE`: Optional deduplication key.
   - `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`.
   - *Indexes*: `(lead_id, status)`, `(scheduled_for, status)`.

3. **`reminders`**:
   - `id TEXT PRIMARY KEY`: Prefixed UUID (`rem_...`).
   - `task_id TEXT`: Optional foreign key to `follow_up_tasks(id)`.
   - `lead_id TEXT NOT NULL`: Associated CRM lead.
   - `title TEXT NOT NULL`: Reminder summary.
   - `remind_at TEXT NOT NULL`: Target notification time in UTC.
   - `timezone TEXT NOT NULL`: Default `Asia/Kolkata`.
   - `status TEXT NOT NULL`: `PENDING`, `SENT`, `DISMISSED`, `FAILED`.
   - `recipient TEXT NOT NULL`: Target internal user/rep.
   - `channel TEXT NOT NULL`: `INTERNAL_LOG`, `NOTIFICATION`.
   - `idempotency_key TEXT UNIQUE`: Optional deduplication key.
   - `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`.
   - *Indexes*: `(lead_id, status)`, `(remind_at, status)`, `(task_id)`.

4. **`workflow_rules`**:
   - `id TEXT PRIMARY KEY`: Prefixed UUID (`rule_...`).
   - `name TEXT NOT NULL`: Rule name.
   - `trigger_type TEXT NOT NULL`: `LEAD_CREATED`, `INTENT_CLASSIFIED`, `SCORE_UPDATED`, `SCHEDULED_TIME`, `MANUAL`.
   - `conditions TEXT NOT NULL`: JSON object of evaluation conditions.
   - `actions TEXT NOT NULL`: JSON array of target actions.
   - `requires_approval INTEGER NOT NULL`: Default `1` (true).
   - `is_active INTEGER NOT NULL`: Default `1` (true).
   - `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`.
   - *Indexes*: `(trigger_type, is_active)`.

5. **`workflow_executions`**:
   - `id TEXT PRIMARY KEY`: Prefixed UUID (`exec_...`).
   - `rule_id TEXT NOT NULL`: Foreign key to `workflow_rules(id)`.
   - `lead_id TEXT NOT NULL`: Associated CRM lead.
   - `trigger_event TEXT NOT NULL`: Event descriptor.
   - `status TEXT NOT NULL`: `PENDING`, `AWAITING_APPROVAL`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED`.
   - `context_data TEXT NOT NULL`: JSON payload provided at trigger.
   - `result_data TEXT`: JSON output upon completion.
   - `error_message TEXT`: Error details if failed.
   - `idempotency_key TEXT UNIQUE`: Optional deduplication key.
   - `started_at TEXT`, `completed_at TEXT`.
   - `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`.
   - *Indexes*: `(lead_id, status)`, `(rule_id)`.

6. **`approval_requests`**:
   - `id TEXT PRIMARY KEY`: Prefixed UUID (`appr_...`).
   - `workflow_execution_id TEXT`: Foreign key to `workflow_executions(id)`.
   - `lead_id TEXT NOT NULL`: Associated CRM lead.
   - `action_type TEXT NOT NULL`: Action name (e.g., `SEND_EMAIL`).
   - `action_payload TEXT NOT NULL`: JSON parameters for proposed action.
   - `status TEXT NOT NULL`: `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`.
   - `requested_by TEXT NOT NULL`: User or service identifier.
   - `reviewed_by TEXT`, `reviewed_at TEXT`: Approver information.
   - `rejection_reason TEXT`: Reason if rejected.
   - `idempotency_key TEXT UNIQUE`: Optional deduplication key.
   - `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`.
   - *Indexes*: `(lead_id, status)`.

7. **`automation_audit_logs`**:
   - `id TEXT PRIMARY KEY`: Prefixed UUID (`audit_...`).
   - `entity_type TEXT NOT NULL`: Entity category.
   - `entity_id TEXT NOT NULL`: Target entity ID.
   - `lead_id TEXT`: Associated lead ID if applicable.
   - `action TEXT NOT NULL`: Action type (`CREATED`, `UPDATED`, `STATUS_CHANGE`, `APPROVED`, `REJECTED`, `JOB_COMPLETED`, etc.).
   - `actor TEXT NOT NULL`: Performing identity.
   - `details TEXT NOT NULL`: JSON payload with changes or metadata.
   - `ip_address TEXT`: Client IP if available.
   - `created_at TEXT NOT NULL`.
   - *Indexes*: `(entity_type, entity_id)`, `(lead_id)`, `(created_at DESC)`.

8. **`automation_jobs`**:
   - `id TEXT PRIMARY KEY`: Prefixed UUID (`job_...`).
   - `job_type TEXT NOT NULL`: Registered handler name (`PROCESS_REMINDER`, `PROCESS_FOLLOW_UP`, `EVALUATE_WORKFLOW`).
   - `payload TEXT NOT NULL`: JSON parameters.
   - `scheduled_at TEXT NOT NULL`: Scheduled execution timestamp in UTC.
   - `status TEXT NOT NULL`: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `CANCELLED`.
   - `attempts INTEGER NOT NULL`: Current execution count (starts at 0).
   - `max_retries INTEGER NOT NULL`: Default `3`.
   - `locked_until TEXT`: Expiration timestamp of execution lock (for atomic claim & crash recovery).
   - `last_error TEXT`: Error log from previous attempt.
   - `idempotency_key TEXT UNIQUE`: Deduplication key.
   - `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`.
   - *Indexes*: `(status, scheduled_at)`, `(locked_until)`.

---

## Background Processing Architecture

- **Persistent & Crash-Resilient**: Jobs are saved to SQLite disk storage. If the application restarts, pending jobs remain persisted. Upon application startup, any abandoned jobs stuck in `PROCESSING` state are automatically reset to `PENDING`.
- **Atomic Claiming**: `AutomationStore.claim_due_jobs()` uses `BEGIN IMMEDIATE` transactions to select and lock due jobs (`locked_until = now + lock_duration`). No two workers or concurrent coroutines can claim the same job.
- **Retry with Exponential Backoff**: When a job handler throws an error, `AutomationStore.fail_job()` schedules a retry with exponential delay (`min(300, 10 * 2^(attempts-1))`) as long as `attempts < max_retries`. If max retries are exceeded, the job transitions to `FAILED`.
- **Single-Worker Loop**: Runs an asyncio background loop in FastAPI lifespan (`AutomationWorker`), polling at configurable intervals (`AUTOMATION_WORKER_POLL_INTERVAL_SECONDS`, default 10s). It requires zero external infrastructure.

---

## API Endpoints

All protected endpoints require the existing `X-Webhook-Secret` header.

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/v1/automation/health` | Health status of database and background worker | No |
| `GET` | `/api/v1/automation/status` | Overview counts of scores, tasks, reminders, jobs | Yes |
| `POST` | `/api/v1/automation/scores` | Record or update lead score (validates lead_id) | Yes |
| `GET` | `/api/v1/automation/scores/{lead_id}` | Get latest lead score | Yes |
| `GET` | `/api/v1/automation/scores/{lead_id}/history` | Get score history for a lead | Yes |
| `POST` | `/api/v1/automation/tasks` | Create / schedule a follow-up task | Yes |
| `GET` | `/api/v1/automation/tasks` | List follow-up tasks (filters: `lead_id`, `status`) | Yes |
| `GET` | `/api/v1/automation/tasks/{task_id}` | Get task details | Yes |
| `PATCH` | `/api/v1/automation/tasks/{task_id}` | Update task status or metadata | Yes |
| `POST` | `/api/v1/automation/reminders` | Create an automated reminder | Yes |
| `GET` | `/api/v1/automation/reminders` | List reminders (filters: `lead_id`, `task_id`, `status`) | Yes |
| `GET` | `/api/v1/automation/reminders/{reminder_id}` | Get reminder details | Yes |
| `POST` | `/api/v1/automation/rules` | Create a workflow rule | Yes |
| `GET` | `/api/v1/automation/rules` | List workflow rules | Yes |
| `GET` | `/api/v1/automation/rules/{rule_id}` | Get workflow rule | Yes |
| `POST` | `/api/v1/automation/executions` | Trigger workflow execution (creates approval if sensitive) | Yes |
| `GET` | `/api/v1/automation/executions` | List executions | Yes |
| `GET` | `/api/v1/automation/executions/{execution_id}` | Get execution details | Yes |
| `GET` | `/api/v1/automation/approvals` | List approval requests (filters: `status`, `lead_id`) | Yes |
| `GET` | `/api/v1/automation/approvals/{approval_id}` | Get approval request | Yes |
| `POST` | `/api/v1/automation/approvals/{approval_id}/decision` | Approve or reject sensitive action | Yes |
| `GET` | `/api/v1/automation/audit-logs` | List audit logs (filters: `entity_type`, `entity_id`, `lead_id`) | Yes |
| `GET` | `/api/v1/automation/jobs` | List background queue jobs | Yes |
| `POST` | `/api/v1/automation/jobs/process` | Manually trigger job queue processing | Yes |
