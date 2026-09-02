# RecoverAI

### AI-Powered Revenue Recovery

RecoverAI is a full-stack revenue recovery platform that helps merchants automatically identify failed payments and abandoned checkouts, analyse each case using an AI agent, and initiate recovery actions — including real Razorpay Test Mode payment links — with a complete audit trail.

---

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [Solution](#solution)
4. [Key Features](#key-features)
5. [End-to-End Workflow](#end-to-end-workflow)
6. [AI Decision-Making](#ai-decision-making)
7. [System Architecture](#system-architecture)
8. [Technology Stack](#technology-stack)
9. [Backend Architecture](#backend-architecture)
10. [Frontend Architecture](#frontend-architecture)
11. [Database](#database)
12. [Razorpay Integration](#razorpay-integration)
13. [Webhook Architecture](#webhook-architecture)
14. [Security](#security)
15. [Synthetic Data](#synthetic-data)
16. [Testing](#testing)
17. [Installation and Local Setup](#installation-and-local-setup)
18. [Environment Variables](#environment-variables)
19. [Running the Application](#running-the-application)
20. [API Documentation](#api-documentation)
21. [Project Structure](#project-structure)
22. [Example Recovery Scenario](#example-recovery-scenario)
23. [Current Limitations](#current-limitations)
24. [Future Enhancements](#future-enhancements)
25. [Screenshots](#screenshots)
26. [Project Highlights](#project-highlights)

---

## Overview

Merchants lose revenue every day to failed payments and abandoned checkouts. RecoverAI ingests merchant payment and checkout events, automatically detects revenue-at-risk situations, and runs an AI-powered recovery agent for each case.

The agent — built with LangGraph and Google Gemini — investigates each case by examining customer history, payment history, failure reasons, and previous recovery attempts. It then makes a structured decision: recover, wait, or stop. A deterministic policy gate validates every AI decision before execution. When recovery is warranted, the system creates a Razorpay Payment Link in Test Mode, simulates sending it to the customer, and tracks the case status until the webhook confirms payment or the case is resolved.

Merchants see everything in a real-time dashboard: KPI cards, a customer risk list, AI recommendations with confidence scores and reasoning, payment history, and a full chronological audit trail for every case.

---

## Problem Statement

**Failed payments and checkout abandonments** represent a significant portion of recoverable revenue for online merchants:

- A customer's card is declined due to a temporary bank error. Without automated detection, the merchant never retries the transaction.
- A customer abandons checkout at the payment step. Without recovery, that revenue is permanently lost.
- A subscription payment fails silently. The merchant's team manually reviews logs days later — too late to recover.

**Manual recovery is inefficient:**

- Deciding which customers to contact, when to retry, and which method to use requires analysing payment history, failure types, and customer value — a task that doesn't scale manually.
- Blindly retrying every failed payment risks annoying good customers or wasting effort on non-recoverable cases (cancelled orders, fraud, repeated failures).

**The need for intelligent, policy-aware recovery:**

- Recovery decisions need to be data-driven: a customer with eight prior successful payments and a one-off network error is a different case from a customer with four consecutive failures.
- Any AI-powered decision must be validated by a deterministic safety layer before execution — the model should never be the final authority on whether real actions are taken.

---

## Solution

RecoverAI addresses these problems through a structured, automated pipeline:

**Event ingestion and risk detection** — Merchants send checkout and payment events to the `/api/events` endpoint. The `RevenueRiskDetector` evaluates each event and opens a `RecoveryCase` when revenue is at risk (payment failure, checkout abandonment, subscription failure). Detection is idempotent — duplicate events are safely rejected.

**AI investigation** — When a merchant triggers recovery for a case, the LangGraph agent gathers:
- Customer history: total orders, successful and failed payments, payment success rate, recent failure reasons
- Payment history: all attempts for the order, their statuses and failure reasons
- Order history: recent order statuses for the customer
- Previous recovery attempts: how many times recovery has been attempted on this case
- Case context: case type, risk amount, failure reason, detected-at timestamp

This structured context is assembled and sent to Google Gemini with a system prompt that defines allowed decisions, action selection guidance, and evidence requirements.

**Structured AI decision** — Gemini returns a `RecoveryDecision` with `decision` (RECOVER / WAIT / STOP), `action` (RETRY_PAYMENT / SEND_PAYMENT_LINK / SEND_REMINDER / WAIT / STOP), `confidence` (0.0–1.0), `reason`, and `evidence` list. Pydantic validation enforces the schema and cross-field constraints before any action is taken.

**Policy gate** — A deterministic safety layer (`recovery_policy.py`) evaluates the AI decision against seven rules — in order: order already paid, order cancelled, case in terminal status, maximum attempts reached, invalid action for decision, action not in allowed set, pass through. The policy can override the AI decision to STOP or WAIT. No action is executed if the policy rejects it.

**Recovery action execution** — When policy allows, the executor creates a Razorpay Payment Link in Test Mode (for RETRY_PAYMENT and SEND_PAYMENT_LINK actions). The link URL and payment link ID are returned. The payment link ID is persisted on the `Payment` record for webhook correlation.

**Simulated customer notification** — After a payment link is created, RecoverAI simulates sending it to the customer by resolving their email or phone from the database and recording a `PAYMENT_LINK_SENT` audit entry with the contact details and link URL. No real email, SMS, or WhatsApp message is sent.

**Webhook-driven state update** — When the customer pays via the Razorpay Test Mode link, Razorpay delivers a `payment_link.paid` webhook. The webhook handler verifies the HMAC signature, enforces idempotency, resolves the `Payment` record via `razorpay_payment_link_id`, marks it as SUCCESS, and updates the related `RecoveryCase` to RECOVERED with the recovered amount.

---

## Key Features

- **Merchant dashboard** — Real-time KPI cards showing revenue at risk, open cases, in-progress cases, and recovered revenue
- **Revenue-at-risk detection** — Automatic detection of PAYMENT_FAILURE, CHECKOUT_ABANDONMENT, and SUBSCRIPTION_FAILURE cases from merchant events
- **Recovery case management** — Full case list with search, filtering by status and type, sort, and pagination
- **Customer and payment history** — Per-case view of all payment attempts, success rate, failure reasons, and previous recovery actions
- **AI-powered recovery recommendations** — Google Gemini produces structured decisions with confidence scores, reasoning, and evidence
- **Deterministic policy gate** — Seven ordered safety rules prevent unsafe recovery actions regardless of AI output
- **Razorpay Test Mode payment links** — Real payment links created via the Razorpay API in Test Mode for RETRY_PAYMENT and SEND_PAYMENT_LINK actions
- **Simulated customer notification** — Payment link sent event recorded in audit trail with customer contact details
- **Success toast notification** — Frontend toast confirms payment link dispatch after successful recovery action
- **Razorpay webhook processing** — Incoming `payment_link.paid` events update payment and case status with HMAC signature verification
- **Recovery status lifecycle** — OPEN → IN_PROGRESS → RECOVERED / NOT_RECOVERED / STOPPED
- **Full audit timeline** — Every agent step, policy check, action taken, notification, and webhook event recorded chronologically per case
- **PostgreSQL persistence** — All entities stored with proper foreign keys, NUMERIC money columns, timezone-aware timestamps, and composite indexes
- **Synthetic dataset** — 100 customers, 341 orders, 348 payments, and 991 checkout events across 12 defined recovery scenarios, with 100 recovery cases including 83 open cases, 39 high-value cases, and 9 recovered cases — for development and testing
- **Automated backend tests** — 192 tests covering models, event processing, risk detection, policy gate, agent graph, action executor, API endpoints, and audit trail

---

## End-to-End Workflow

```
Merchant payment event (PAYMENT_FAILED / CHECKOUT_ABANDONED)
        │
        ▼
POST /api/events
  ├── Idempotency check (external_event_id)
  ├── Resolve / create Customer, Order, Payment
  ├── Apply state transitions
  ├── Persist CheckoutEvent
  └── RevenueRiskDetector.evaluate()
        │
        ▼
RecoveryCase created (status: OPEN)
        │
        ▼
Merchant triggers: POST /api/recovery-cases/{id}/run-agent
        │
        ▼
LangGraph workflow (6 nodes)
  ├── load_case       → load case context from DB
  ├── investigate     → customer history, payment history, order history,
  │                     previous recovery attempts
  ├── analyze         → build context dict → Gemini API
  │                     ← RecoveryDecision (decision, action, confidence,
  │                        reason, evidence)
  ├── policy_gate     → deterministic 7-rule safety check
  │                     → STOP if unsafe, WAIT if ambiguous, ALLOW if valid
  ├── execute_action  → RazorpayTestModeExecutor or SimulatedActionExecutor
  │                     → Razorpay Payment Link created (Test Mode)
  │                     → payment_link_id persisted on Payment record
  │                     → PAYMENT_LINK_SENT audit entry recorded
  └── record_result   → AgentAction saved, RecoveryCase status updated,
                        all AuditLog entries written, AGENT_COMPLETED logged
        │
        ▼
Frontend receives AgentRunResponse
  ├── AI recommendation shown (decision, confidence, action, reason, evidence)
  ├── Payment link displayed as clickable URL
  ├── Notification banner: "Payment link sent to customer"
  └── Toast: "Payment link sent successfully"
        │
        ▼
Customer clicks payment link → pays in Razorpay Test Mode
        │
        ▼
Razorpay delivers payment_link.paid webhook
        │
        ▼
POST /api/webhooks/razorpay
  ├── Verify HMAC signature (X-Razorpay-Signature)
  ├── Idempotency check (X-Razorpay-Event-Id → razorpay_webhook_events)
  ├── Resolve Payment via razorpay_payment_link_id
  ├── Update Payment.status = SUCCESS
  ├── Update RecoveryCase.status = RECOVERED, recovered_amount = paid amount
  ├── Write PAYMENT_RECOVERED audit entry
  └── Commit transaction
        │
        ▼
Merchant dashboard reflects updated case status and recovered revenue
```

---

## AI Decision-Making

### Agent Architecture

The recovery agent is implemented using **LangGraph** — a directed acyclic graph where each node is a pure Python function that receives and returns the `AgentState` TypedDict.

### Agent State

`AgentState` carries all workflow data across nodes:
- Input: `recovery_case_id`
- Case context: type, status, risk amount, currency, IDs, failure reason
- Investigation results: customer history dict, payment history dict, order history dict, previous recovery attempts dict
- AI decision: proposed decision, action, confidence, reason, evidence
- Policy result: allowed flag, final decision, final action, override flag
- Action result: execution outcome dict
- Persistence: agent action ID
- Audit: accumulated event list, error list, completion flag

No ORM objects travel through state — only plain Python types and dicts, making state JSON-serialisable across node boundaries.

### Graph Nodes

| Node | Responsibility |
|------|---------------|
| `load_case` | Loads case context via `RecoveryTools.get_recovery_case()`. Adds `AGENT_STARTED` and `CASE_LOADED` audit events. |
| `investigate_case` | Calls all five `RecoveryTools` methods: customer history, payment history, order history, previous recovery attempts, current order status. Adds retrieval audit events. |
| `analyze` | Assembles a structured case context dict and calls `GeminiService.request_recovery_decision()`. Adds `DECISION_MADE` audit event. On Gemini error, defaults to WAIT. |
| `policy_gate` | Calls `recovery_policy.evaluate()` with investigation results. Adds `POLICY_CHECKED` audit event. Routes to `execute_action` if allowed, `record_result` otherwise. |
| `execute_action` | Calls the selected executor (Razorpay or simulated). Adds action-specific audit events. Resolves customer contact and adds `PAYMENT_LINK_SENT` audit event for payment link actions. |
| `record_result` | Persists `AgentAction`, updates `RecoveryCase` status, writes all accumulated `AuditLog` rows, adds `AGENT_COMPLETED` entry. |

### Conditional Routing

- After `load_case`: routes to `investigate_case` or `END` if an error was encountered early
- After `policy_gate`: routes to `execute_action` (allowed) or `record_result` (blocked)

### Recovery Decision Generation

`GeminiService` calls the `google-generativeai` SDK with:
- System prompt defining decision/action taxonomy and evidence requirements
- Case context as JSON in the user message
- `response_mime_type="application/json"` and `response_schema=RecoveryDecision` for structured output
- `temperature=0.1` for deterministic decisions
- `max_output_tokens=512`

The response is validated with Pydantic. Action must be consistent with decision (`@field_validator` enforces cross-field constraint). Invalid responses raise `GeminiParseError` and the agent defaults to WAIT.

### Policy Gate Rules (in order)

| Rule | Condition | Outcome |
|------|-----------|---------|
| R1 | Order already has a successful payment | STOP |
| R2 | Order status is CANCELLED | STOP |
| R3 | Case is in terminal status (RECOVERED / NOT_RECOVERED / STOPPED) | STOP |
| R4 | Previous recovery attempts ≥ MAX_RECOVERY_ATTEMPTS (default: 2) | STOP |
| R5 | RECOVER decision with action not in allowed set | WAIT |
| R6 | Action not permitted for the given decision | STOP |
| R7 | All checks pass | Allow |

`MAX_RECOVERY_ATTEMPTS` is configurable via environment variable.

---

## System Architecture

```mermaid
graph TB
    subgraph Frontend["Frontend (React + Vite)"]
        UI[Dashboard UI]
        API_SVC[api.js service layer]
    end

    subgraph Backend["Backend (FastAPI + Python)"]
        ROUTES[API Routes]
        EVT[Event Processor]
        RISK[Revenue Risk Detector]
        AGENT[Recovery Agent]
        GRAPH[LangGraph Graph]
        POLICY[Policy Gate]
        EXEC[Razorpay Executor / Simulated Executor]
        TOOLS[Recovery Tools]
        WEBHOOK[Webhook Handler]
    end

    subgraph AI["AI Layer"]
        GEMINI[Google Gemini API]
    end

    subgraph Payments["Payment Infrastructure"]
        RZPAY[Razorpay Test Mode API]
        RZWH[Razorpay Webhook Delivery]
    end

    subgraph Database["PostgreSQL"]
        DB[(PostgreSQL)]
        ORM[SQLAlchemy ORM]
        MIG[Alembic Migrations]
    end

    subgraph Tunnel["Public Webhook Tunnel"]
        ZROK[zrok tunnel]
    end

    UI -->|HTTP REST| API_SVC
    API_SVC -->|HTTP| ROUTES
    ROUTES --> EVT
    ROUTES --> AGENT
    ROUTES --> WEBHOOK
    EVT --> RISK
    RISK --> DB
    AGENT --> GRAPH
    GRAPH --> TOOLS
    GRAPH --> POLICY
    GRAPH --> EXEC
    TOOLS --> ORM
    ORM --> DB
    EXEC --> RZPAY
    GRAPH --> GEMINI
    RZWH -->|HTTPS| ZROK
    ZROK -->|localhost:8000| WEBHOOK
    WEBHOOK --> ORM
    MIG --> DB
```

---

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.13 | Backend language |
| **FastAPI** | 0.141.1 | REST API framework |
| **Uvicorn** | 0.52.4 | ASGI server |
| **SQLAlchemy** | 2.0.52 | ORM, query builder, connection pooling |
| **Alembic** | 1.19.1 | Database schema migrations |
| **PostgreSQL** | 17 | Primary relational database (via Docker) |
| **psycopg** | 3.3.4 | PostgreSQL driver (psycopg3) |
| **Pydantic** | 2.13.4 | Request/response validation, structured AI output schema |
| **LangGraph** | 0.3.21 | Agent workflow orchestration (directed graph) |
| **google-generativeai** | 0.8.3 | Google Gemini API client |
| **razorpay** (Python SDK) | — | Razorpay payment link creation and webhook verification |
| **python-dotenv** | 1.2.3 | Environment variable loading |
| **pytest** | 9.1.1 | Backend test framework |
| **React** | 19.2.8 | Frontend UI library |
| **Vite** | 8.2.2 | Frontend build tool and dev server |
| **Tailwind CSS** | 3.4.17 | Utility-first CSS framework |
| **Docker** | — | PostgreSQL containerisation |
| **zrok** | — | Public HTTPS tunnel for Razorpay webhook delivery to localhost |

---

## Backend Architecture

### Directory Structure

```
backend/
├── app/
│   ├── agents/
│   │   ├── graph.py           # LangGraph 6-node workflow
│   │   ├── recovery_agent.py  # High-level agent entry point
│   │   └── state.py           # AgentState TypedDict
│   ├── api/
│   │   └── routes/
│   │       ├── agent.py           # POST /api/recovery-cases/{id}/run-agent
│   │       ├── audit.py           # GET /api/recovery-cases/{id}/audit
│   │       ├── dashboard.py       # GET /api/dashboard/summary
│   │       ├── events.py          # POST /api/events
│   │       ├── health.py          # GET /health
│   │       ├── razorpay_webhook.py # POST /api/webhooks/razorpay
│   │       └── recovery_cases.py  # GET /api/recovery-cases[/{id}][/customer-history]
│   ├── database/
│   │   ├── __init__.py        # Engine, SessionLocal, Base
│   │   └── dependencies.py    # get_db() FastAPI dependency
│   ├── models/                # SQLAlchemy ORM models
│   ├── schemas/               # Pydantic request/response schemas
│   ├── services/
│   │   ├── action_executor.py    # SimulatedActionExecutor
│   │   ├── event_processor.py    # Event ingestion service
│   │   ├── executionModels.py    # ExecutionResult dataclass
│   │   ├── gemini_service.py     # Google Gemini API wrapper
│   │   ├── razorpay_executor.py  # RazorpayTestModeExecutor
│   │   ├── razorpay_service.py   # Razorpay SDK wrapper
│   │   ├── recovery_policy.py    # Deterministic policy gate
│   │   └── revenue_risk.py       # RevenueRiskDetector
│   ├── tools/
│   │   └── recovery_tools.py  # Read-only agent investigation tools
│   ├── config.py              # Environment variable loading
│   └── main.py                # FastAPI app factory
├── alembic/                   # Migration scripts
├── tests/                     # pytest test suite
└── requirements.txt
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `GET` | `/api/dashboard/summary` | Aggregated KPI metrics: revenue at risk, case counts, recovered revenue |
| `POST` | `/api/events` | Ingest a merchant event; returns revenue-at-risk detection result |
| `GET` | `/api/recovery-cases` | List recovery cases with optional `?status=`, `?type=`, `?limit=`, `?offset=` filters |
| `GET` | `/api/recovery-cases/{case_id}` | Full case detail with customer, order, and payment context |
| `GET` | `/api/recovery-cases/{case_id}/customer-history` | Aggregated payment metrics and payment list for the case's customer |
| `GET` | `/api/recovery-cases/{case_id}/audit` | Chronological audit log for a case |
| `POST` | `/api/recovery-cases/{case_id}/run-agent` | Trigger the LangGraph + Gemini recovery agent for a case |
| `POST` | `/api/webhooks/razorpay` | Receive and process Razorpay `payment_link.paid` webhook events |

### Executor Selection

At startup, `backend/app/services/__init__.py` reads `USE_RAZORPAY_TEST_MODE`:
- `true` → `RazorpayTestModeExecutor` (creates real Razorpay Test Mode payment links)
- `false` (default) → `SimulatedActionExecutor` (in-memory simulation, no external calls)

---

## Frontend Architecture

The frontend is a single-page React application built with Vite and styled with Tailwind CSS. All backend communication is handled through the `src/services/api.js` module, which reads `VITE_API_BASE_URL` (defaults to `http://localhost:8000`).

### Dashboard Sections

**Summary cards (top)** — Four KPI cards showing revenue at risk, open cases, in-progress cases, and recovered revenue. Values are fetched from `GET /api/dashboard/summary`.

**Customer risk list (left panel)** — Always-visible sidebar with search, status/type filters, sort options, and pagination. Each row shows customer avatar, name, case type, risk amount, status badge, and detection date. Clicking a row loads the detail panel.

**Case detail (right panel)** — Displays when a case is selected:
- Customer header with name, email, customer ID, and status badge
- Quick facts strip: at-risk amount, failure reason, case type, payment success rate
- AI Recommendation card: shows RECOVER / WAIT / STOP decision in large text, confidence percentage badge, recommended action, reasoning, and collapsible evidence factors
- Payment History card: stats row with total payments, success rate, failed payments; scrollable list of all payment attempts with date, amount, failure reason, and status badge
- Next Action card (right column): start recovery button with risk amount; shows payment link as a clickable highlighted URL after recovery
- Simulated notification banner: blue card confirming the customer's email/contact was notified with the payment link
- Audit Timeline (right column): full chronological event list with time, colour-coded dots per event type, and expand/collapse toggle for cases with many events

**Toast notification** — Top-right success toast appears after a payment link is successfully created and sent. Auto-dismisses after 5.5 seconds.

### Key Components

| Component | Purpose |
|-----------|---------|
| `App.jsx` | Root — state management, API orchestration, layout |
| `SummaryCards.jsx` | KPI metric cards |
| `CaseList.jsx` | Customer risk list with search, filters, pagination |
| `CaseDetail.jsx` | Full case detail panel (header, facts strip, two-column body) |
| `AgentPanel.jsx` | AI recommendation, payment link display, notification banner |
| `AuditTrail.jsx` | Full audit timeline with expand/collapse |
| `StatusBadge.jsx` | Coloured status chip for case and payment statuses |
| `SimulatedBadge.jsx` | "DEMO" badge indicating simulated/test-mode actions |
| `Toast.jsx` | Portal-rendered success toast notification |

---

## Database

RecoverAI uses PostgreSQL 17 managed via Docker. The ORM layer is SQLAlchemy 2.x with the modern `DeclarativeBase` style. Schema is managed by Alembic — four migrations are applied in order.

### Entity Relationships

```
Customer
  ├── Order (1:N)
  │     ├── Payment (1:N)
  │     │     └── RecoveryCase (1:N via payment_id, nullable)
  │     ├── CheckoutEvent (1:N)
  │     └── RecoveryCase (1:N via order_id)
  ├── Payment (1:N via customer_id)
  └── RecoveryCase (1:N via customer_id)

RecoveryCase
  ├── AgentAction (1:N)
  └── AuditLog (1:N)

AgentAction
  └── AuditLog (1:N via agent_action_id)

RazorpayWebhookEvent (standalone — idempotency store)
```

### Database Tables

| Table | Description |
|-------|-------------|
| `customers` | Merchant customers: `external_customer_id`, `name`, `email`, `phone` |
| `orders` | Purchase orders: `external_order_id`, amount, currency, status |
| `payments` | Payment attempts: amount, status, `failure_reason`, `payment_method`, `razorpay_payment_link_id` |
| `checkout_events` | Funnel events: `CHECKOUT_STARTED`, `CHECKOUT_ABANDONED`, `PAYMENT_INITIATED`, `PAYMENT_SUCCESS`, `PAYMENT_FAILED` |
| `recovery_cases` | Revenue-at-risk cases: `case_type`, `status`, `risk_amount`, `recovered_amount`, `detected_at`, `resolved_at` |
| `agent_actions` | AI agent decisions and results: `action_type`, `status`, `reason`, `result` (JSON) |
| `audit_logs` | Immutable event log: `event_type`, `actor`, `details` (JSON), `created_at` |
| `razorpay_webhook_events` | Processed Razorpay event IDs for idempotency |

### Design Decisions

- All monetary columns use `NUMERIC(12, 2)` — never `FLOAT`
- All timestamps are timezone-aware (`DateTime(timezone=True)`)
- Composite indexes on frequent agent query patterns (e.g. `(customer_id, status)`, `(recovery_case_id, created_at)`)
- `external_payment_id` and `external_customer_id` have unique constraints
- `razorpay_payment_link_id` on `payments` is the webhook correlation key

### Alembic Migrations

| Migration | Description |
|-----------|-------------|
| `d54d61ae25c7` | Initial domain models: all 7 core tables |
| `1d8457647d64` | Add `recovered_amount` to `recovery_cases` |
| `829f2397b62e` | Add `razorpay_webhook_events` table |
| `f746b2772cc0` | Add `razorpay_payment_link_id` to `payments` |

---

## Razorpay Integration

RecoverAI integrates with **Razorpay Test Mode** — no real customer money is ever processed. Test Mode allows end-to-end testing of the full payment link → payment → webhook → recovery flow without financial transactions.

### Credentials

Three credentials are required (all Test Mode):

| Variable | Purpose |
|----------|---------|
| `RAZORPAY_KEY_ID` | Test Mode API key ID (`rzp_test_...`) |
| `RAZORPAY_KEY_SECRET` | Test Mode API key secret |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook signature verification secret |

### Payment Link Creation

`RazorpayService.create_payment_link()` builds a payment link payload with:
- Amount in paise (₹ × 100), currency INR
- `reference_id` set to `case-{case_id}` for traceability
- `notes` containing `case_id` and `reference_id`
- `description` identifying the RecoverAI case
- Optional `customer` dict (name, email, phone) when available
- `reminder_enable: true`

The response provides `id` (payment link ID) and `short_url`. Both are returned in `ExecutionResult` and stored on the `Payment` record.

### Payment Link ID Persistence

After a payment link is created, the `record_result` graph node stores `payment_link_id` in `Payment.razorpay_payment_link_id`. This field is the **correlation key** that the webhook handler uses to find the correct `Payment` and associated `RecoveryCase` when Razorpay delivers the paid event.

### Executor Selection

`USE_RAZORPAY_TEST_MODE=true` in `backend/.env` activates `RazorpayTestModeExecutor`. Both `RETRY_PAYMENT` and `SEND_PAYMENT_LINK` actions create real Razorpay Test Mode payment links. `SEND_REMINDER`, `WAIT`, and `STOP` remain simulated.

When `USE_RAZORPAY_TEST_MODE` is `false` (default), `SimulatedActionExecutor` handles all actions locally without any external API calls.

---

## Webhook Architecture

```
Razorpay Test Mode dashboard
        │ HTTPS POST (payment_link.paid)
        ▼
zrok public tunnel (e.g. https://<subdomain>.zrok.io)
        │ forwards to
        ▼
localhost:8000/api/webhooks/razorpay
        │
        ├── 1. Read raw body (required for HMAC verification)
        ├── 2. Verify X-Razorpay-Signature using RAZORPAY_WEBHOOK_SECRET
        ├── 3. Check X-Razorpay-Event-Id against razorpay_webhook_events (idempotency)
        ├── 4. Parse JSON payload
        ├── 5. Extract payment_link.entity.id
        ├── 6. Find Payment by razorpay_payment_link_id
        ├── 7. Update Payment.status = SUCCESS
        ├── 8. Find active RecoveryCase(s) via payment_id
        ├── 9. Update RecoveryCase.status = RECOVERED, recovered_amount = paid amount
        ├── 10. Write PAYMENT_RECOVERED AuditLog entry
        └── 11. Commit transaction
```

### Setting Up the Webhook Tunnel

1. Install [zrok](https://zrok.io/) and authenticate
2. Start your FastAPI backend on port 8000
3. Create a public tunnel:
   ```
   zrok share public localhost:8000
   ```
4. Copy the generated HTTPS URL (e.g. `https://abc123.share.zrok.io`)
5. In the Razorpay Test Mode dashboard → Webhooks, add a new webhook:
   - URL: `https://abc123.share.zrok.io/api/webhooks/razorpay`
   - Events: `payment_link.paid`
   - Secret: matches `RAZORPAY_WEBHOOK_SECRET` in `backend/.env`

---

## Security

- **No hardcoded credentials** — all secrets (`DATABASE_URL`, `GEMINI_API_KEY`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`) are read from `backend/.env` via `python-dotenv`. The file is never committed.
- **Webhook HMAC verification** — the Razorpay webhook endpoint verifies `X-Razorpay-Signature` using the webhook secret before parsing the JSON body. Invalid signatures return `HTTP 400`.
- **Webhook idempotency** — `X-Razorpay-Event-Id` is stored in `razorpay_webhook_events` with a unique primary key constraint. Duplicate deliveries are detected and rejected before any state is modified. A DB-level `IntegrityError` on concurrent duplicates is handled as a safe no-op.
- **AI output validation** — Gemini responses are validated by Pydantic before any action is taken. The policy gate provides a second deterministic validation layer.
- **Read-only investigation tools** — `RecoveryTools` methods are explicitly read-only. No INSERT, UPDATE, or DELETE operations can be triggered by the LLM through these tools.
- **Key safety in logs** — `GeminiService` logs only the first 4 characters of the API key as a visibility marker. Full keys are never logged or returned in API responses.
- **CORS** — The FastAPI CORS middleware allows only `http://localhost:5173` and `http://127.0.0.1:5173` (Vite dev server) for cross-origin requests.

> **Note:** RecoverAI does not implement authentication or login/logout. It is designed as a merchant-facing operations tool where access control is handled at the infrastructure layer.

---

## Synthetic Data

The `data/synthetic/` module generates a realistic fictional merchant dataset for development and testing. No real customer names, emails, or payment data are used.

### Why It Exists

The synthetic dataset provides a populated database from the first run, allowing:
- Immediate demonstration of the full recovery pipeline without requiring real merchant events
- Consistent, deterministic test data for automated tests
- Realistic scenario coverage across 12 defined recovery archetypes

### What It Generates

The generator (`scenarios.py`, seeded with `random.Random(seed=42)`) creates:
- **100 customers** with names, emails, and phone numbers
- **341 orders** with realistic amounts in INR
- **348 payments** (mix of SUCCESS and FAILED) with failure reasons and payment methods — including 249 successful payments and 99 payment failures
- **991 checkout events** in chronological funnel order, including 28 checkout abandonments
- **100 recovery cases** across all statuses — 83 open, 9 recovered, and 39 high-value cases (≥ ₹10,000)

### Scenario Catalogue

| Scenario | Description | Recovery Outlook |
|----------|-------------|-----------------|
| S01 | Loyal customer, one-off failure (5–8 prior successes) | Recoverable |
| S02 | New customer, first payment fails | Recoverable |
| S03 | Repeated failures (3–4 consecutive) | Low probability |
| S04 | Clean checkout abandonment | Recoverable |
| S05 | Payment fails then customer abandons | Recoverable |
| S06 | High-value order (≥ ₹10,000) fails | High-priority recovery |
| S07 | Subscription/recurring payment fails | Recoverable |
| S08 | Failure then self-recovered | Not at risk |
| S09 | Order cancelled by customer | Not recoverable |
| S10 | Stale abandonment (60–90 days ago) | Low probability |
| S11 | Mixed history (successes + failures) | Baseline |
| S12 | Purely successful — no risk | Control group |

### Seed Commands

All commands run from the project root:

```bash
# Seed the database (idempotent — safe to run multiple times)
backend\venv\Scripts\python.exe -m data.synthetic.seed_data

# Reset and reseed (clears all rows first)
backend\venv\Scripts\python.exe -m data.synthetic.seed_data --reset

# Verify record counts without inserting
backend\venv\Scripts\python.exe -m data.synthetic.seed_data --verify
```

---

## Testing

RecoverAI uses **pytest** for backend testing. Tests run against a real PostgreSQL database using the configured `DATABASE_URL`.

### Test Files

| File | Coverage |
|------|----------|
| `test_db_connection.py` | Database connectivity |
| `test_models.py` | ORM model instantiation and constraints |
| `test_synthetic_data.py` | Seed data counts, FK integrity, uniqueness, scenario coverage, generator determinism |
| `test_stage4.py` | `RevenueRiskDetector` unit tests, event API integration, idempotency, recovery case API |
| `test_stage5.py` | `RecoveryTools`, policy gate, `SimulatedActionExecutor`, end-to-end agent graph (mocked Gemini), API layer, audit persistence |
| `test_stage6.py` | Dashboard summary API, audit trail API, case list regression |
| `test_stage7.py` | Simulation outcomes (SUCCESS → RECOVERED, FAILURE → NOT_RECOVERED, WAIT → IN_PROGRESS), dashboard recovered revenue, idempotency on resolved cases |
| `test_gemini_service.py` | GeminiService schema and error handling |
| `test_customer_history_api.py` | Customer history endpoint |
| `test_health.py` | Health check endpoint |

### Running Tests

```bash
# Run all tests
backend\venv\Scripts\python.exe -m pytest backend/tests/ -v

# Run a specific stage
backend\venv\Scripts\python.exe -m pytest backend/tests/test_stage5.py -v

# Run with summary
backend\venv\Scripts\python.exe -m pytest backend/tests/ -q
```

The verified test result across the full test suite: **192 passed, 4 warnings**.

---

## Installation and Local Setup

### Prerequisites

- Python 3.13
- Node.js 18+ and npm
- Docker Desktop (for PostgreSQL)
- A Razorpay Test Mode account (free) — for payment link and webhook features
- A Google Gemini API key — for AI recovery decisions
- [zrok](https://zrok.io/) — for receiving Razorpay webhooks on localhost

### 1. Clone the Repository

```bash
git clone <repository-url>
cd RecoverAI
```

### 2. Start PostgreSQL

```bash
docker compose up -d db
```

This starts a PostgreSQL 17 container named `recoverai_postgres` on port 5432, with database `recoverai`, user `recoverai_user`, password `recoverai_password`.

### 3. Create the Python Virtual Environment

```bash
cd backend
python -m venv venv
```

### 4. Install Backend Dependencies

```bash
# Windows
backend\venv\Scripts\pip.exe install -r backend\requirements.txt

# macOS/Linux
backend/venv/bin/pip install -r backend/requirements.txt
```

### 5. Configure Environment Variables

Create `backend/.env` (see [Environment Variables](#environment-variables) section):

```bash
copy backend\.env.example backend\.env   # Windows
# or
cp backend/.env.example backend/.env     # macOS/Linux
```

Edit `backend/.env` and fill in all required values.

### 6. Run Database Migrations

From the project root:

```bash
backend\venv\Scripts\alembic.exe -c backend\alembic.ini upgrade head
```

### 7. Seed Synthetic Data

```bash
backend\venv\Scripts\python.exe -m data.synthetic.seed_data
```

### 8. Install Frontend Dependencies

```bash
cd frontend
npm install
```

### 9. Configure Frontend Environment

Create `frontend/.env`:

```
VITE_API_BASE_URL=http://localhost:8000
```

### 10. Razorpay Test Mode Setup

1. Create a free account at [razorpay.com](https://razorpay.com)
2. Navigate to Settings → API Keys → Test Mode → Generate Key
3. Copy the Key ID and Key Secret into `backend/.env`
4. Navigate to Settings → Webhooks → Add New Webhook (configure after setting up zrok — see step 11)
5. Set `USE_RAZORPAY_TEST_MODE=true` in `backend/.env`

### 11. Webhook Tunnel Setup (zrok)

1. Download and install zrok from [zrok.io](https://zrok.io)
2. Authenticate: `zrok enable <your-token>`
3. After starting the backend, run: `zrok share public localhost:8000`
4. Copy the generated HTTPS URL
5. In Razorpay Test Mode → Webhooks, add:
   - URL: `<zrok-url>/api/webhooks/razorpay`
   - Active events: `payment_link.paid`
   - Secret: your `RAZORPAY_WEBHOOK_SECRET` value

---

## Environment Variables

Create `backend/.env` with the following variables. Never commit this file.

```env
# ── Database ─────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+psycopg://recoverai_user:recoverai_password@localhost:5432/recoverai

# ── Google Gemini ─────────────────────────────────────────────────────────
GEMINI_API_KEY=<your_gemini_api_key>
AGENT_MODEL=gemini-3.5-flash-lite   # or gemini-1.5-flash etc.

# ── Razorpay ─────────────────────────────────────────────────────────────
USE_RAZORPAY_TEST_MODE=true
RAZORPAY_KEY_ID=<your_test_key_id>
RAZORPAY_KEY_SECRET=<your_test_key_secret>
RAZORPAY_WEBHOOK_SECRET=<your_webhook_secret>

# ── Recovery Policy ───────────────────────────────────────────────────────
MAX_RECOVERY_ATTEMPTS=2
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `AGENT_MODEL` | No | Gemini model name (default: `gemini-3.5-flash-lite`) |
| `USE_RAZORPAY_TEST_MODE` | No | Enable Razorpay Test Mode executor (default: `false`) |
| `RAZORPAY_KEY_ID` | If Razorpay enabled | Test Mode API Key ID |
| `RAZORPAY_KEY_SECRET` | If Razorpay enabled | Test Mode API Key Secret |
| `RAZORPAY_WEBHOOK_SECRET` | If Razorpay enabled | Webhook HMAC secret |
| `MAX_RECOVERY_ATTEMPTS` | No | Maximum agent runs per case (default: `2`) |

---

## Running the Application

### Start the Backend

```bash
# From the project root
backend\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

Backend available at: `http://localhost:8000`

### Start the Frontend

```bash
cd frontend
npm run dev
```

Frontend available at: `http://localhost:5173`

### Start the Webhook Tunnel (when using Razorpay)

```bash
zrok share public localhost:8000
```

### Verify Everything Is Running

```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

---

## API Documentation

FastAPI automatically generates interactive API documentation when the backend is running:

| Documentation | URL |
|---------------|-----|
| Swagger UI (interactive) | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |
| OpenAPI JSON | `http://localhost:8000/openapi.json` |

Visiting `http://localhost:8000/` redirects to `/docs` automatically.

---

## Project Structure

```
RecoverAI/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── graph.py            # LangGraph 6-node recovery workflow
│   │   │   ├── recovery_agent.py   # Agent entry point and orchestration
│   │   │   └── state.py            # AgentState TypedDict
│   │   ├── api/routes/
│   │   │   ├── agent.py            # POST /api/recovery-cases/{id}/run-agent
│   │   │   ├── audit.py            # GET /api/recovery-cases/{id}/audit
│   │   │   ├── dashboard.py        # GET /api/dashboard/summary
│   │   │   ├── events.py           # POST /api/events
│   │   │   ├── health.py           # GET /health
│   │   │   ├── razorpay_webhook.py # POST /api/webhooks/razorpay
│   │   │   └── recovery_cases.py   # GET /api/recovery-cases[/{id}]
│   │   ├── database/
│   │   │   ├── __init__.py         # Engine, SessionLocal, Base
│   │   │   └── dependencies.py     # get_db() dependency
│   │   ├── models/
│   │   │   ├── agent_action.py     # AgentAction ORM model
│   │   │   ├── audit_log.py        # AuditLog ORM model
│   │   │   ├── checkout_event.py   # CheckoutEvent ORM model
│   │   │   ├── customer.py         # Customer ORM model
│   │   │   ├── order.py            # Order ORM model
│   │   │   ├── payment.py          # Payment ORM model (incl. payment_link_id)
│   │   │   ├── razorpay_webhook_event.py # Webhook idempotency store
│   │   │   └── recovery_case.py    # RecoveryCase ORM model
│   │   ├── schemas/
│   │   │   ├── event.py            # EventRequest / EventResponse
│   │   │   ├── recovery_agent.py   # RecoveryDecision / AgentRunResponse
│   │   │   └── revenue_risk.py     # Case list / detail schemas
│   │   ├── services/
│   │   │   ├── action_executor.py  # SimulatedActionExecutor
│   │   │   ├── event_processor.py  # Event ingestion and entity resolution
│   │   │   ├── executionModels.py  # ExecutionResult dataclass
│   │   │   ├── gemini_service.py   # Google Gemini API wrapper
│   │   │   ├── razorpay_executor.py # RazorpayTestModeExecutor
│   │   │   ├── razorpay_service.py # Razorpay SDK wrapper
│   │   │   ├── recovery_policy.py  # Deterministic policy gate
│   │   │   └── revenue_risk.py     # RevenueRiskDetector
│   │   ├── tools/
│   │   │   └── recovery_tools.py   # Read-only agent investigation tools
│   │   ├── config.py               # Environment variable loading
│   │   └── main.py                 # FastAPI app factory + router registration
│   ├── alembic/
│   │   └── versions/               # 4 migration scripts
│   ├── tests/                      # pytest test suite (10 files)
│   ├── requirements.txt
│   └── alembic.ini
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── AgentPanel.jsx      # AI recommendation + payment link display
│   │   │   ├── AuditTrail.jsx      # Full audit timeline
│   │   │   ├── CaseDetail.jsx      # Case header, facts, two-column body
│   │   │   ├── CaseList.jsx        # Customer risk list with filters/pagination
│   │   │   ├── SimulatedBadge.jsx  # DEMO badge
│   │   │   ├── StatusBadge.jsx     # Coloured status chip
│   │   │   ├── SummaryCards.jsx    # KPI cards
│   │   │   └── Toast.jsx           # Success toast notification
│   │   ├── services/
│   │   │   └── api.js              # All backend HTTP calls
│   │   ├── App.jsx                 # Root component and state management
│   │   ├── config.js               # IS_SIMULATED flag
│   │   ├── index.css               # Tailwind + custom utilities
│   │   └── main.jsx                # React entry point
│   ├── package.json
│   └── vite.config.js
├── data/
│   └── synthetic/
│       ├── scenarios.py            # Pure data generation (12 scenarios)
│       ├── seed_data.py            # Database seeder CLI
│       └── README.md
├── alembic/                        # Root-level alembic (same migrations)
│   └── versions/
├── docker-compose.yml              # PostgreSQL 17 container
└── README.md
```

---

## Example Recovery Scenario

> This is an illustrative example using fictional data.

**Customer:** Kavya Pandey (`cust0056@example.com`)  
**Order:** ORD-2026-08-KP, ₹25,000  
**Event sequence:**

1. `CHECKOUT_STARTED` → order created
2. `PAYMENT_INITIATED` → payment attempted via CARD
3. `PAYMENT_FAILED` → `failure_reason: insufficient_funds` → **RecoveryCase OPEN, risk ₹25K**

**Merchant triggers recovery** → `POST /api/recovery-cases/42/run-agent`

**Agent investigation finds:**
- Customer has 6 previous successful payments (success rate: 85.7%)
- This is the first failure on this order
- 0 prior recovery attempts for this case
- Order status: FAILED, not cancelled

**Gemini decision:**
```json
{
  "decision": "RECOVER",
  "action": "SEND_PAYMENT_LINK",
  "confidence": 0.88,
  "reason": "Customer has strong payment history with 6 prior successes. Single failure due to insufficient_funds suggests temporary cash-flow issue. Payment link gives customer a convenient retry opportunity.",
  "evidence": [
    "6 previous successful payments",
    "payment success rate: 0.857",
    "failure_reason: insufficient_funds",
    "0 prior recovery attempts"
  ]
}
```

**Policy gate:** all 7 rules pass → ALLOW

**Executor:** `RazorpayTestModeExecutor` creates payment link `plink_XXXX` → URL `https://rzp.io/rzp/XXXX`

**Audit entry added:** `PAYMENT_LINK_SENT` — sent to `cust0056@example.com` (simulated — no real email sent)

**Dashboard shows:**
- AI recommendation: RECOVER / 88% confidence
- Payment link: `https://rzp.io/rzp/XXXX` (clickable)
- Blue notification: "Payment link sent to customer — cust0056@example.com"
- Toast: "Payment link sent successfully"
- Case status: IN_PROGRESS

**Customer pays via Test Mode link**

**Razorpay delivers** `payment_link.paid` webhook → signature verified → `Payment.status = SUCCESS`, `RecoveryCase.status = RECOVERED`, `recovered_amount = ₹25,000`

**Dashboard updates:** case RECOVERED, recovered revenue increases by ₹25,000

---

## Future Enhancements

The following capabilities are not currently implemented and are candidates for future development:

- **Real customer notifications** — Integrate an email provider (SendGrid, AWS SES) and SMS gateway to deliver payment links via real channels
- **Authentication and authorisation** — Add merchant login, API key authentication
- **Production payment infrastructure** — Move from Test Mode to Razorpay Live Mode for real payment processing
- **Scheduled recovery** — Background job scheduler (Celery, APScheduler) to run the agent automatically at configurable intervals after case detection
- **Multi-channel notifications** — WhatsApp Business API, push notifications, in-app messaging
- **Advanced analytics** — Recovery rate trends, A/B testing of recovery strategies, customer lifetime value scoring
- **Multi-merchant support** — Tenant isolation, per-merchant configuration and dashboards
- **Model evaluation framework** — Offline evaluation of AI decision quality against ground truth labels from the synthetic dataset
- **Cloud deployment** — Containerised deployment on AWS/GCP/Azure with managed PostgreSQL and production-grade secrets management
- **Webhook reliability** — Retry queues, dead-letter handling, and webhook replay for missed events
- **Subscription recovery** — Dedicated flow for recurring billing failures with smarter retry scheduling

---

## Project Highlights

- **Structured agent architecture** — LangGraph 6-node directed workflow with typed state, conditional routing, and clean separation between investigation, decision, policy, execution, and persistence
- **AI never acts alone** — Every Gemini decision passes through a deterministic 7-rule policy gate before any action is executed, with full override logging
- **Complete Razorpay payment flow** — End-to-end test-mode payment link creation, payment link ID persistence, HMAC-verified webhook handling, and case status update in a single atomic transaction
- **Idempotency at every layer** — Duplicate merchant events (checked via JSON metadata), duplicate Razorpay webhook deliveries (checked via event ID primary key + DB constraint), and duplicate agent runs on resolved cases all handled safely
- **Append-only audit trail** — Every agent step, policy check, action, notification, and webhook event is written as an immutable `AuditLog` row with actor, timestamp, and structured JSON details
- **192 automated tests** — Comprehensive pytest coverage across models, risk detection, event processing, policy gate, agent graph, API endpoints, simulation outcomes, and synthetic data integrity
- **Realistic synthetic dataset** — 12 defined recovery scenarios covering the full spectrum from loyal customers to repeated failures, deterministically generated with a fixed seed for reproducible testing
- **Monetary correctness** — All money columns use `NUMERIC(12, 2)`, never `FLOAT`. Razorpay's paise-based amounts are converted precisely using `Decimal`
- **Zero frontend build errors** — React 19 + Vite 8 frontend builds cleanly with 26 modules and ships production-ready via `vite build`
