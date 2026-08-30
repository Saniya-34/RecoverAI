"""
backend/app/tools/recovery_tools.py

Read-only investigation tools for the RecoverAI agent.

IMPORTANT BOUNDARIES
────────────────────
- Every function here is READ-ONLY.
- No INSERT, UPDATE, or DELETE operations.
- No external API calls.
- The LLM cannot construct or inject arbitrary SQL.
- All queries use typed SQLAlchemy ORM expressions.

These tools are called by the LangGraph agent nodes — not directly
by the LLM.  The LLM receives the structured results and uses them
as evidence for its RecoveryDecision.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.agent_action import AgentAction
from backend.app.models.customer import Customer
from backend.app.models.order import Order
from backend.app.models.payment import Payment
from backend.app.models.recovery_case import CaseStatus, RecoveryCase

logger = logging.getLogger(__name__)


# ── Return types (plain dataclasses — no ORM objects leave this module) ───────

@dataclass
class CaseContext:
    """Minimal case snapshot passed into the agent state."""
    case_id: int
    case_type: str
    status: str
    risk_amount: Decimal
    recovered_amount: Decimal
    currency: str
    customer_id: int
    order_id: int
    payment_id: int | None
    detected_at: datetime
    failure_reason: str | None = None


@dataclass
class CustomerHistory:
    customer_id: int
    external_customer_id: str
    name: str | None
    email: str | None
    total_orders: int
    successful_payments: int
    failed_payments: int
    payment_success_rate: float          # 0.0 – 1.0
    recent_failure_reasons: list[str]    # last 3 distinct failure reasons


@dataclass
class PaymentAttempt:
    external_payment_id: str | None
    status: str
    amount: Decimal
    currency: str
    failure_reason: str | None
    payment_method: str | None
    attempted_at: datetime | None


@dataclass
class PaymentHistory:
    order_id: int
    customer_id: int
    attempts: list[PaymentAttempt]
    total_attempts: int
    successful_attempts: int
    failed_attempts: int


@dataclass
class OrderSummary:
    external_order_id: str
    amount: Decimal
    currency: str
    status: str
    created_at: datetime


@dataclass
class OrderHistory:
    customer_id: int
    recent_orders: list[OrderSummary]
    total_orders: int


@dataclass
class PreviousRecoveryAttempt:
    agent_action_id: int
    recovery_case_id: int
    action_type: str
    status: str
    reason: str | None
    executed_at: datetime | None
    created_at: datetime


@dataclass
class RecoveryAttemptHistory:
    recovery_case_id: int
    attempts: list[PreviousRecoveryAttempt]
    total_attempts: int


# ── Tool implementations ──────────────────────────────────────────────────────

class RecoveryTools:
    """
    Stateless tool container.  Instantiate with a live, read-only DB session.
    All methods raise ValueError for invalid inputs so the agent can catch
    them and add them to the error list in state.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Tool 1: Get Recovery Case ─────────────────────────────────────────────

    def get_recovery_case(self, recovery_case_id: int) -> CaseContext:
        """
        Load the minimal case context needed to start the agent workflow.
        Raises ValueError if the case does not exist.
        """
        case = self._db.get(RecoveryCase, recovery_case_id)
        if not case:
            raise ValueError(f"RecoveryCase {recovery_case_id} not found.")

        failure_reason: str | None = None
        if case.payment_id:
            payment = self._db.get(Payment, case.payment_id)
            if payment:
                failure_reason = payment.failure_reason

        logger.debug("get_recovery_case: loaded case %d type=%s", case.id, case.case_type)
        return CaseContext(
            case_id=case.id,
            case_type=case.case_type.value,
            status=case.status.value,
            risk_amount=case.risk_amount,
            recovered_amount=case.recovered_amount,
            currency="INR",
            customer_id=case.customer_id,
            order_id=case.order_id,
            payment_id=case.payment_id,
            detected_at=case.detected_at,
            failure_reason=failure_reason,
        )

    # ── Tool 2: Get Customer History ──────────────────────────────────────────

    def get_customer_history(self, customer_id: int) -> CustomerHistory:
        """
        Returns aggregated payment and order statistics for a customer.
        Does NOT return raw PII beyond name/email (no phone, no card details).
        """
        customer = self._db.get(Customer, customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found.")

        # Aggregate payment stats
        total_payments: int = self._db.execute(
            select(func.count(Payment.id)).where(Payment.customer_id == customer_id)
        ).scalar() or 0

        successful: int = self._db.execute(
            select(func.count(Payment.id)).where(
                Payment.customer_id == customer_id,
                Payment.status == "SUCCESS",
            )
        ).scalar() or 0

        failed: int = self._db.execute(
            select(func.count(Payment.id)).where(
                Payment.customer_id == customer_id,
                Payment.status == "FAILED",
            )
        ).scalar() or 0

        success_rate = (successful / total_payments) if total_payments > 0 else 0.0

        # Recent distinct failure reasons (last 3)
        recent_failures = self._db.execute(
            select(Payment.failure_reason)
            .where(
                Payment.customer_id == customer_id,
                Payment.status == "FAILED",
                Payment.failure_reason.isnot(None),
            )
            .order_by(Payment.attempted_at.desc())
            .limit(10)
        ).scalars().all()

        seen: list[str] = []
        for r in recent_failures:
            if r and r not in seen:
                seen.append(r)
            if len(seen) >= 3:
                break

        total_orders: int = self._db.execute(
            select(func.count(Order.id)).where(Order.customer_id == customer_id)
        ).scalar() or 0

        logger.debug(
            "get_customer_history: customer %d — success_rate=%.2f total_orders=%d",
            customer_id, success_rate, total_orders,
        )
        return CustomerHistory(
            customer_id=customer_id,
            external_customer_id=customer.external_customer_id,
            name=customer.name,
            email=customer.email,
            total_orders=total_orders,
            successful_payments=successful,
            failed_payments=failed,
            payment_success_rate=round(success_rate, 4),
            recent_failure_reasons=seen,
        )

    # ── Tool 3: Get Payment History ───────────────────────────────────────────

    def get_payment_history(self, order_id: int) -> PaymentHistory:
        """
        Returns all payment attempts for a given order.
        """
        order = self._db.get(Order, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found.")

        payments = self._db.execute(
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.attempted_at.asc())
        ).scalars().all()

        attempts = [
            PaymentAttempt(
                external_payment_id=p.external_payment_id,
                status=p.status,
                amount=p.amount,
                currency=p.currency,
                failure_reason=p.failure_reason,
                payment_method=p.payment_method,
                attempted_at=p.attempted_at,
            )
            for p in payments
        ]

        successful = sum(1 for a in attempts if a.status == "SUCCESS")
        failed = sum(1 for a in attempts if a.status == "FAILED")

        logger.debug(
            "get_payment_history: order %d — %d attempts (%d success, %d failed)",
            order_id, len(attempts), successful, failed,
        )
        return PaymentHistory(
            order_id=order_id,
            customer_id=order.customer_id,
            attempts=attempts,
            total_attempts=len(attempts),
            successful_attempts=successful,
            failed_attempts=failed,
        )

    # ── Tool 4: Get Order History ─────────────────────────────────────────────

    def get_order_history(self, customer_id: int, limit: int = 10) -> OrderHistory:
        """
        Returns recent orders for a customer (most recent first).
        """
        orders = self._db.execute(
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        ).scalars().all()

        total: int = self._db.execute(
            select(func.count(Order.id)).where(Order.customer_id == customer_id)
        ).scalar() or 0

        return OrderHistory(
            customer_id=customer_id,
            total_orders=total,
            recent_orders=[
                OrderSummary(
                    external_order_id=o.external_order_id,
                    amount=o.amount,
                    currency=o.currency,
                    status=o.status,
                    created_at=o.created_at,
                )
                for o in orders
            ],
        )

    # ── Tool 5: Get Previous Recovery Attempts ────────────────────────────────

    def get_previous_recovery_attempts(
        self, recovery_case_id: int
    ) -> RecoveryAttemptHistory:
        """
        Returns all AgentAction records for this recovery case.
        Used by the policy gate to enforce MAX_RECOVERY_ATTEMPTS.
        """
        actions = self._db.execute(
            select(AgentAction)
            .where(AgentAction.recovery_case_id == recovery_case_id)
            .order_by(AgentAction.created_at.asc())
        ).scalars().all()

        return RecoveryAttemptHistory(
            recovery_case_id=recovery_case_id,
            total_attempts=len(actions),
            attempts=[
                PreviousRecoveryAttempt(
                    agent_action_id=a.id,
                    recovery_case_id=a.recovery_case_id,
                    action_type=a.action_type.value,
                    status=a.status.value,
                    reason=a.reason,
                    executed_at=a.executed_at,
                    created_at=a.created_at,
                )
                for a in actions
            ],
        )

    # ── Tool 6: Get Full Case Context (aggregated) ────────────────────────────

    def get_case_context(self, recovery_case_id: int) -> dict:
        """
        Convenience aggregator — returns all investigation data in one call.
        The agent nodes call individual tools; this is for the LLM prompt
        context builder.  Returns plain dicts (JSON-serialisable).
        """
        case = self.get_recovery_case(recovery_case_id)
        customer_history = self.get_customer_history(case.customer_id)
        payment_history = self.get_payment_history(case.order_id)
        order_history = self.get_order_history(case.customer_id, limit=5)
        recovery_attempts = self.get_previous_recovery_attempts(recovery_case_id)

        return {
            "case": {
                "id": case.case_id,
                "type": case.case_type,
                "status": case.status,
                "risk_amount": str(case.risk_amount),
                "currency": case.currency,
                "failure_reason": case.failure_reason,
                "detected_at": case.detected_at.isoformat(),
            },
            "customer": {
                "id": customer_history.customer_id,
                "total_orders": customer_history.total_orders,
                "successful_payments": customer_history.successful_payments,
                "failed_payments": customer_history.failed_payments,
                "payment_success_rate": customer_history.payment_success_rate,
                "recent_failure_reasons": customer_history.recent_failure_reasons,
            },
            "payment_history": {
                "total_attempts": payment_history.total_attempts,
                "successful_attempts": payment_history.successful_attempts,
                "failed_attempts": payment_history.failed_attempts,
                "attempts": [
                    {
                        "status": a.status,
                        "failure_reason": a.failure_reason,
                        "payment_method": a.payment_method,
                        "attempted_at": a.attempted_at.isoformat() if a.attempted_at else None,
                    }
                    for a in payment_history.attempts
                ],
            },
            "order_history": {
                "total_orders": order_history.total_orders,
                "recent_statuses": [o.status for o in order_history.recent_orders],
            },
            "previous_recovery_attempts": {
                "total": recovery_attempts.total_attempts,
                "actions": [
                    {
                        "action_type": a.action_type,
                        "status": a.status,
                        "executed_at": a.executed_at.isoformat() if a.executed_at else None,
                    }
                    for a in recovery_attempts.attempts
                ],
            },
        }
