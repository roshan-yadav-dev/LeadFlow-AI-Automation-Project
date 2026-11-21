# LeadFlow-AI

AI-Powered Lead Capture, Personalization, Automation & Control System.

LeadFlow AI connects inbound lead capture with Groq LLM personalization, Google Sheets CRM synchronization, Gmail inbox intelligence, and an autonomous deterministic lead scoring, follow-up scheduling, and human-in-the-loop automation engine.

---

## Phase 7: Complete Frontend Dashboard

Phase 7 introduces a production-ready, responsive, dark-mode enabled web control dashboard built with **React 18, Vite, TypeScript, Tailwind CSS, TanStack Query, and Recharts**.

### Key Modules:
- **Executive Dashboard:** Live KPI stat cards (Total Leads, Hot/Warm/Cold, Pending Approvals, Upcoming Tasks), 4 interactive Recharts charts (lead temperature distribution, lead score brackets, task statuses, workflow outcomes), and real-time audit stream.
- **Lead Directory & Profiles:** Search by name/company/email, filter by tier and lead status, sort, and inspect leads across a 5-tab profile (Overview, Communications, AI Intelligence, Tasks, Activity Timeline).
- **AI Lead Scoring:** 100-point factor breakdown (Intent, Sentiment, Engagement, Budget, Urgency, Recency), hot/warm/cold classifications, complaint attention flags, leaderboard ranking, and on-demand recalculation.
- **Follow-up Tasks:** Scheduling in **Asia/Kolkata (IST)** with ISO-8601 UTC submission, upcoming vs. overdue separation, and reschedule/complete/cancel controls.
- **Human Approval Center:** Safety guardrail where sensitive actions (`SEND_EMAIL`, `UPDATE_CRM`) pause in `PENDING` status. Distinct authorization vs. execution tracking; rejection requires an explicit rationale; no client-side email dispatch.
- **Workflow Automation:** Visual WHEN/IF/THEN rule builder, manual trigger modal, and execution logs.
- **Gmail Intelligence:** Inbound inbox synchronization, CRM contact matching, Groq AI sentiment/intent classification, and message inspect modal.
- **Security & Access (BFF):** HttpOnly session cookies, double-submit CSRF protection, PBKDF2 password hashing, and login rate limiting (5 attempts per 15 min).

### Documentation:
- [Phase 7 Frontend Architecture](docs/PHASE_7_FRONTEND_ARCHITECTURE.md)
- [Phase 7 Implementation Ledger](docs/PHASE_7_IMPLEMENTATION.md)
- [Phase 7 API Integration Reference](docs/PHASE_7_API_INTEGRATION.md)
- [Phase 7 Testing Guide](docs/PHASE_7_TESTING_GUIDE.md)
- [Phase 7 Deployment Guide](docs/PHASE_7_DEPLOYMENT_GUIDE.md)

### Quickstart: Running Backend & Frontend

```bash
# 1. Run Backend Server (FastAPI on http://127.0.0.1:8000)
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 2. Run Frontend Development Server (http://localhost:5173)
cd frontend
npm install
npm run dev

# 3. Production Build
cd frontend
npm run build
```

Default Dashboard Login:
- Username: `admin`
- Password: Configure `DASHBOARD_PASSWORD` in `.env` (default in dev: `admin123`)

---

## Gmail Inbox Integration

The Gmail inbox is stored in a local SQLite database. SQLite provides
transactional `message_id` uniqueness, while Google Sheets remains the lead
database and is not used for inbox deduplication or checkpoints.

Modules:

- `app/services/gmail_inbox_service.py`: Gmail API retrieval and pagination.
- `app/services/gmail_parser.py`: Base64URL decoding and MIME parsing.
- `app/services/gmail_sync_service.py`: SQLite persistence, locking, checkpoint
  updates, manual sync, and the optional scheduler.
- `app/api/gmail.py`: OAuth, synchronization, and inbox endpoints.

## Gmail Lead Intelligence

Phase 5 adds a separate SQLite store and a manual workflow for matching
synchronized inbound messages to CRM leads, classifying matched messages with
the existing Groq client, and retrieving lead communication history. It does
not send replies or write to Google Sheets. See
[docs/PHASE_5_GMAIL_INTELLIGENCE.md](docs/PHASE_5_GMAIL_INTELLIGENCE.md) for
the schema, API examples, configuration, and manual testing procedure.

The intelligence API uses the existing `X-Webhook-Secret` authentication used
by lead registration. Configure `GMAIL_INTELLIGENCE_DB_FILE`,
`GMAIL_INTELLIGENCE_BATCH_SIZE`, `GMAIL_INTELLIGENCE_MAX_BATCH_SIZE`, and
`GMAIL_INTELLIGENCE_MAX_BODY_CHARS` to control its database and processing
limits.

## Lead Automation Engine (Phase 6 Complete)

Phase 6 provides a comprehensive, production-ready lead automation engine:
- **Deterministic Lead Scoring:** 100-point transparent algorithmic scoring calculated exclusively via Python business logic across 6 factors (Intent, Sentiment, Engagement, Budget, Urgency, Recency) with HOT/WARM/COLD tiers, complaint attention flagging, and out-of-office neutrality.
- **Follow-Up Task Scheduling:** Timezone-aware and naive ISO-8601 validation (HTTP 422 on invalid input), Asia/Kolkata localization, upcoming/overdue filtering, reschedule, complete, and cancel lifecycle.
- **Automated Reminders:** Persistent reminder scheduling, task associations, dismissal, and single-execution guarantees.
- **Conditional Workflow Engine:** Event-driven rules engine triggered by `LEAD_CREATED`, `INTENT_CLASSIFIED`, `SCORE_UPDATED`, `SCHEDULED_TIME`, or `MANUAL`. Supports multi-attribute conditions and automated action execution.
- **Human-in-the-Loop Approval Safeguards:** Sensitive actions (`SEND_EMAIL`, `UPDATE_CRM`, `EXTERNAL_WEBHOOK`) pause in `AWAITING_APPROVAL`. Reviewer decisions (`APPROVE`/`REJECT`), automated expiration of stale requests, and zero automatic customer email dispatch.
- **Persistent Background Processing:** SQLite WAL-backed single-worker architecture with atomic job locking, bounded exponential backoff retries, and persistence across server restarts.

Documentation:
- Architecture & Design: [docs/PHASE_6_COMPLETE.md](docs/PHASE_6_COMPLETE.md)
- Complete API Reference: [docs/PHASE_6_API_REFERENCE.md](docs/PHASE_6_API_REFERENCE.md)
- Testing & Verification Guide: [docs/PHASE_6_TESTING_GUIDE.md](docs/PHASE_6_TESTING_GUIDE.md)
- Foundation Reference: [docs/PHASE_6_1_AUTOMATION_FOUNDATION.md](docs/PHASE_6_1_AUTOMATION_FOUNDATION.md)

Configuration:
- `AUTOMATION_DB_FILE=credentials/automation.sqlite3`
- `AUTOMATION_WORKER_ENABLED=true`
- `AUTOMATION_WORKER_POLL_INTERVAL_SECONDS=10`
- `AUTOMATION_DEFAULT_TIMEZONE=Asia/Kolkata`

Timestamps are stored in UTC; the default user-facing timezone is Asia/Kolkata.

## Environment Variables

```env
GMAIL_CLIENT_SECRET_FILE=credentials/gmail_oauth_client.json
GMAIL_TOKEN_FILE=credentials/gmail_token.json
GMAIL_REDIRECT_URI=http://localhost:8001/api/v1/gmail/oauth/callback
GMAIL_SENDER_EMAIL=your_personal_gmail@gmail.com

GMAIL_SYNC_ENABLED=false
GMAIL_SYNC_INTERVAL_SECONDS=300
GMAIL_SYNC_BATCH_SIZE=50
GMAIL_SYNC_MAX_PAGES=5
GMAIL_DB_FILE=credentials/gmail_inbox.sqlite3

AUTOMATION_DB_FILE=credentials/automation.sqlite3
AUTOMATION_WORKER_ENABLED=true
AUTOMATION_WORKER_POLL_INTERVAL_SECONDS=10
AUTOMATION_DEFAULT_TIMEZONE=Asia/Kolkata
```

Automatic synchronization is disabled by default. The database and OAuth token
files are created with owner-only permissions where supported.

## OAuth Setup

1. Enable the Gmail API in Google Cloud Console.
2. Configure an OAuth 2.0 Web application client.
3. Add the exact callback URL to Authorized redirect URIs:
   `http://localhost:8001/api/v1/gmail/oauth/callback`
4. Keep the Gmail send and Gmail readonly scopes in the OAuth consent screen.
5. Existing authorization must be repeated after readonly scope support is
   added. Open `/api/v1/gmail/authorize`, grant consent again, and verify
   `/api/v1/gmail/status`.

The application requests only:

- `https://www.googleapis.com/auth/gmail.send`
- `https://www.googleapis.com/auth/gmail.readonly`

## Lead Email Automation

When a lead is registered, LeadFlow saves it to Google Sheets before attempting
delivery. An email is sent only when consent is true, AI email generation
succeeds, a sender is configured, and the existing Gmail OAuth connection is
valid. The lead response includes `email_status` (`PENDING`, `SENT`, `FAILED`,
or `SKIPPED`), and the same status and a safe error message are written to
columns K and M respectively.

The saved lead acts as the idempotency guard: repeating a registration for an
existing email returns the existing duplicate response and does not send again.
Same-email requests are also serialized within the application process. Run one
application worker when relying on this guard; Google Sheets does not provide
an atomic uniqueness constraint across multiple workers or hosts.
If Gmail times out or returns a server error after a send request, delivery is
treated as unknown, is not automatically retried, and the error directs the
operator to check Gmail's Sent folder before taking further action.

## API Endpoints

- `POST /api/v1/leads`
- `GET /api/v1/gmail/authorize`
- `GET /api/v1/gmail/oauth/callback`
- `GET /api/v1/gmail/status`
- `POST /api/v1/gmail/sync`
- `GET /api/v1/gmail/messages?page=1&page_size=25&unread=true&sender=...&date_from=...&date_to=...&search=...`
- `GET /api/v1/gmail/messages/{message_id}`
- `POST /api/v1/gmail/intelligence/match`
- `POST /api/v1/gmail/intelligence/analyze`
- `GET /api/v1/gmail/intelligence/overview`
- `GET /api/v1/gmail/intelligence/messages/{message_id}`
- `POST /api/v1/gmail/intelligence/messages/{message_id}/reanalyze`
- `GET /api/v1/leads/{lead_id}/communications`
- `GET /api/v1/automation/health`
- `GET /api/v1/automation/status`
- `POST /api/v1/automation/scores`
- `GET /api/v1/automation/scores/{lead_id}`
- `GET /api/v1/automation/scores/{lead_id}/history`
- `POST /api/v1/automation/tasks`
- `GET /api/v1/automation/tasks`
- `GET /api/v1/automation/tasks/{task_id}`
- `PATCH /api/v1/automation/tasks/{task_id}`
- `POST /api/v1/automation/reminders`
- `GET /api/v1/automation/reminders`
- `GET /api/v1/automation/reminders/{reminder_id}`
- `POST /api/v1/automation/rules`
- `GET /api/v1/automation/rules`
- `GET /api/v1/automation/rules/{rule_id}`
- `POST /api/v1/automation/executions`
- `GET /api/v1/automation/executions`
- `GET /api/v1/automation/executions/{execution_id}`
- `GET /api/v1/automation/approvals`
- `GET /api/v1/automation/approvals/{approval_id}`
- `POST /api/v1/automation/approvals/{approval_id}/decision`
- `GET /api/v1/automation/audit-logs`
- `GET /api/v1/automation/jobs`
- `POST /api/v1/automation/jobs/process`

`POST /api/v1/gmail/sync` is non-blocking through a worker thread and returns
fetched, new, duplicate, and error status. Synchronization overlap is prevented
by an in-process lock.

## Running

```bash
cd /home/roshan/LeadFlow-AI
venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Manual sync:

```bash
curl -X POST http://localhost:8001/api/v1/gmail/sync
```

Enable automatic synchronization only after OAuth reauthorization:

```env
GMAIL_SYNC_ENABLED=true
```

## Testing

Tests use mocked Gmail API responses and a temporary SQLite database:

```bash
venv/bin/pytest -q
```

No automated test sends email, uses real OAuth credentials, or contacts Google
Sheets.

## Known Limitations

- The synchronization lock is process-local; run one application worker for
  SQLite synchronization.
- SQLite does not provide a shared durable store for multiple hosts.
- Incremental sync uses Gmail's internal message timestamp checkpoint. The
  unique message ID prevents interrupted syncs from storing duplicates.
- Stored HTML is metadata/content for later safe rendering; the API does not
  render or execute it.
