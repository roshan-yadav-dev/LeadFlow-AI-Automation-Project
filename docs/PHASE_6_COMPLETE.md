# Phase 6: Lead Automation — Comprehensive Architecture & Implementation

## 1. Executive Summary

Phase 6 completes the **Lead Automation Engine** for LeadFlow AI, transforming inbound communication intelligence and CRM lead registration into an event-driven, deterministic, and safe automation platform.

Key achievements:
- **Phase 6.1 (Automation Foundation):** Dedicated SQLite database (`credentials/automation.sqlite3`), WAL journal mode, atomic transactions, idempotency guards, and UTC persistence with `Asia/Kolkata` localization.
- **Phase 6.2 (Deterministic Lead Scoring):** 100-point transparent algorithmic scoring calculated exclusively via Python business logic (no arbitrary LLM generation), structured across 6 distinct factors, tiered into HOT (75–100), WARM (40–74), and COLD (0–39), with complaint attention flagging and out-of-office neutrality.
- **Phase 6.3 (Follow-Up Task Scheduling):** ISO-8601 timestamp validation rejecting invalid dates with HTTP 422, naive and aware datetime normalization, upcoming and overdue task filtering, reschedule, complete, and cancel lifecycle.
- **Phase 6.4 (Automated Reminders):** Persistent reminder scheduling, automatic task linking, pending reminder queries, dismissal, and single-execution guarantees.
- **Phase 6.5 (Conditional Workflow Engine):** Event-driven rules engine supporting triggers (`LEAD_CREATED`, `INTENT_CLASSIFIED`, `SCORE_UPDATED`, `SCHEDULED_TIME`, `MANUAL`), declarative conditions (min/max score, tier, intent, sentiment, complaint, budget, CRM attributes), and automated actions (`CREATE_FOLLOW_UP`, `CREATE_REMINDER`, `UPDATE_LEAD_PRIORITY`, `REQUEST_HUMAN_APPROVAL`, `CREATE_INTERNAL_NOTIFICATION`).
- **Phase 6.6 (Human-in-the-Loop Approval Safeguards):** Mandatory human approval for sensitive actions (`SEND_EMAIL`, `UPDATE_CRM`, `EXTERNAL_WEBHOOK`). Execution status pausing at `AWAITING_APPROVAL`, reviewer approval/rejection with notes/reasons, automated expiry of stale requests, and zero automatic customer email dispatch.
- **Phase 6.7 (Persistent Background Job Queue & Worker):** In-process SQLite-backed single-Uvicorn worker, atomic job claiming (`status = 'PROCESSING'`), bounded exponential backoff retries, and survivability across application restarts without Redis/Celery.
- **Phase 1–5 End-to-End Integration:** Direct event hooks inside `lead_service.py` (`LEAD_CREATED`) and `gmail_intelligence_service.py` (`INTENT_CLASSIFIED` triggering real-time deterministic score recalculation).

---

## 2. Architecture & Design Principles

```
  +-----------------------------------------------------------------------------------+
  |                                LeadFlow AI System                                 |
  +-----------------------------------------------------------------------------------+
       |                                      |                                  |
 [Lead Registration]                [Inbound Gmail Sync]                 [Cron / Manual]
       |                                      |                                  |
  POST /api/v1/leads               POST /api/v1/gmail/messages/analyze           |
       |                                      |                                  |
       v                                      v                                  v
+------------------+                +--------------------+             +------------------+
| LEAD_CREATED     |                | INTENT_CLASSIFIED  |             | MANUAL / TIME    |
+------------------+                +--------------------+             +------------------+
       \                                      /                                  /
        \                                    /                                  /
         v                                  v                                  v
      +----------------------------------------------------------------------------+
      |                       Automation Event Bus (emit_event)                    |
      +----------------------------------------------------------------------------+
                                            |
                         +------------------+------------------+
                         |                                     |
                         v                                     v
         +-------------------------------+     +-------------------------------+
         |  Deterministic Scoring Engine |     |   Conditional Workflow Engine |
         |  (6 factors, Max 100 points)  |     |   (Rule & Condition Matcher)  |
         +-------------------------------+     +-------------------------------+
                         |                                     |
                         v                                     |
                 SCORE_UPDATED --------------------------------+
                                                               |
                                            +------------------+------------------+
                                            |                                     |
                                  [Non-Sensitive Action]                 [Sensitive Action]
                                            |                                     |
                                            v                                     v
                                +-----------------------+             +-----------------------+
                                | CREATE_FOLLOW_UP      |             | SEND_EMAIL            |
                                | CREATE_REMINDER       |             | UPDATE_CRM            |
                                | NOTIFICATION          |             | EXTERNAL_WEBHOOK      |
                                +-----------------------+             +-----------------------+
                                            |                                     |
                                            v                                     v
                                +-----------------------+             +-----------------------+
                                | Persistent Job Queue  |             | Human Approval Request|
                                | (SQLite WAL Worker)   |             | (Status: PENDING)     |
                                +-----------------------+             +-----------------------+
                                            |                                     |
                                            v                                     v
                                +-----------------------+             +-----------------------+
                                | Safe Execution        |             | Reviewer Decision     |
                                | & Audit Trail         |             | (APPROVE / REJECT)    |
                                +-----------------------+             +-----------------------+
```

---

## 3. Deterministic Lead Scoring Model (Phase 6.2)

Lead scoring is computed entirely in Python by `app/services/lead_scoring_service.py`. No arbitrary LLM hallucination is permitted.

### Scoring Factors (Total: 100 Points)

| Factor | Max Points | Evaluation Rules |
|---|---|---|
| **Customer Intent** | 30 | `MEETING_REQUEST`: 30 pts<br>`NEGOTIATION`: 28 pts<br>`INTERESTED`: 25 pts<br>`PRICING_INQUIRY`: 22 pts<br>`INFORMATION_REQUEST`: 15 pts<br>`FOLLOW_UP`: 12 pts<br>`COMPLAINT`: 10 pts (also sets attention flag)<br>`OUT_OF_OFFICE`: 5 pts (neutral, not penalized)<br>`OTHER`: 5 pts<br>`NOT_INTERESTED`: 0 pts |
| **Sentiment** | 20 | `POSITIVE`: 20 pts<br>`MIXED`: 12 pts<br>`NEUTRAL`: 10 pts<br>`NEGATIVE`: 0 pts |
| **Engagement & Response** | 15 | Distinct inbound messages from lead:<br>$\ge 3$ messages: 15 pts<br>$2$ messages: 10 pts<br>$1$ message: 6 pts<br>$0$ messages: 0 pts |
| **Budget & Buying Signals** | 15 | Valid budget in CRM: 8 pts<br>Explicit budget extracted from email: 4 pts<br>Specific meeting dates or commitments extracted: 3 pts<br>Capped at 15 pts |
| **Follow-Up Urgency** | 10 | Open task priority `URGENT`: 10 pts<br>Open task priority `HIGH`: 8 pts<br>Open task priority `MEDIUM`: 5 pts<br>Open task priority `LOW`: 3 pts<br>Or urgent timeline keywords in email ("asap", "immediate", "today"): 8 pts |
| **Recency of Interaction** | 10 | Last inbound message or CRM interaction:<br>$\le 24$ hours: 10 pts<br>$\le 3$ days: 8 pts<br>$\le 7$ days: 5 pts<br>$\le 14$ days: 2 pts<br>$> 14$ days: 0 pts |

### Lead Tiers
- **HOT:** 75 – 100
- **WARM:** 40 – 74
- **COLD:** 0 – 39

### Key Scoring Safeguards
1. **Complaint Attention Flag:** A complaint (`COMPLAINT` intent or negative sentiment with issue keywords) sets `complaint_attention_flag = True`. It does *not* automatically force a lead into the COLD tier if strong budget, urgency, and recency signals exist.
2. **Out-of-Office Neutrality:** Out-of-office autoreplies are scored at 5 points (neutral) and never treated as disinterest.
3. **Missing Data Safety:** Missing fields produce 0 points for that factor; they never cause negative deductions or 500 crashes.
4. **Message Deduplication:** Inbound messages are deduplicated by `message_id` to prevent inflated engagement scores.

---

## 4. Safety & Human Approval Safeguards (Phase 6.6)

LeadFlow AI strictly enforces the following non-negotiable safety rules:
1. **No Automatic Customer Emails:** Scheduled or approved `EMAIL` tasks or `SEND_EMAIL` actions do not automatically dispatch emails to customers. All customer communications require manual human oversight and execution.
2. **No Google Sheets CRM Overwrite:** Automation services only read CRM records for matching; they do not alter or delete customer lead rows.
3. **Sensitive Action Trapping:** Any workflow action of type `SEND_EMAIL`, `UPDATE_CRM`, or `EXTERNAL_WEBHOOK` automatically transitions the workflow execution to `AWAITING_APPROVAL` and creates an `approval_requests` entry.
4. **Approval Expiration:** Pending approval requests include an expiration timestamp (default: 72 hours). Stale requests are automatically expired by the worker.
5. **Full Audit Logging:** All state changes (scores, tasks, reminders, rules, executions, approvals, jobs) create immutable records in `automation_audit_logs`.

---

## 5. Background Processing Architecture (Phase 6.7)

- **Worker:** `AutomationWorker` runs as an asynchronous background loop within the single Uvicorn process.
- **Queue Table:** `automation_jobs` in SQLite.
- **Atomic Locking:** Workers claim jobs using an atomic single-statement lock:
  ```sql
  UPDATE automation_jobs
  SET status = 'PROCESSING', locked_until = ?, attempts = attempts + 1
  WHERE id IN (
      SELECT id FROM automation_jobs
      WHERE (status = 'PENDING' AND scheduled_at <= ?)
         OR (status = 'PROCESSING' AND locked_until < ?)
      ORDER BY scheduled_at ASC LIMIT ?
  )
  ```
- **Crash Recovery:** If a worker crashes mid-task, the lock expires (`locked_until < now`) and another iteration reclaims it safely.
- **Bounded Exponential Backoff:** Failed jobs retry up to `max_retries` with exponential backoff ($30 \times 2^{\text{attempts}}$ seconds), transitioning to `FAILED` if exhausted.
