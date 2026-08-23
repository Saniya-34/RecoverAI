"""
backend/app/services/recovery_policy.py

Deterministic Recovery Policy Gate.

This is the SAFETY LAYER between the LLM decision and action execution.
The LLM proposes a decision; this service validates it.

The LLM is NEVER the final authority on whether an action is executed.

Rules (evaluated in order — first match wins)
─────────────────────────────────────────────
R1  Order already paid               → STOP
R2  Order cancelled                  → STOP
R3  Case already in terminal status  → STOP
R4  Max recovery attempts reached    → STOP
R5  Missing required context         → WAIT
R6  Validate LLM action is allowed   → override to STOP if not
R7  Pass through                     → allow LLM decision

Configuration
─────────────
MAX_RECOVERY_ATTEMPTS is read from the environment.
Default = 2.  Override in backend/.env.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Configurable limit — never hardcoded
_DEFAULT_MAX_ATTEMPTS = 2
MAX_RECOVERY_ATTEMPTS: int = int(
    os.getenv("MAX_RECOVERY_ATTEMPTS", str(_DEFAULT_MAX_ATTEMPTS))
)

# Terminal case statuses — no further agent runs allowed
TERMINAL_STATUSES = frozenset({"RECOVERED", "NOT_RECOVERED", "STOPPED"})

# Order statuses where recovery is pointless
NON_RECOVERABLE_ORDER_STATUSES = frozenset({"CANCELLED", "PAID"})

# Allowed action sets per decision (single source of truth)
DECISION_ACTION_MAP: dict[str, frozenset[str]] = {
    "RECOVER": frozenset({"RETRY_PAYMENT", "SEND_PAYMENT_LINK", "SEND_REMINDER"}),
    "WAIT":    frozenset({"WAIT"}),
    "STOP":    frozenset({"STOP"}),
}


@dataclass
class PolicyResult:
    """
    Outcome of the policy gate evaluation.

    allowed       True if the proposed action may proceed.
    decision      Final decision (may differ from LLM if overridden).
    action        Final action (may differ from LLM if overridden).
    reason        Why the policy allowed or rejected the proposal.
    overridden    True if the policy changed the LLM decision.
    """
    allowed: bool
    decision: str
    action: str
    reason: str
    overridden: bool = False


def evaluate(
    *,
    proposed_decision: str,
    proposed_action: str,
    order_status: str,
    case_status: str,
    previous_attempt_count: int,
    has_successful_payment: bool,
) -> PolicyResult:
    """
    Deterministically evaluate whether the LLM decision should be executed.

    Parameters mirror the data retrieved by the investigation tools —
    no raw DB objects are passed here to keep the policy layer testable
    without a database.
    """

    # ── R1: Order already paid ────────────────────────────────────────────────
    if has_successful_payment or order_status == "PAID":
        logger.info("Policy R1: order already paid — forcing STOP")
        return PolicyResult(
            allowed=False,
            decision="STOP",
            action="STOP",
            reason="Order already has a successful payment; no recovery needed.",
            overridden=(proposed_decision != "STOP"),
        )

    # ── R2: Order cancelled ───────────────────────────────────────────────────
    if order_status == "CANCELLED":
        logger.info("Policy R2: order cancelled — forcing STOP")
        return PolicyResult(
            allowed=False,
            decision="STOP",
            action="STOP",
            reason="Order has been cancelled; recovery is not applicable.",
            overridden=(proposed_decision != "STOP"),
        )

    # ── R3: Case already in terminal status ───────────────────────────────────
    if case_status in TERMINAL_STATUSES:
        logger.info("Policy R3: case already terminal (%s) — forcing STOP", case_status)
        return PolicyResult(
            allowed=False,
            decision="STOP",
            action="STOP",
            reason=f"RecoveryCase is already in terminal status '{case_status}'.",
            overridden=(proposed_decision != "STOP"),
        )

    # ── R4: Max recovery attempts reached ─────────────────────────────────────
    if previous_attempt_count >= MAX_RECOVERY_ATTEMPTS:
        logger.info(
            "Policy R4: max attempts reached (%d/%d) — forcing STOP",
            previous_attempt_count, MAX_RECOVERY_ATTEMPTS,
        )
        return PolicyResult(
            allowed=False,
            decision="STOP",
            action="STOP",
            reason=(
                f"Maximum recovery attempts ({MAX_RECOVERY_ATTEMPTS}) reached. "
                "No further recovery actions will be executed."
            ),
            overridden=(proposed_decision != "STOP"),
        )

    # ── R5: Missing context guard ─────────────────────────────────────────────
    # If the model proposed RECOVER but picked an action outside the allowed set
    if proposed_decision == "RECOVER" and proposed_action not in DECISION_ACTION_MAP["RECOVER"]:
        logger.warning(
            "Policy R5: invalid action '%s' for RECOVER — forcing WAIT",
            proposed_action,
        )
        return PolicyResult(
            allowed=False,
            decision="WAIT",
            action="WAIT",
            reason=(
                f"Model proposed action '{proposed_action}' which is not permitted "
                "for a RECOVER decision. Defaulting to WAIT."
            ),
            overridden=True,
        )

    # ── R6: Validate action is in allowed set for the given decision ──────────
    allowed_for_decision = DECISION_ACTION_MAP.get(proposed_decision, frozenset())
    if proposed_action not in allowed_for_decision:
        logger.warning(
            "Policy R6: action '%s' not allowed for decision '%s'",
            proposed_action, proposed_decision,
        )
        return PolicyResult(
            allowed=False,
            decision="STOP",
            action="STOP",
            reason=(
                f"Action '{proposed_action}' is not permitted for "
                f"decision '{proposed_decision}'."
            ),
            overridden=True,
        )

    # ── R7: Allow ─────────────────────────────────────────────────────────────
    logger.info(
        "Policy R7: decision='%s' action='%s' ALLOWED",
        proposed_decision, proposed_action,
    )
    return PolicyResult(
        allowed=True,
        decision=proposed_decision,
        action=proposed_action,
        reason="Policy checks passed.",
        overridden=False,
    )
