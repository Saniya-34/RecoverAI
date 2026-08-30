"""
backend/app/services/executionModels.py

Shared models for action execution.
"""

from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """
    Result of an action execution.

    simulated=True:
        The action was handled by the local simulator.

    simulated=False:
        The action was handled by Razorpay Test Mode.
    """

    success: bool
    action: str
    simulated: bool = True
    message: str | None = None

    # Possible values:
    # SUCCESS  -> payment actually succeeded
    # FAILURE  -> payment failed
    # WAIT     -> waiting for an external event/payment
    payment_outcome: str = "WAIT"

    # Razorpay Payment Link information.
    # These are populated only when a Razorpay payment link is created.
    payment_link_id: str | None = None
    payment_link_url: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "action": self.action,
            "simulated": self.simulated,
            "message": self.message,
            "payment_outcome": self.payment_outcome,
            "payment_link_id": self.payment_link_id,
            "payment_link_url": self.payment_link_url,
        }