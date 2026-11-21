# Phase 7: Testing & Verification Guide

This guide details how to execute automated backend tests, automated frontend tests, and manual verification procedures for LeadFlow AI.

---

## 1. Automated Test Suites

### Backend Test Suite (Pytest)
The backend test suite covers all Phases 1–6 plus the Phase 7 Dashboard Authentication and BFF endpoints.

```bash
# Activate virtual environment
source venv/bin/activate

# Run all 98 tests
pytest -v
```

Expected result:
```
======================= 98 passed in 14.86s ========================
```

Key test files:
- `tests/test_dashboard_auth.py`: Tests PBKDF2 password verification, rate limiting, session cookies, double-submit CSRF tokens, and lead aggregation endpoints.
- `tests/test_automation.py` & `test_automation_audit.py`: Tests SQLite persistence, atomic job locking, and lifecycle safety.
- `tests/test_automation_phase6.py`: Tests deterministic lead scoring, follow-up scheduling, and human approval safeguards.

---

### Frontend Test Suite (Vitest)
The frontend test suite exercises component rendering, router authentication guards, form submissions, and safety rules in a simulated DOM (`jsdom`).

```bash
# From project root
cd frontend

# Run test suite
npm test
```

Expected result:
```
Test Files  4 passed (4)
     Tests  9 passed (9)
```

Covered test files:
- `src/test/Auth.test.tsx`: Validates login form rendering, 401 invalid credentials error handling, and 429 rate limit error presentation.
- `src/test/Leads.test.tsx`: Validates lead directory table, column mappings, temperature badges, and empty states.
- `src/test/Approvals.test.tsx`: Verifies human approval safety invariants, distinct authorization vs. execution statuses, and mandatory rejection reasoning.
- `src/test/App.test.tsx`: Validates root router navigation, protected route redirection to `/login`, and authenticated dashboard loading.

---

## 2. Production Build Verification

Verify that TypeScript compiles without errors and Vite packages the production assets:

```bash
cd frontend
npm run build
```

Expected output:
```
✓ 2326 modules transformed.
dist/index.html                   0.59 kB
dist/assets/index-siGK0yJ0.css   39.47 kB
dist/assets/index-BO64-eeG.js   982.73 kB
✓ built in 13.05s
```

---

## 3. Manual QA Verification Checklist

### 1. Authentication & Security
- [ ] Navigate to `http://localhost:5173/`. Unauthenticated user is immediately redirected to `/login`.
- [ ] Submit invalid password: verify red alert with "Invalid username or password".
- [ ] Submit 5 consecutive invalid logins: verify 6th attempt triggers `HTTP 429` rate limit message.
- [ ] Log in with valid credentials (`admin` / configured password): redirected to `/dashboard`.
- [ ] Inspect cookies in Browser DevTools: verify `leadflow_session` is marked `HttpOnly` and `SameSite=Lax`.

### 2. Executive Dashboard
- [ ] Verify KPI metric cards (Total Leads, Hot Leads, Warm Leads, Cold Leads, Pending Approvals).
- [ ] Verify 4 interactive Recharts charts render with tooltips and empty states when no data is present.
- [ ] Verify Recent Automation Activity feed shows latest events.

### 3. Lead Management & Scoring
- [ ] Open `/leads`. Verify leads table displays name, email, company, score gauge, and tier badges.
- [ ] Test live search filter by name, company, or email.
- [ ] Click "Add Inbound Lead": fill form and submit. Verify success banner and table refresh.
- [ ] Click a lead to navigate to `/leads/:id`. Verify all 5 tabs:
  - Tab 1: Overview
  - Tab 2: Communication History
  - Tab 3: AI Intelligence (Groq classification)
  - Tab 4: Follow-up Tasks
  - Tab 5: Activity Timeline
- [ ] Click "Calculate Score" for a lead. Verify score updates to server-calculated value.

### 4. Human Approval Center (Critical Safety)
- [ ] Open `/approvals`. Verify amber security banner with safety invariants.
- [ ] Click "Reject" on a pending action: modal appears requiring rejection rationale.
- [ ] Verify "Block & Reject" button is disabled until a non-empty reason is entered.
- [ ] Verify approving an action updates status to `APPROVED` without triggering client-side emails.

### 5. Follow-up Tasks & Asia/Kolkata Datetimes
- [ ] Open `/tasks`. Verify tabs for "Upcoming Tasks" and "Overdue Tasks".
- [ ] Click "Schedule Task": select channel (`EMAIL`, `CALL`, `MEETING`, `MANUAL`) and priority (`URGENT`, `HIGH`, `MEDIUM`, `LOW`).
- [ ] Select a datetime in Indian Standard Time (IST). Submit and verify creation.
- [ ] Test "Reschedule", "Complete", and "Cancel" actions.

### 6. Settings & Diagnostics
- [ ] Open `/settings`. Verify Automation Worker loop state is `RUNNING`.
- [ ] Verify SQLite database file paths and WAL journal mode are displayed.
- [ ] Verify CSRF protection and default timezone (`Asia/Kolkata`) are operational.
