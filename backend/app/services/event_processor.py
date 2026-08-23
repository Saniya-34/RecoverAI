"""
backend/app/services/event_processor.py

Event Processing Service.

Sits between the FastAPI route and the RevenueRiskDetector.

Responsibilities
────────────────
1. Idempotency — rejects events whose external_event_id was already stored.
2. Entity resolution — resolves (or creates) Customer, Order, Payment.
3. State transitions — updates Order/Payment status to reflect the event.
4. CheckoutEvent persistence — stores the raw event for audit/analysis.
5. Risk detection — delegates to RevenueRiskDetector.
6. Result — returns EventProcessingResult to the route layer.

Transaction ownership
─────────────────────
This service flushes but does NOT commit.  The FastAPI route wraps the
entire operation in a single session.begin() block, so the transaction is
committed or rolled back atomically by the route.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.checkout_event import CheckoutEvent, CheckoutEventType
from backend.app.models.customer import Customer
from backend.app.models.order import Order
from backend.app.models.payment import Payment
from backend.app.models.recovery_case import RecoveryCase
from backend.app.schemas.event import EventRequest
from backend.app.services.revenue_risk import DetectionResult, RevenueRiskDetector


# ──────────────────────────────────────────────────────────────────────────────
# Result container
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class EventProcessingResult:
    event_processed: bool
    duplicate: bool
    detection: DetectionResult


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────

class EventProcessor:
    """
    Stateless per-request service.
    Instantiate with a live, open SQLAlchemy session.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._detector = RevenueRiskDetector(db)

    # ── Public entry point ────────────────────────────────────────────────────

    def process(self, req: EventRequest) -> EventProcessingResult:
        """
        Process one merchant event end-to-end.

        Raises ValueError for unresolvable order references so the
        route layer can translate it to HTTP 422.
        """

        # ── 1. Idempotency guard ──────────────────────────────────────────────
        if self._event_already_seen(req.external_event_id):
            return self._duplicate_result(req)

        # ── 2. Resolve / create Customer ─────────────────────────────────────
        customer = self._get_or_create_customer(req)

        # ── 3. Resolve / create Order ────────────────────────────────────────
        order = self._get_or_create_order(req, customer)

        # ── 4. Resolve / create Payment (payment events only) ────────────────
        payment: Payment | None = None
        if req.external_payment_id:
            payment = self._get_or_create_payment(req, order, customer)

        # ── 5. Apply state transitions to Order / Payment ────────────────────
        self._apply_state_transitions(req, order, payment)

        # ── 6. Persist CheckoutEvent (with embedded idempotency key) ─────────
        occurred_at = req.occurred_at or datetime.now(timezone.utc)
        event_meta: dict = dict(req.event_metadata or {})
        event_meta["external_event_id"] = req.external_event_id

        checkout_event = CheckoutEvent(
            customer_id=customer.id,
            order_id=order.id,
            event_type=CheckoutEventType(req.event_type),
            amount=req.amount or order.amount,
            event_metadata=event_meta,
            occurred_at=occurred_at,
            created_at=occurred_at,
        )
        self._db.add(checkout_event)
        self._db.flush()

        # ── 7. Revenue-risk detection ─────────────────────────────────────────
        detection = self._detector.evaluate(
            event_type=req.event_type,
            customer=customer,
            order=order,
            payment=payment,
        )

        return EventProcessingResult(
            event_processed=True,
            duplicate=False,
            detection=detection,
        )

    # ── Idempotency ───────────────────────────────────────────────────────────

    def _event_already_seen(self, external_event_id: str) -> bool:
        """
        Return True if a CheckoutEvent already carries this external_event_id
        inside its event_metadata JSON column.

        Uses the PostgreSQL ->> text extraction operator via SQLAlchemy's
        JSON subscript API, which is efficient and index-friendly.
        """
        result = self._db.execute(
            select(CheckoutEvent.id)
            .where(
                CheckoutEvent.event_metadata["external_event_id"].as_string()
                == external_event_id
            )
            .limit(1)
        ).first()
        return result is not None

    def _duplicate_result(self, req: EventRequest) -> EventProcessingResult:
        """Build a safe, informative result for a duplicate event."""
        detection = DetectionResult(
            revenue_at_risk=False,
            reason=f"Duplicate event '{req.external_event_id}' — already processed.",
        )

        # Enrich with the existing recovery case (if any) for this order
        if req.external_order_id:
            order = self._find_order(req.external_order_id)
            if order:
                existing_case = self._db.execute(
                    select(RecoveryCase)
                    .where(RecoveryCase.order_id == order.id)
                    .order_by(RecoveryCase.created_at.desc())
                    .limit(1)
                ).scalars().first()

                if existing_case:
                    detection = DetectionResult(
                        revenue_at_risk=(existing_case.status.value == "OPEN"),
                        reason=(
                            f"Duplicate event '{req.external_event_id}' — already processed."
                        ),
                        recovery_case=existing_case,
                    )

        return EventProcessingResult(
            event_processed=False,
            duplicate=True,
            detection=detection,
        )

    # ── Customer resolution ───────────────────────────────────────────────────

    def _get_or_create_customer(self, req: EventRequest) -> Customer:
        customer = self._db.execute(
            select(Customer).where(
                Customer.external_customer_id == req.external_customer_id
            )
        ).scalars().first()

        if not customer:
            now = datetime.now(timezone.utc)
            customer = Customer(
                external_customer_id=req.external_customer_id,
                created_at=now,
                updated_at=now,
            )
            self._db.add(customer)
            self._db.flush()

        return customer

    # ── Order resolution ──────────────────────────────────────────────────────

    def _get_or_create_order(self, req: EventRequest, customer: Customer) -> Order:
        order = self._find_order(req.external_order_id)

        if order is None:
            if req.amount is None:
                raise ValueError(
                    f"Order '{req.external_order_id}' does not exist and no 'amount' "
                    "was provided to create it. "
                    "Supply 'amount' with the first event for a new order."
                )
            now = datetime.now(timezone.utc)
            order = Order(
                external_order_id=req.external_order_id,
                customer_id=customer.id,
                amount=req.amount,
                currency=req.currency,
                status="CREATED",
                created_at=now,
                updated_at=now,
            )
            self._db.add(order)
            self._db.flush()

        return order

    def _find_order(self, external_order_id: str | None) -> Order | None:
        if not external_order_id:
            return None
        return self._db.execute(
            select(Order).where(Order.external_order_id == external_order_id)
        ).scalars().first()

    # ── Payment resolution ────────────────────────────────────────────────────

    def _get_or_create_payment(
        self,
        req: EventRequest,
        order: Order,
        customer: Customer,
    ) -> Payment:
        payment = self._db.execute(
            select(Payment).where(
                Payment.external_payment_id == req.external_payment_id
            )
        ).scalars().first()

        if not payment:
            now = datetime.now(timezone.utc)
            occurred = req.occurred_at or now
            payment = Payment(
                external_payment_id=req.external_payment_id,
                order_id=order.id,
                customer_id=customer.id,
                amount=req.amount if req.amount is not None else order.amount,
                currency=req.currency,
                status="PENDING",
                payment_method=req.payment_method,
                attempted_at=occurred,
                created_at=now,
                updated_at=now,
            )
            self._db.add(payment)
            self._db.flush()

        return payment

    # ── State transitions ─────────────────────────────────────────────────────

    def _apply_state_transitions(
        self,
        req: EventRequest,
        order: Order,
        payment: Payment | None,
    ) -> None:
        """
        Update Order and Payment status to reflect the incoming event.

        Transitions are intentionally conservative — we never downgrade
        a status (e.g. we never mark a PAID order as PENDING).
        """
        now = datetime.now(timezone.utc)
        et = req.event_type

        if et == "CHECKOUT_STARTED":
            if order.status == "CREATED":
                order.status = "PENDING"
                order.updated_at = now

        elif et == "PAYMENT_INITIATED":
            if payment and payment.status == "PENDING":
                payment.attempted_at = req.occurred_at or now
                payment.payment_method = req.payment_method or payment.payment_method
                payment.updated_at = now

        elif et == "PAYMENT_SUCCESS":
            order.status = "PAID"
            order.updated_at = now
            if payment:
                payment.status = "SUCCESS"
                payment.attempted_at = req.occurred_at or now
                payment.updated_at = now

        elif et == "PAYMENT_FAILED":
            # Only downgrade order from PENDING/CREATED → FAILED (never from PAID)
            if order.status not in ("PAID",):
                order.status = "FAILED"
                order.updated_at = now
            if payment:
                payment.status = "FAILED"
                payment.failure_reason = req.failure_reason
                payment.attempted_at = req.occurred_at or now
                payment.updated_at = now

        elif et == "CHECKOUT_ABANDONED":
            if order.status not in ("PAID",):
                order.status = "ABANDONED"
                order.updated_at = now

        self._db.flush()
