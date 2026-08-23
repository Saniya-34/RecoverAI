"""
Order model — represents a purchase/transaction made by a customer.

RecoverAI needs this to:
- Know what revenue is at stake when a payment fails
- Link failed payments back to the originating order
- Calculate the risk_amount for a RecoveryCase
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class Order(Base):
    __tablename__ = "orders"

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # External reference — merchant's own order/invoice identifier         #
    # ------------------------------------------------------------------ #
    external_order_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    # ------------------------------------------------------------------ #
    # Foreign key to Customer                                              #
    # ------------------------------------------------------------------ #
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Financials — NEVER floating-point for money                         #
    # NUMERIC(12, 2) supports up to 9,999,999,999.99                      #
    # ------------------------------------------------------------------ #
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    # ------------------------------------------------------------------ #
    # Order status — stored as plain string, validated at app layer.      #
    # Keeping it a VARCHAR (not a DB enum) makes future extension easy.   #
    # ------------------------------------------------------------------ #
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING", index=True
    )

    # ------------------------------------------------------------------ #
    # Timestamps                                                           #
    # ------------------------------------------------------------------ #
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
    customer: Mapped["Customer"] = relationship(  # noqa: F821
        "Customer", back_populates="orders"
    )
    payments: Mapped[list["Payment"]] = relationship(  # noqa: F821
        "Payment", back_populates="order", cascade="all, delete-orphan"
    )
    checkout_events: Mapped[list["CheckoutEvent"]] = relationship(  # noqa: F821
        "CheckoutEvent", back_populates="order", cascade="all, delete-orphan"
    )
    recovery_cases: Mapped[list["RecoveryCase"]] = relationship(  # noqa: F821
        "RecoveryCase", back_populates="order"
    )

    # ------------------------------------------------------------------ #
    # Extra composite index — common query: "all orders for a customer    #
    # with a given status"                                                 #
    # ------------------------------------------------------------------ #
    __table_args__ = (
        Index("ix_orders_customer_status", "customer_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Order id={self.id} external_id={self.external_order_id!r} "
            f"amount={self.amount} {self.currency} status={self.status!r}>"
        )
