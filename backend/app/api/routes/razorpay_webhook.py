"""
Razorpay webhook endpoint.

Responsibilities:
- Verify Razorpay webhook signatures.
- Guarantee webhook idempotency using RazorpayWebhookEvent.
- Resolve the related Payment using the Razorpay payment-link ID.
- Update the Payment when a payment succeeds.
- Mark related RecoveryCase records as recovered.
- Record an immutable audit event.

This route does not contain agent/business decision logic.
The LangGraph agent decides how to recover; Razorpay webhooks report
the external payment result.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.database.dependencies import get_db
from backend.app.models.audit_log import AuditLog
from backend.app.models.payment import Payment
from backend.app.models.razorpay_webhook_event import RazorpayWebhookEvent
from backend.app.models.recovery_case import CaseStatus, RecoveryCase
from backend.app.services.razorpay_service import RazorpayError, RazorpayService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/webhooks",
    tags=["webhooks"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_payment_link_id(payload: dict[str, Any]) -> str | None:
    """
    Extract the Razorpay payment-link ID from a webhook payload.

    Razorpay payment-link events normally contain the payment-link entity
    under payload["payload"]["payment_link"]["entity"].
    """

    payment_link = (
        payload
        .get("payload", {})
        .get("payment_link", {})
        .get("entity", {})
    )

    if isinstance(payment_link, dict):
        payment_link_id = payment_link.get("id")

        if payment_link_id:
            return str(payment_link_id)

    return None


def _extract_payment_entity(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Return the Razorpay payment entity when available."""

    payment = (
        payload
        .get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )

    return payment if isinstance(payment, dict) else {}


def _amount_from_razorpay_payment(
    payment_entity: dict[str, Any],
    fallback_amount: Decimal,
) -> Decimal:
    """
    Convert Razorpay's smallest currency unit into the amount stored
    by RecoverAI.

    For INR:
        249900 paise -> 2499.00 INR
    """

    amount = payment_entity.get("amount")

    if amount is None:
        return fallback_amount

    try:
        return Decimal(str(amount)) / Decimal("100")
    except Exception:
        logger.warning(
            "Unable to parse Razorpay payment amount=%r. "
            "Using existing payment amount.",
            amount,
        )
        return fallback_amount


def _create_audit_log(
    *,
    recovery_case_id: int | None,
    event_type: str,
    details: dict[str, Any],
) -> AuditLog:
    """Create an immutable webhook audit record."""

    return AuditLog(
        recovery_case_id=recovery_case_id,
        agent_action_id=None,
        event_type=event_type,
        actor="WEBHOOK",
        details=details,
    )


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/razorpay",
    status_code=status.HTTP_200_OK,
    summary="Receive Razorpay webhooks",
    description=(
        "Receives and verifies Razorpay webhook events and updates "
        "RecoverAI payment/recovery state."
    ),
)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(
        default=None,
        alias="X-Razorpay-Signature",
    ),
    x_razorpay_event_id: str | None = Header(
        default=None,
        alias="X-Razorpay-Event-Id",
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:

    # ------------------------------------------------------------------
    # 1. Read the raw request body.
    #
    # Signature verification MUST use the exact raw request body.
    # ------------------------------------------------------------------

    raw_body = await request.body()

    if not raw_body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload is empty.",
        )

    # ------------------------------------------------------------------
    # 2. Validate required Razorpay headers.
    # ------------------------------------------------------------------

    if not x_razorpay_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Razorpay-Signature header.",
        )

    if not x_razorpay_event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Razorpay-Event-Id header.",
        )

    # ------------------------------------------------------------------
    # 3. Verify webhook signature.
    # ------------------------------------------------------------------

    razorpay_service = RazorpayService()

    try:
        razorpay_service.verify_webhook_signature(
            payload=raw_body,
            signature=x_razorpay_signature,
        )

    except RazorpayError:
        logger.warning(
            "Rejected Razorpay webhook because signature verification failed."
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature.",
        )

    # ------------------------------------------------------------------
    # 4. Parse JSON only AFTER signature verification.
    # ------------------------------------------------------------------

    try:
        payload = await request.json()

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        )

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload must be a JSON object.",
        )

    event_type = str(payload.get("event", ""))

    logger.info(
        "Received Razorpay webhook: event=%s event_id=%s",
        event_type,
        x_razorpay_event_id,
    )

    # ------------------------------------------------------------------
    # 5. Idempotency check.
    #
    # Razorpay can retry webhook delivery. We must process a particular
    # event ID only once.
    # ------------------------------------------------------------------

    existing_event = db.execute(
        select(RazorpayWebhookEvent).where(
            RazorpayWebhookEvent.event_id == x_razorpay_event_id
        )
    ).scalar_one_or_none()

    if existing_event:
        logger.info(
            "Ignoring duplicate Razorpay webhook: event_id=%s",
            x_razorpay_event_id,
        )

        return {
            "status": "already_processed",
            "event_id": x_razorpay_event_id,
        }

    # ------------------------------------------------------------------
    # 6. Register the event before performing business updates.
    #
    # The unique database constraint protects us from concurrent duplicate
    # webhook deliveries.
    # ------------------------------------------------------------------

    webhook_event = RazorpayWebhookEvent(
        event_id=x_razorpay_event_id,
    )

    db.add(webhook_event)

    try:
        db.flush()

    except IntegrityError:
        db.rollback()

        logger.info(
            "Duplicate Razorpay webhook detected by database constraint: "
            "event_id=%s",
            x_razorpay_event_id,
        )

        return {
            "status": "already_processed",
            "event_id": x_razorpay_event_id,
        }

    # ------------------------------------------------------------------
    # 7. Only process payment-success events.
    #
    # Other Razorpay events are acknowledged but do not change payment
    # recovery state.
    # ------------------------------------------------------------------

    supported_success_events = {
        "payment_link.paid",
    }

    if event_type not in supported_success_events:
        db.add(
            _create_audit_log(
                recovery_case_id=None,
                event_type="RAZORPAY_WEBHOOK_RECEIVED",
                details={
                    "event": event_type,
                    "event_id": x_razorpay_event_id,
                    "processed": False,
                    "reason": "Event type is not handled by recovery flow.",
                },
            )
        )

        db.commit()

        return {
            "status": "ignored",
            "event_id": x_razorpay_event_id,
            "event": event_type,
        }

    # ------------------------------------------------------------------
    # 8. Resolve the RecoverAI Payment.
    # ------------------------------------------------------------------

    payment_link_id = _extract_payment_link_id(payload)

    if not payment_link_id:
        db.rollback()

        logger.warning(
            "Razorpay payment-success webhook has no payment-link ID. "
            "event_id=%s",
            x_razorpay_event_id,
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment-link ID missing from webhook payload.",
        )

    payment = db.execute(
        select(Payment).where(
            Payment.razorpay_payment_link_id == payment_link_id
        )
    ).scalar_one_or_none()

    if not payment:
        db.rollback()

        logger.error(
            "No RecoverAI payment found for Razorpay payment_link_id=%s",
            payment_link_id,
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No RecoverAI payment found for the Razorpay payment link."
            ),
        )

    # ------------------------------------------------------------------
    # 9. Extract Razorpay payment information.
    # ------------------------------------------------------------------

    payment_entity = _extract_payment_entity(payload)

    razorpay_payment_id = payment_entity.get("id")

    recovered_amount = _amount_from_razorpay_payment(
        payment_entity,
        payment.amount,
    )

    # ------------------------------------------------------------------
    # 10. Update Payment.
    # ------------------------------------------------------------------

    old_payment_status = payment.status

    payment.status = "SUCCESS"
    payment.failure_reason = None

    if razorpay_payment_id:
        payment.external_payment_id = str(razorpay_payment_id)

    # ------------------------------------------------------------------
    # 11. Find all active recovery cases connected to this payment.
    #
    # Normally there should be one case, but handling multiple active
    # cases safely is better than assuming one forever.
    # ------------------------------------------------------------------

    recovery_cases = db.execute(
        select(RecoveryCase).where(
            RecoveryCase.payment_id == payment.id,
            RecoveryCase.status.in_(
                [
                    CaseStatus.OPEN,
                    CaseStatus.IN_PROGRESS,
                ]
            ),
        )
    ).scalars().all()

    # ------------------------------------------------------------------
    # 12. Mark the active recovery case(s) as recovered.
    # ------------------------------------------------------------------

    recovered_case_ids: list[int] = []

    for recovery_case in recovery_cases:

        old_case_status = recovery_case.status.value

        recovery_case.status = CaseStatus.RECOVERED
        recovery_case.recovered_amount = recovered_amount

        # Do not overwrite an existing detected_at / created_at value.
        # resolved_at represents the actual recovery completion time.
        from datetime import datetime, timezone

        recovery_case.resolved_at = datetime.now(timezone.utc)

        recovered_case_ids.append(recovery_case.id)

        db.add(
            _create_audit_log(
                recovery_case_id=recovery_case.id,
                event_type="PAYMENT_RECOVERED",
                details={
                    "event_id": x_razorpay_event_id,
                    "razorpay_event": event_type,
                    "payment_id": payment.id,
                    "razorpay_payment_link_id": payment_link_id,
                    "razorpay_payment_id": razorpay_payment_id,
                    "old_payment_status": old_payment_status,
                    "new_payment_status": "SUCCESS",
                    "old_case_status": old_case_status,
                    "new_case_status": CaseStatus.RECOVERED.value,
                    "recovered_amount": str(recovered_amount),
                    "currency": payment.currency,
                },
            )
        )

    # ------------------------------------------------------------------
    # 13. Audit the payment update even if no active case exists.
    # ------------------------------------------------------------------

    if not recovery_cases:
        db.add(
            _create_audit_log(
                recovery_case_id=None,
                event_type="RAZORPAY_PAYMENT_UPDATED",
                details={
                    "event_id": x_razorpay_event_id,
                    "razorpay_event": event_type,
                    "payment_id": payment.id,
                    "razorpay_payment_link_id": payment_link_id,
                    "razorpay_payment_id": razorpay_payment_id,
                    "old_status": old_payment_status,
                    "new_status": "SUCCESS",
                    "note": (
                        "Payment was updated but no OPEN or IN_PROGRESS "
                        "RecoveryCase was found."
                    ),
                },
            )
        )

    # ------------------------------------------------------------------
    # 14. Commit the complete transaction.
    # ------------------------------------------------------------------

    try:
        db.commit()

    except Exception:
        db.rollback()

        logger.exception(
            "Failed to commit Razorpay webhook processing: event_id=%s",
            x_razorpay_event_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process Razorpay webhook.",
        )

    logger.info(
        "Razorpay payment recovered successfully: "
        "event_id=%s payment_id=%s cases=%s",
        x_razorpay_event_id,
        payment.id,
        recovered_case_ids,
    )

    return {
        "status": "processed",
        "event_id": x_razorpay_event_id,
        "event": event_type,
        "payment_id": payment.id,
        "razorpay_payment_link_id": payment_link_id,
        "razorpay_payment_id": razorpay_payment_id,
        "recovered_amount": str(recovered_amount),
        "recovered_case_ids": recovered_case_ids,
    }