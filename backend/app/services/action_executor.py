"""
backend/app/services/action_executor.py

Bounded Simulated Action Executor.

THIS IS A SIMULATION — NO REAL PAYMENTS ARE MADE.

Every result includes "simulated": True so there is never any ambiguity.

Architecture
────────────
    AI Agent
        ↓
    Policy Gate
        ↓
    ActionExecutor  ← this module
        ↓
    SimulatedActionExecutor  (current implementation)
        ↓
    [Future: RazorpayTestModeExecutor]

The executor interface is intentionally minimal so the Razorpay Test Mode
adapter can replace SimulatedActionExecutor without changing the agent or
policy code.

Allowed actions
───────────────
RETRY_PAYMENT       Simulates a payment retry attempt.
SEND_PAYMENT_LINK   Simulates sending a payment link to the customer.
SEND_REMINDER       Simulates sending an abandonment/recovery reminder.
WAIT                No action — agent is waiting for external signal.
STOP                No action — recovery is halted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = frozenset({
    "RETRY_PAYMENT",
    "SEND_PAYMENT_LINK",
    "SEND_REMINDER",
    "WAIT",
    "STOP",
})


@dataclass
class ExecutionResult:
    """
    Result of a simulated action execution.

    simulated is ALWAYS True in this executor.
    It must be preserved in the AgentAction.result JSON so nobody
    mistakes this for a real payment action.
    """
    success: bool
    action: str
    simulated: bool = True
    message: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "action": self.action,
            "simulated": self.simulated,
            "message": self.message,
        }


class SimulatedActionExecutor:
    """
    Executes bounded recovery actions in simulation mode.

    No external APIs are called.
    No database writes happen here — the agent graph handles persistence.
    """

    def execute(self, action: str, context: dict | None = None) -> ExecutionResult:
        """
        Execute a recovery action.

        Parameters
        ----------
        action  : One of ALLOWED_ACTIONS.
        context : Optional dict with case/customer context for logging.

        Returns
        -------
        ExecutionResult with simulated=True always.

        Raises
        ------
        ValueError if action is not in ALLOWED_ACTIONS.
        """
        if action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"Action '{action}' is not permitted. "
                f"Allowed: {sorted(ALLOWED_ACTIONS)}"
            )

        case_id = (context or {}).get("case_id", "?")
        logger.info(
            "ActionExecutor: executing '%s' for case_id=%s [SIMULATED]",
            action, case_id,
        )

        result = self._dispatch(action, context or {})
        logger.info(
            "ActionExecutor: '%s' completed — success=%s [SIMULATED]",
            action, result.success,
        )
        return result

    def _dispatch(self, action: str, context: dict) -> ExecutionResult:
        handlers = {
            "RETRY_PAYMENT":    self._retry_payment,
            "SEND_PAYMENT_LINK": self._send_payment_link,
            "SEND_REMINDER":    self._send_reminder,
            "WAIT":             self._wait,
            "STOP":             self._stop,
        }
        return handlers[action](context)

    # ── Simulated action handlers ─────────────────────────────────────────────

    def _retry_payment(self, context: dict) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            action="RETRY_PAYMENT",
            simulated=True,
            message=(
                "Payment retry simulated successfully. "
                "In production this would call the Razorpay payment retry API."
            ),
        )

    def _send_payment_link(self, context: dict) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            action="SEND_PAYMENT_LINK",
            simulated=True,
            message=(
                "Payment link generation simulated. "
                "In production this would generate a Razorpay payment link "
                "and dispatch it via email or SMS."
            ),
        )

    def _send_reminder(self, context: dict) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            action="SEND_REMINDER",
            simulated=True,
            message=(
                "Recovery reminder simulated. "
                "In production this would send an email or SMS reminder "
                "with a checkout recovery link."
            ),
        )

    def _wait(self, context: dict) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            action="WAIT",
            simulated=True,
            message="No action taken. Agent is waiting for external signal.",
        )

    def _stop(self, context: dict) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            action="STOP",
            simulated=True,
            message="Recovery stopped. No further actions will be attempted.",
        )


# Module-level singleton — reuse across requests
executor = SimulatedActionExecutor()
