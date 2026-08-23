"""
backend/app/schemas/event.py

Pydantic v2 schemas for the merchant-event ingestion API.

Design notes
────────────
- External IDs (strings) are accepted rather than internal DB integers,
  exactly as a real merchant integration would send them.
- external_event_id is the idempotency key — callers must supply it.
- Per-event cross-field validation is enforced via model_validator so
  that error messages are precise and actionable.
- Monetary values use Decimal (validated with Annotated constraints)
  to match the DB NUMERIC(12, 2) columns.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Type alias for monetary amounts ──────────────────────────────────────────
# Pydantic v2: use Annotated + Field for Decimal constraints.
# max_digits=14 allows up to 999999999999.99; decimal_places=2 matches DB.
PositiveAmount = Annotated[
    Decimal,
    Field(gt=Decimal("0"), max_digits=14, decimal_places=2),
]


# ── Supported event types ─────────────────────────────────────────────────────
VALID_EVENT_TYPES: frozenset[str] = frozenset({
    "CHECKOUT_STARTED",
    "PAYMENT_INITIATED",
    "PAYMENT_SUCCESS",
    "PAYMENT_FAILED",
    "CHECKOUT_ABANDONED",
})


# ── Inbound request ───────────────────────────────────────────────────────────

class EventRequest(BaseModel):
    """
    A single merchant/payment event sent to RecoverAI.

    Always required
    ───────────────
    external_event_id     Caller-supplied idempotency key (unique per event).
    event_type            One of VALID_EVENT_TYPES.
    external_customer_id  Merchant's own customer identifier.

    Conditionally required (enforced by validate_event_fields)
    ──────────────────────────────────────────────────────────
    external_order_id     Required for all five event types.
    external_payment_id   Required for PAYMENT_INITIATED / SUCCESS / FAILED.
    amount                Required for CHECKOUT_STARTED / PAYMENT_* events.
    failure_reason        Required for PAYMENT_FAILED.

    Optional
    ────────
    payment_method        Recommended for payment events.
    occurred_at           Merchant-side timestamp (ISO-8601). Defaults to now.
    event_metadata        Arbitrary JSON pass-through.
    currency              ISO-4217. Defaults to "INR".
    """

    # ── Idempotency ───────────────────────────────────────────────────────────
    external_event_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Caller-supplied unique event identifier (idempotency key).",
    )

    # ── Classification ────────────────────────────────────────────────────────
    event_type: str = Field(
        ...,
        description=f"One of: {', '.join(sorted(VALID_EVENT_TYPES))}",
    )

    # ── Merchant-side identifiers ─────────────────────────────────────────────
    external_customer_id: str = Field(..., min_length=1, max_length=255)
    external_order_id: str | None = Field(None, max_length=255)
    external_payment_id: str | None = Field(None, max_length=255)

    # ── Financials ────────────────────────────────────────────────────────────
    amount: PositiveAmount | None = Field(
        None,
        description="Order/payment amount. Required for financial events.",
    )
    currency: str = Field(
        "INR",
        min_length=3,
        max_length=3,
        description="ISO-4217 currency code.",
    )

    # ── Payment details ───────────────────────────────────────────────────────
    failure_reason: str | None = Field(None, max_length=255)
    payment_method: str | None = Field(None, max_length=100)

    # ── Timing ────────────────────────────────────────────────────────────────
    occurred_at: datetime | None = Field(
        None,
        description=(
            "When the event occurred on the merchant side (ISO-8601 with timezone). "
            "Defaults to server receipt time if omitted."
        ),
    )

    # ── Pass-through ──────────────────────────────────────────────────────────
    event_metadata: dict[str, Any] | None = Field(
        None,
        description="Arbitrary key/value metadata (UTM params, browser info, etc.).",
    )

    # ── Field-level validation ────────────────────────────────────────────────

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in VALID_EVENT_TYPES:
            raise ValueError(
                f"event_type '{v}' is not supported. "
                f"Must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}"
            )
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency_uppercase(cls, v: str) -> str:
        return v.upper()

    # ── Cross-field validation ────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_event_fields(self) -> "EventRequest":
        et = self.event_type

        # order_id is required for all supported event types
        if not self.external_order_id:
            raise ValueError(f"external_order_id is required for {et}")

        # amount is required for financial events
        if et in {
            "CHECKOUT_STARTED",
            "PAYMENT_INITIATED",
            "PAYMENT_SUCCESS",
            "PAYMENT_FAILED",
        } and self.amount is None:
            raise ValueError(f"amount is required for {et}")

        # payment_id is required for payment events
        if et in {"PAYMENT_INITIATED", "PAYMENT_SUCCESS", "PAYMENT_FAILED"}:
            if not self.external_payment_id:
                raise ValueError(f"external_payment_id is required for {et}")

        # failure_reason is required for PAYMENT_FAILED
        if et == "PAYMENT_FAILED" and not self.failure_reason:
            raise ValueError("failure_reason is required for PAYMENT_FAILED")

        return self


# ── Outbound response ─────────────────────────────────────────────────────────

class EventResponse(BaseModel):
    """
    Response from POST /api/events.

    event_processed   False only for duplicate events (idempotency guard).
    duplicate         True when external_event_id was already seen.
    revenue_at_risk   Whether a RecoveryCase was created or found.
    risk_amount       The monetary amount at risk (null if no case).
    currency          ISO-4217 (always present when risk_amount is set).
    case_id           Internal RecoveryCase ID (null if no case).
    case_type         PAYMENT_FAILURE | CHECKOUT_ABANDONMENT | etc.
    case_status       OPEN | IN_PROGRESS | RECOVERED | etc.
    reason            Human-readable explanation of the detection decision.
    """

    event_processed: bool
    duplicate: bool = False
    revenue_at_risk: bool
    risk_amount: Decimal | None = None
    currency: str | None = None
    case_id: int | None = None
    case_type: str | None = None
    case_status: str | None = None
    reason: str

    model_config = {"from_attributes": True}
