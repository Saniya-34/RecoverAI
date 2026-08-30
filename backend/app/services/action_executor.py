"""
backend/app/services/action_executor.py

Bounded Simulated Action Executor.

This module contains the simulation implementation of recovery actions.

The shared ExecutionResult model is defined in executionModels.py so that
both the simulated and Razorpay executors can use it without creating
a circular import.
"""

from __future__ import annotations

import logging

from .executionModels import ExecutionResult

logger = logging.getLogger(__name__)


ALLOWED_ACTIONS = frozenset({
    "RETRY_PAYMENT",
    "SEND_PAYMENT_LINK",
    "SEND_REMINDER",
    "WAIT",
    "STOP",
})


class SimulatedActionExecutor:
    """
    Executes bounded recovery actions in simulation mode.

    No external APIs are called.
    No database writes happen here.
    The agent graph handles persistence.
    """

    ALLOWED_ACTIONS = ALLOWED_ACTIONS

    def execute(
        self,
        action: str,
        context: dict | None = None,
    ) -> ExecutionResult:

        if action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"Action '{action}' is not permitted. "
                f"Allowed: {sorted(ALLOWED_ACTIONS)}"
            )

        case_id = (context or {}).get("case_id", "?")

        logger.info(
            "ActionExecutor: executing '%s' for case_id=%s [SIMULATED]",
            action,
            case_id,
        )

        result = self._dispatch(action, context or {})

        logger.info(
            "ActionExecutor: '%s' completed — success=%s [SIMULATED]",
            action,
            result.success,
        )

        return result

    def _dispatch(
        self,
        action: str,
        context: dict,
    ) -> ExecutionResult:

        handlers = {
            "RETRY_PAYMENT": self._retry_payment,
            "SEND_PAYMENT_LINK": self._send_payment_link,
            "SEND_REMINDER": self._send_reminder,
            "WAIT": self._wait,
            "STOP": self._stop,
        }

        return handlers[action](context)

    # ------------------------------------------------------------------
    # Simulated action handlers
    # ------------------------------------------------------------------

    def _retry_payment(self, context: dict) -> ExecutionResult:
        import random

        force_outcome = context.get("force_outcome")

        if force_outcome is not None:
            if force_outcome == "SUCCESS":
                success = True
                payment_outcome = "SUCCESS"

            elif force_outcome == "FAILURE":
                success = False
                payment_outcome = "FAILURE"

            else:
                success = False
                payment_outcome = "WAIT"

        elif "force_success" in context:
            success = bool(context["force_success"])
            payment_outcome = "SUCCESS" if success else "FAILURE"

        else:
            success = random.random() > 0.3
            payment_outcome = "SUCCESS" if success else "FAILURE"

        message = (
            "Payment retry simulated successfully."
            if success
            else "Payment retry simulated but failed (simulated decline)."
        )

        message += (
            " In production this would call the Razorpay payment retry API."
        )

        return ExecutionResult(
            success=success,
            action="RETRY_PAYMENT",
            simulated=True,
            message=message,
            payment_outcome=payment_outcome,
        )

    def _send_payment_link(self, context: dict) -> ExecutionResult:

        success = context.get("force_success", True)

        return ExecutionResult(
            success=success,
            action="SEND_PAYMENT_LINK",
            simulated=True,
            message=(
                "Payment link generation simulated. "
                "In production this would generate a Razorpay payment link "
                "and dispatch it via email or SMS."
            ),
            payment_outcome="WAIT",
        )

    def _send_reminder(self, context: dict) -> ExecutionResult:

        success = context.get("force_success", True)

        return ExecutionResult(
            success=success,
            action="SEND_REMINDER",
            simulated=True,
            message=(
                "Recovery reminder simulated. "
                "In production this would send an email or SMS reminder "
                "with a checkout recovery link."
            ),
            payment_outcome="WAIT",
        )

    def _wait(self, context: dict) -> ExecutionResult:

        return ExecutionResult(
            success=True,
            action="WAIT",
            simulated=True,
            message="No action taken. Agent is waiting for external signal.",
            payment_outcome="WAIT",
        )

    def _stop(self, context: dict) -> ExecutionResult:

        return ExecutionResult(
            success=True,
            action="STOP",
            simulated=True,
            message="Recovery stopped. No further actions will be attempted.",
            payment_outcome="FAILURE",
        )