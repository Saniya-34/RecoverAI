import logging

from .razorpay_service import RazorpayService
from .executionModels import ExecutionResult
from .action_executor import SimulatedActionExecutor

logger = logging.getLogger(__name__)


class RazorpayTestModeExecutor:
    """
    Executes payment-related actions through Razorpay Test Mode.

    Non-payment actions continue to use the existing simulated executor.
    """

    ALLOWED_ACTIONS = SimulatedActionExecutor.ALLOWED_ACTIONS

    def __init__(self) -> None:
        self._simulated_executor = SimulatedActionExecutor()
        self._razorpay_service = RazorpayService()

    def execute(
        self,
        action: str,
        context: dict | None = None,
    ) -> ExecutionResult:

        if action not in self.ALLOWED_ACTIONS:
            raise ValueError(
                f"Action '{action}' is not permitted. "
                f"Allowed: {sorted(self.ALLOWED_ACTIONS)}"
            )

        context = context or {}
        case_id = context.get("case_id", "?")

        logger.info(
            "RazorpayTestModeExecutor: executing '%s' for case_id=%s",
            action,
            case_id,
        )

        if action in {"RETRY_PAYMENT", "SEND_PAYMENT_LINK"}:
            return self._create_payment_link(action, context)

        # SEND_REMINDER, WAIT and STOP remain simulated.
        result = self._simulated_executor.execute(action, context)
        result.simulated = True

        return result

    def _create_payment_link(
        self,
        action: str,
        context: dict,
    ) -> ExecutionResult:

        case_id = context.get("case_id", "?")
        risk_amount = context.get("risk_amount")

        if risk_amount is None:
            raise ValueError(
                "Context must provide 'risk_amount' for payment link creation."
            )

        try:
            amount_int = int(float(risk_amount) * 100)

            notes = {
                "reference_id": f"case-{case_id}",
                "case_id": str(case_id),
            }

            response = self._razorpay_service.create_payment_link(
                amount=amount_int,
                currency="INR",
                notes=notes,
                description=f"RecoverAI payment for case {case_id}",
            )

            payment_link_id = response.get("id")
            short_url = response.get("short_url")

            if not payment_link_id or not short_url:
                raise RuntimeError(
                    "Razorpay did not return a payment link ID and URL."
                )

            result = ExecutionResult(
                    success=True,
                    action=action,
                    simulated=False,
                    message=f"Payment link created: {short_url}",
                    payment_outcome="WAIT",
                    payment_link_id=payment_link_id,
                    payment_link_url=short_url,
                )
                
            logger.info(
                "Razorpay payment link created for case_id=%s",
                case_id,
            )

            return result

        except Exception as exc:

            logger.exception(
                "Failed to create Razorpay payment link for case_id=%s",
                case_id,
            )

            return ExecutionResult(
                success=False,
                action=action,
                simulated=False,
                message=str(exc),
                payment_outcome="FAILURE",
            )


# Module-level singleton
executor = RazorpayTestModeExecutor()