# RecoverAI — Recovery Agent Architecture

## 1. Why RecoverAI Needs an Agent

A simple rule-based system can detect that a payment failed.  
What it cannot do is weigh evidence: a loyal customer whose card timed out once is very different from a customer who has failed four times across three different payment methods.

RecoverAI uses an AI agent to:
- Reason over structured evidence retrieved from PostgreSQL
- Select the most appropriate bounded recovery action
- Explain every decision in human-readable terms
- Respect hard safety rules that the LLM cannot override

---

## 2. How the Agent Retrieves Information

The agent **never constructs SQL**. It calls pre-defined read-only Python tools
backed by typed SQLAlchemy ORM queries.

| Tool | Input | Returns |
|---|---|---|
| `get_recovery_case` | `recovery_case_id` | Case type, status, risk amount, customer/order/payment IDs |
| `get_customer_history` | `customer_id` | Total orders, success rate, recent failure reasons |
| `get_payment_history` | `order_id` | All payment attempts, statuses, failure reasons |
| `get_order_history` | `customer_id` | Recent order statuses |
| `get_previous_recovery_attempts` | `recovery_case_id` | Prior AgentAction records |
| `get_case_context` | `recovery_case_id` | Aggregated JSON of all of the above |

All tools are in `backend/app/tools/recovery_tools.py`.  
Tools are **read-only** — they cannot modify payments, orders, or cases.

---

## 3. Agent State

The LangGraph workflow passes a `TypedDict` state object between nodes.

Key fields:

```
recovery_case_id      — input
case_type             — PAYMENT_FAILURE | CHECKOUT_ABANDONMENT | …
risk_amount           — Decimal as string (JSON-safe)
customer_history      — aggregated dict from tool
payment_history       — aggregated dict from tool
previous_attempt_count — integer count of prior AgentAction rows
proposed_decision     — what Gemini returned
proposed_action       — what Gemini returned
policy_allowed        — result of deterministic policy gate
final_decision        — after policy validation
final_action          — after policy validation
action_result         — ExecutionResult dict (always simulated=True)
agent_action_id       — DB id of the persisted AgentAction
errors                — list of non-fatal errors
audit_events          — list of structured audit entries
completed             — terminal flag
```

No secrets, credentials, or raw payment card data are stored in state.

---

## 4. Agent Tools

See section 2 above. Enforced boundaries:

- **No INSERT/UPDATE/DELETE** in any tool
- **No external API calls** in any tool
- **No arbitrary SQL** — all queries use typed SQLAlchemy expressions
- Tools raise `ValueError` on bad input; the agent catches this and appends to `errors`

---

## 5. Decision Process

```
START
  │
  ▼
load_case          (tool: get_recovery_case)
  │
  ▼
investigate_case   (tools: get_customer_history, get_payment_history,
  │                         get_order_history, get_previous_recovery_attempts)
  ▼
analyze            (Gemini: structured RecoveryDecision JSON)
  │
  ▼
policy_gate        (deterministic Python — no LLM)
  │
  ├── allowed ──→ execute_action  (SimulatedActionExecutor)
  │                    │
  └── rejected ─┐      │
                ▼      ▼
            record_result  (AgentAction + AuditLog + RecoveryCase update)
                 │
                 ▼
               END
```

Gemini is called **exactly once** per workflow run (in the `analyze` node).  
If Gemini fails, the agent defaults to `WAIT` and continues to `record_result`.

---

## 6. Policy Gate

File: `backend/app/services/recovery_policy.py`

The policy gate is **purely deterministic Python** — it receives plain values
(no DB objects, no LLM output) and returns a `PolicyResult`.

| Rule | Condition | Forces |
|---|---|---|
| R1 | Order already has a SUCCESS payment | STOP |
| R2 | Order status is CANCELLED | STOP |
| R3 | Case already in terminal status (RECOVERED / NOT_RECOVERED / STOPPED) | STOP |
| R4 | `previous_attempt_count >= MAX_RECOVERY_ATTEMPTS` | STOP |
| R5 | LLM proposed RECOVER but action not in allowed set | WAIT |
| R6 | Action not valid for the given decision | STOP |
| R7 | All checks pass | Allow LLM decision |

`MAX_RECOVERY_ATTEMPTS` is read from the environment variable of the same name.  
Default: `2`. Override in `backend/.env`.

**The LLM is never the final authority.** Every LLM decision passes through
this gate before any action is executed.

---

## 7. Bounded Action Execution

File: `backend/app/services/action_executor.py`

The executor accepts only actions from a fixed whitelist:

| Action | Description |
|---|---|
| `RETRY_PAYMENT` | Simulates a payment retry at the gateway |
| `SEND_PAYMENT_LINK` | Simulates generating and dispatching a payment link |
| `SEND_REMINDER` | Simulates sending a checkout recovery reminder |
| `WAIT` | No action — agent is waiting |
| `STOP` | No action — recovery halted |

Every result includes `"simulated": true` so no one can mistake it for a real action.

The executor **never calls Razorpay**, sends email/SMS, or accesses any external API.

---

## 8. Audit Trail

Every significant workflow step produces an `AuditLog` row:

| Event | When |
|---|---|
| `AGENT_STARTED` | Workflow begins |
| `CASE_LOADED` | RecoveryCase loaded from DB |
| `CUSTOMER_HISTORY_RETRIEVED` | Customer tool called |
| `PAYMENT_HISTORY_RETRIEVED` | Payment tool called |
| `RECOVERY_ATTEMPTS_RETRIEVED` | Prior attempts loaded |
| `DECISION_MADE` | Gemini returned a decision |
| `POLICY_CHECKED` | Policy gate evaluated |
| `ACTION_SELECTED` | AgentAction record created |
| `ACTION_EXECUTED` | Simulated executor ran |
| `CASE_UPDATED` | RecoveryCase status changed |
| `AGENT_COMPLETED` | Workflow finished |
| `AGENT_ERROR` | Non-fatal error occurred |

The audit trail answers: **What happened? Why? When? What was decided?**

---

## 9. Why Actions Are Currently Simulated

Real payment actions (Razorpay retries, payment links, SMS) require:
- Live Razorpay Test Mode credentials
- Idempotency keys for gateway calls
- Retry/backoff logic for network failures
- Customer consent and communication infrastructure

These are Stage 6+ concerns. The simulation layer lets the full agent workflow
be built, tested, and demonstrated without any external dependencies.

The architecture explicitly isolates the executor so the Razorpay adapter
can replace it with zero changes to the agent, policy, or graph.

---

## 10. Where Razorpay Test Mode Will Connect

```
Current
───────
AI Agent → Policy Gate → ActionExecutor → SimulatedActionExecutor

Stage 6+
────────
AI Agent → Policy Gate → ActionExecutor → RazorpayTestModeExecutor
                                               │
                                               ▼
                                      Razorpay Test Mode API
                                      (payment.create, payment_link.create, …)
```

Only `SimulatedActionExecutor` needs to be replaced.  
The agent, policy gate, tools, state, and graph remain unchanged.

---

## 11. Security Boundaries

- Gemini API key read from `GEMINI_API_KEY` env var — never hardcoded
- LLM cannot execute arbitrary code, SQL, or HTTP requests
- All DB access goes through typed ORM queries in `RecoveryTools`
- Tools are read-only during investigation
- Only `record_result` node writes to the DB (AgentAction, AuditLog, RecoveryCase)
- No PII (phone, card details) is stored in agent state or audit logs

---

## 12. Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL connection string |
| `GEMINI_API_KEY` | — | Google AI Studio API key |
| `AGENT_MODEL` | `gemini-1.5-flash` | Gemini model name |
| `MAX_RECOVERY_ATTEMPTS` | `2` | Max AgentAction rows before STOP |
