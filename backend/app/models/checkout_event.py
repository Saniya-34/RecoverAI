"""
CheckoutEvent model — records granular events during the checkout funnel.

RecoverAI needs this to:
- Detect checkout abandonment (CHECKOUT_STARTED but never PAYMENT_SUCCESS)
- Understand at which step a customer dropped off
- Feed the AI agent with behavioural signals for smarter recovery decisions

Event types are stored as a PostgreSQL ENUM for data integrity while
remaining extensible — add new values to the Enum class and generate
a new migration (ALTER TYPE ... ADD VALUE).
"""

import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class CheckoutEventType(str, enum.Enum):
    """
    Lifecycle events within the checkout funnel.

    Using a Python str-enum means values are plain strings at the
    application layer, while PostgreSQL enforces the allowed set.
    Add new values here + run a migration to extend.
    """
    CHECKOUT_STARTED   = "CHECKOUT_STARTED"
    CHECKOUT_ABANDONED = "CHECKOUT_ABANDONED"
    PAYMENT_INITIATED  = "PAYMENT_INITIATED"
    PAYMENT_SUCCESS    = "PAYMENT_SUCCESS"
    PAYMENT_FAILED     = "PAYMENT_FAILED"


class CheckoutEvent(Base):
    __tablename__ = "checkout_events"

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # Foreign keys — both nullable because an event might arrive before   #
    # an order is confirmed (e.g. CHECKOUT_STARTED has no order yet)      #
    # ------------------------------------------------------------------ #
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Event classification                                                 #
    # ------------------------------------------------------------------ #
    event_type: Mapped[CheckoutEventType] = mapped_column(
        Enum(CheckoutEventType, name="checkout_event_type", create_type=True),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Cart/order value at the time of the event                           #
    # ------------------------------------------------------------------ #
    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=2), nullable=True
    )

    # ------------------------------------------------------------------ #
    # Flexible metadata — browser info, UTM params, cart contents, etc.  #
    # Stored as JSON for PostgreSQL query flexibility.                   #
    # Named event_metadata because 'metadata' is reserved by SQLAlchemy. #
    # ------------------------------------------------------------------ #
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    # ------------------------------------------------------------------ #
    # Timestamps                                                           #
    # ------------------------------------------------------------------ #
    # occurred_at: the real-world time the event happened (sent by client)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    # created_at: when this row was inserted into our DB
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    customer: Mapped["Customer"] = relationship(  # noqa: F821
        "Customer", back_populates="checkout_events"
    )
    order: Mapped["Order | None"] = relationship(  # noqa: F821
        "Order", back_populates="checkout_events"
    )

    # ------------------------------------------------------------------ #
    # Composite index — "all checkout events for a customer ordered by    #
    # time" is the primary abandonment-detection query                    #
    # ------------------------------------------------------------------ #
    __table_args__ = (
        Index("ix_checkout_events_customer_occurred", "customer_id", "occurred_at"),
        Index("ix_checkout_events_order_type", "order_id", "event_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<CheckoutEvent id={self.id} type={self.event_type.value!r} "
            f"customer_id={self.customer_id} occurred_at={self.occurred_at}>"
        )
