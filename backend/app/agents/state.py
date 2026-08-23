"""
backend/app/agents/state.py

LangGraph agent state for the RecoverAI recovery workflow.

AgentState is a TypedDict — LangGraph requires this to track the
mutable workflow state across nodes.

Design rules
────────────
- No ORM objects in state (not serialisable across node boundaries).
- No secrets, API keys, or sensitive credentials.
- No raw card numbers, bank account details, or PII beyond name/email.
- All monetary values are stored as strings (Decimal is not JSON-native).
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """
    Mutable state object passed through every LangGraph node.

    Fields are populated progressively as the workflow advances.
    total=False means all fields are optional at construction time.
    """

    # ── Input ─────────────────────────────────────────────────────────────────
    recovery_case_id: int

    # ── Case context (populated by load_case node) ────────────────────────────
    case_type: str                  # PAYMENT_FAILURE | CHECKOUT_ABANDONMENT | …
    case_status: str                # OPEN | IN_PROGRESS | …
    risk_amount: str                # Decimal as string — JSON-safe
    currency: str
    customer_id: int
    order_id: int
    payment_id: int | None
    failure_reason: str | None

    # ── Investigation results (populated by investigate_case node) ─────────────
    customer_history: dict[str, Any]
    payment_history: dict[str, Any]
    order_history: dict[str, Any]
    previous_recovery_attempts: dict[str, Any]
    order_status: str               # current order status (from order history)
    has_successful_payment: bool    # True if order already paid
    previous_attempt_count: int

    # ── AI decision (populated by analyze node) ───────────────────────────────
    proposed_decision: str          # RECOVER | WAIT | STOP
    proposed_action: str            # specific action from RecoveryDecision
    confidence: float
    decision_reason: str
    evidence: list[str]

    # ── Policy result (populated by policy_gate node) ─────────────────────────
    policy_allowed: bool
    final_decision: str
    final_action: str
    policy_reason: str
    policy_overridden: bool

    # ── Action result (populated by execute_action node) ──────────────────────
    action_result: dict[str, Any]   # ExecutionResult.to_dict()

    # ── Persistence (populated by record_result node) ─────────────────────────
    agent_action_id: int | None

    # ── Errors and audit ──────────────────────────────────────────────────────
    errors: list[str]               # non-fatal errors accumulated during run
    audit_events: list[dict[str, Any]]  # structured audit log entries
    completed: bool                 # True when the workflow has finished
