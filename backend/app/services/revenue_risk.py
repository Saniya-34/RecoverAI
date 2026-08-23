"""
backend/app/services/revenue_risk.py

Deterministic Revenue-at-Risk Detection Service.

This service is the ONLY place where RecoveryCase rows are created.
It receives a fully-resolved context (customer, order, payment ORM objects)
and a triggering event type, inspects the current database state, and
decides whether a recovery case should be opened.

Design principles
─────────────────
- Purely deterministic: no randomness, no LLM, no external calls.
- Database-aware: always checks current state before creating cases.
- Idempotent: never creates two OPEN cases for the same order+case_type.
- Explainable: every decision carries a human-readable `reason` string.
- Does NOT execute recovery actions — that is Stage 5+.

Detection rules
───────────────
Rule 1 — PAYMENT_FAILURE
    Trigger : PAYMENT_FAILED event
    Condition: order has NO successful payment
    Action  : create/return OPEN RecoveryCase(PAYMENT_FAILURE)
    Skipped : if order already has a SUCCESS payment
    Skipped : if an OPEN PAYMENT_FAILURE case already exists for this order

Rule 2 — CHECKOUT_ABANDONMENT
    Trigger : CHECKOUT_ABANDONED event
    Condition: order has NO successful payment
    Action  : create/return OPEN RecoveryCase(CHECKOUT_ABANDONMENT)
    Skipped : if order already has a SUCCESS payment
    Skipped : if an OPEN CHECKOUT_ABANDONMENT case already exists for this order

Rule 3 — PAYMENT_SUCCESS (close open cases)
    Trigger : PAYMENT_SUCCESS event
    Action  : mark any OPEN cases for the order as RECOVERED
    Returns : revenue_at_risk = False
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.customer import Customer
from backend.app.models.order import Order
from backend.app.models.payment import Payment
from backend.app.models.recovery_case import CaseStatus, CaseType, RecoveryCase


# ── Result returned to the caller ────────────────────────────────────────────

@dataclass
class DetectionResult:
    revenue_at_risk: bool
    reason: str
    recovery_case: RecoveryCase | None = None


# ── Public entry point ────────────────────────────────────────────────────────

class RevenueRiskDetector:
    """
    Stateless service — instantiate per-request with a live DB session.
    All methods flush but do NOT commit: the caller owns the transaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Main dispatch ─────────────────────────────────────────────────────────

    def evaluate(
        self,
        event_type: str,
        customer: Customer,
        order: Order,
        payment: Payment | None,
    ) -> DetectionResult:
        """
        Evaluate whether the event creates a revenue-at-risk situation.

        Returns a DetectionResult — callers should inspect .revenue_at_risk
        and .recovery_case (may be None if no new case was created).
        """
        if event_type == "PAYMENT_FAILED":
            return self._handle_payment_failed(customer, order, payment)

        if event_type == "CHECKOUT_ABANDONED":
            return self._handle_checkout_abandoned(customer, order)

        if event_type == "PAYMENT_SUCCESS":
            return self._handle_payment_success(order)

        # CHECKOUT_STARTED and PAYMENT_INITIATED do not trigger cases
        return DetectionResult(
            revenue_at_risk=False,
            reason=f"Event type '{event_type}' does not trigger risk detection.",
        )

    # ── Rule 1: PAYMENT_FAILED ────────────────────────────────────────────────

    def _handle_payment_failed(
        self,
        customer: Customer,
        order: Order,
        payment: Payment | None,
    ) -> DetectionResult:

        # Guard: order already paid — no risk
        if self._order_has_successful_payment(order.id):
            return DetectionResult(
                revenue_at_risk=False,
                reason="Order already has a successful payment; no recovery needed.",
            )

        # Deduplication: OPEN PAYMENT_FAILURE case already exists for this order
        existing = self._find_open_case(order.id, CaseType.PAYMENT_FAILURE)
        if existing:
            return DetectionResult(
                revenue_at_risk=True,
                reason=(
                    f"Payment failed while the order remains unpaid. "
                    f"An existing open case (id={existing.id}) was found."
                ),
                recovery_case=existing,
            )

        # Create new case
        risk_amount = (payment.amount if payment else order.amount)
        case = RecoveryCase(
            customer_id=customer.id,
            order_id=order.id,
            payment_id=payment.id if payment else None,
            case_type=CaseType.PAYMENT_FAILURE,
            risk_amount=risk_amount,
            status=CaseStatus.OPEN,
            detected_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._db.add(case)
        self._db.flush()

        return DetectionResult(
            revenue_at_risk=True,
            reason="Payment failed while the order remains unpaid.",
            recovery_case=case,
        )

    # ── Rule 2: CHECKOUT_ABANDONED ────────────────────────────────────────────

    def _handle_checkout_abandoned(
        self,
        customer: Customer,
        order: Order,
    ) -> DetectionResult:

        # Guard: order already paid — no risk
        if self._order_has_successful_payment(order.id):
            return DetectionResult(
                revenue_at_risk=False,
                reason="Checkout was abandoned, but the order already has a successful payment.",
            )

        # Deduplication
        existing = self._find_open_case(order.id, CaseType.CHECKOUT_ABANDONMENT)
        if existing:
            return DetectionResult(
                revenue_at_risk=True,
                reason=(
                    f"Checkout was abandoned before successful payment. "
                    f"An existing open case (id={existing.id}) was found."
                ),
                recovery_case=existing,
            )

        case = RecoveryCase(
            customer_id=customer.id,
            order_id=order.id,
            payment_id=None,
            case_type=CaseType.CHECKOUT_ABANDONMENT,
            risk_amount=order.amount,
            status=CaseStatus.OPEN,
            detected_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._db.add(case)
        self._db.flush()

        return DetectionResult(
            revenue_at_risk=True,
            reason="Checkout was abandoned before successful payment.",
            recovery_case=case,
        )

    # ── Rule 3: PAYMENT_SUCCESS (close open cases) ────────────────────────────

    def _handle_payment_success(self, order: Order) -> DetectionResult:
        now = datetime.now(timezone.utc)
        closed = 0

        open_cases = self._db.execute(
            select(RecoveryCase).where(
                RecoveryCase.order_id == order.id,
                RecoveryCase.status == CaseStatus.OPEN,
            )
        ).scalars().all()

        for case in open_cases:
            case.status = CaseStatus.RECOVERED
            case.resolved_at = now
            case.updated_at = now
            closed += 1

        if closed:
            self._db.flush()
            return DetectionResult(
                revenue_at_risk=False,
                reason=f"Payment succeeded; {closed} open recovery case(s) marked as RECOVERED.",
            )

        return DetectionResult(
            revenue_at_risk=False,
            reason="Order already has a successful payment; no recovery needed.",
        )

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _order_has_successful_payment(self, order_id: int) -> bool:
        """Return True if at least one SUCCESS payment exists for this order."""
        row = self._db.execute(
            select(Payment.id).where(
                Payment.order_id == order_id,
                Payment.status == "SUCCESS",
            ).limit(1)
        ).first()
        return row is not None

    def _find_open_case(
        self, order_id: int, case_type: CaseType
    ) -> RecoveryCase | None:
        """Return the first OPEN case of the given type for this order, or None."""
        return self._db.execute(
            select(RecoveryCase).where(
                RecoveryCase.order_id == order_id,
                RecoveryCase.case_type == case_type,
                RecoveryCase.status == CaseStatus.OPEN,
            ).limit(1)
        ).scalars().first()
