# Phase 7: Frontend Dashboard Architecture

## 1. Overview & Architectural Principles

LeadFlow AI Phase 7 delivers a production-grade, responsive, and secure web control dashboard for the entire AI-powered lead capture, personalization, and automation system developed across Phases 1–6.

The frontend is architected according to five non-negotiable principles:
1. **Zero Secret Leakage:** Browser code never possesses, stores, or transmits `WEBHOOK_SECRET`, Google Service Account keys, Gmail OAuth tokens, or Groq API keys.
2. **Backend as Source of Truth:** All scoring calculations, workflow rule condition evaluations, job dispatches, and state transitions are executed exclusively by the backend FastAPI services and SQLite stores.
3. **Decoupled Authorization & Execution:** In the Human Approval Center, granting approval (`APPROVE`) authorizes the action in the system (`authorization_granted=True`), but sensitive actions like `SEND_EMAIL` are NEVER automatically dispatched to customers by the background worker or approval service (`action_executed=False`). Outbound communications preserve the Phase 6 safety policy and require deliberate manual execution.
4. **Timezone Determinism:** User-facing schedules and datetimes are presented in **Asia/Kolkata (IST)** by default, while network payloads submit standardized ISO-8601 strings with explicit UTC normalization.
5. **Robust Offline & Degraded State Handling:** In environments where external networks (Google Sheets, Gmail API) are unreachable, the UI gracefully renders cached local SQLite intelligence records and displays informative synchronization badges.
6. **Production Credential Hardening:** Default development passwords (e.g. `LeadFlow2026!Secure`, `admin123`) are strictly rejected in production. Startup validation fails safely (`RuntimeError`) if secure production credentials are not configured.

---

## 2. Technology Stack & Rationale

| Layer | Technology | Version | Rationale |
| :--- | :--- | :--- | :--- |
| **Framework** | React | `^18.3.1` | Declarative component model, ecosystem maturity, strict type compatibility. |
| **Build Tool** | Vite | `^5.4.9` | Sub-second HMR, optimized Rollup bundling, native ESM dev server. |
| **Language** | TypeScript | `^5.6.3` | End-to-end type safety matching backend Pydantic models. |
| **Styling** | Tailwind CSS | `^3.4.14` | Utility-first CSS, dark mode support, rapid responsive layout design. |
| **Routing** | React Router | `^6.27.0` | Client-side routing, protected route wrappers, search param state sync. |
| **Server State** | TanStack Query | `^5.59.0` | Asynchronous query caching, optimistic UI updates, background polling, automatic refetching. |
| **HTTP Client** | Axios | `^1.7.7` | Interceptors for double-submit CSRF tokens and standardized error handling. |
| **Charts** | Recharts | `^2.13.0` | Declarative SVG-based charts, responsive containers, custom tooltips. |
| **Icons** | Lucide React | `^0.453.0` | Clean, modern iconography with minimal bundle footprint. |
| **Forms & Validation** | React Hook Form + Zod | `^7.53.0` / `^3.23.8` | Performant uncontrolled forms with declarative schema validation. |
| **Testing** | Vitest + Testing Library | `^2.1.3` / `^16.0.1` | Fast unit/component tests in jsdom environment. |

---

## 3. Directory & Component Hierarchy

```
frontend/src/
├── app/
│   ├── App.tsx               # QueryClientProvider, BrowserRouter, AuthProvider root
│   └── main.tsx              # React DOM entrypoint
├── components/
│   ├── common/               # Reusable UI primitives
│   │   ├── ConfirmationModal.tsx
│   │   ├── DateTimeDisplay.tsx
│   │   ├── EmptyState.tsx
│   │   ├── ErrorBanner.tsx
│   │   ├── LoadingSkeleton.tsx
│   │   ├── Modal.tsx
│   │   ├── ScoreGauge.tsx
│   │   ├── StatCard.tsx
│   │   ├── StatusBadge.tsx
│   │   └── Tabs.tsx
│   └── layout/               # Shell layout & navigation
│       ├── AppLayout.tsx     # Responsive container with sidebar and topbar
│       ├── Sidebar.tsx       # Collapsible navigation menu with badging
│       └── Topbar.tsx        # Breadcrumbs, worker health pill, theme toggle, logout
├── hooks/
│   └── useAuth.tsx           # Session verification, login, logout context
├── pages/                    # 12 core dashboard views
│   ├── Approvals/            # Human Approval Center (safety rules, decision modal)
│   ├── AuditLogs/            # Immutable event logs, payload modal, filtering
│   ├── AutomationJobs/       # Single-process worker status, queue inspection, tick trigger
│   ├── Dashboard/            # KPI metrics, 4 Recharts charts, recent activity feed
│   ├── GmailIntelligence/   # Sync inbox, match CRM leads, analyze, sentiment inspector
│   ├── Leads/                # Lead directory, multi-column search, 5-tab detail view
│   ├── LeadScoring/          # 100-point factor inspector, recalculate all modal, leaderboard
│   ├── Login/                # Secure operator login, rate limit error feedback
│   ├── Reminders/            # Pending & all reminders, creation modal, dismissal
│   ├── Settings/             # Engine diagnostics, SQLite paths, timezone & security status
│   ├── Tasks/                # Upcoming, overdue, and all tasks; Asia/Kolkata date picker
│   └── Workflows/            # Visual WHEN/IF/THEN rule editor, manual trigger modal
├── router.tsx                # Route definitions & ProtectedRoute guard
├── services/                 # Type-safe Axios API services
│   ├── api.ts                # Axios instance with CSRF cookie/header interceptor
│   ├── auth.ts
│   ├── approvals.ts
│   ├── audit.ts
│   ├── automation.ts
│   ├── dashboard.ts
│   ├── gmail.ts
│   ├── leads.ts
│   ├── reminders.ts
│   ├── scoring.ts
│   ├── tasks.ts
│   └── workflows.ts
├── styles/
│   └── index.css             # Tailwind base, components, utilities, custom scrollbars
├── test/                     # Vitest component & unit tests
│   ├── App.test.tsx
│   ├── Approvals.test.tsx
│   ├── Auth.test.tsx
│   ├── Leads.test.tsx
│   └── setup.ts              # Testing library setup, matchMedia & ResizeObserver mocks
└── types/                    # TypeScript interfaces matching backend models
```

---

## 4. State Management & Server Synchronization

### TanStack Query Architecture
- **Stale Time:** Queries default to a 30-second `staleTime`, preventing redundant network requests on tab navigation while ensuring fresh data.
- **Window Focus Refetch:** Disabled (`refetchOnWindowFocus: false`) to avoid jarring visual updates during operator workflow.
- **Query Key Conventions:** Hierarchical arrays:
  - `['leads', { search, status, tier, sortBy, page }]`
  - `['lead-detail', leadId]`
  - `['approvals', 'pending']`
  - `['dashboard-overview']`
  - `['worker-health']`
- **Mutations & Cache Invalidation:** Mutations (e.g. `calculateScore`, `recordDecision`, `createTask`, `dismissReminder`) systematically invalidate related queries:
  ```ts
  queryClient.invalidateQueries({ queryKey: ['leads'] });
  queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  queryClient.invalidateQueries({ queryKey: ['approvals'] });
  ```

---

## 5. Security Architecture (BFF Pattern)

### 1. Dual-Path Authentication Guard
The backend security dependency `verify_webhook_secret` was extended to accept either:
1. `X-Webhook-Secret` header (preserving 100% backward compatibility for automated webhook dispatches, Phase 1–6 tests, and CLI scripts).
2. A valid, signed HttpOnly session cookie (`leadflow_session`) issued upon successful operator authentication.

### 2. Session Management & Password Protection
- **PBKDF2 SHA-256:** Dashboard passwords are verified with 100,000 iterations of PBKDF2 SHA-256 and cryptographic salts.
- **Session Lifecycle:** `leadflow_session` is stored in an in-memory session registry with an 8-hour rolling TTL.
- **Logout:** `POST /api/v1/auth/logout` explicitly destroys the session server-side and clears the cookie.

### 3. Double-Submit CSRF Protection
- For all state-changing HTTP requests (`POST`, `PATCH`, `DELETE`, `PUT`), the backend issues a random cryptographic token in both:
  1. The response JSON (`csrf_token`).
  2. A readable cookie (`leadflow_csrf`).
- The Axios request interceptor extracts this token and transmits it in the `X-CSRF-Token` header.
- The server validates that the header matches the active session's registered CSRF token before permitting execution.

### 4. Brute-Force Rate Limiting
- The `POST /api/v1/auth/login` endpoint enforces an IP-based sliding window rate limiter: maximum **5 failed attempts per 15-minute window**. Exceeding this threshold returns `HTTP 429 Too Many Requests` with a descriptive retry cooldown.
