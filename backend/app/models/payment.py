"""
Payment model — represents a single payment attempt against an order.

RecoverAI needs this to:
- Detect payment failures and classify their root cause
- Know which payment attempts have already been made before retrying
- Track failure_reason to decide the best recovery action
- A single order may have multiple payment attempts (e.g. retry after failure)
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # External reference — payment gateway's own transaction ID           #
    # ------------------------------------------------------------------ #
    external_payment_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )

    # ------------------------------------------------------------------ #
    # Foreign keys                                                         #
    # ------------------------------------------------------------------ #
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Financials — NUMERIC, never FLOAT                                   #
    # ------------------------------------------------------------------ #
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    # ------------------------------------------------------------------ #
    # Payment status — VARCHAR for easy extension                         #
    # Common values: PENDING, SUCCESS, FAILED, REFUNDED, CANCELLED        #
    # ------------------------------------------------------------------ #
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING", index=True
    )

    # ------------------------------------------------------------------ #
    # Failure details — critical for RecoverAI to choose recovery action  #
    # e.g. "INSUFFICIENT_FUNDS", "CARD_EXPIRED", "NETWORK_ERROR"         #
    # ------------------------------------------------------------------ #
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ------------------------------------------------------------------ #
    # Payment method — e.g. "CARD", "UPI", "NETBANKING", "WALLET"        #
    # ------------------------------------------------------------------ #
    payment_method: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ------------------------------------------------------------------ #
    # Timestamps                                                           #
    # ------------------------------------------------------------------ #
    # attempted_at: when the payment was actually attempted at the gateway
    attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    order: Mapped["Order"] = relationship(  # noqa: F821
        "Order", back_populates="payments"
    )
    customer: Mapped["Customer"] = relationship(  # noqa: F821
        "Customer", back_populates="payments"
    )
    recovery_cases: Mapped[list["RecoveryCase"]] = relationship(  # noqa: F821
        "RecoveryCase", back_populates="payment"
    )

    # ------------------------------------------------------------------ #
    # Composite indexes for common recovery queries                        #
    # ------------------------------------------------------------------ #
    __table_args__ = (
        # "All failed payments for an order" — core RecoverAI query
        Index("ix_payments_order_status", "order_id", "status"),
        # "All failed payments for a customer" — for customer-level risk scoring
        Index("ix_payments_customer_status", "customer_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} order_id={self.order_id} "
            f"amount={self.amount} status={self.status!r}>"
        )
