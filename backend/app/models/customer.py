"""
Customer model — represents a merchant's customer who makes purchases.

RecoverAI needs this to:
- Identify who is at risk of churning or has a failed payment
- Link orders, payments, and checkout events to a real person
- Personalise recovery actions (email, SMS, payment links)
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # External reference — the merchant's own customer identifier          #
    # Unique + indexed because we'll look customers up by this often.      #
    # ------------------------------------------------------------------ #
    external_customer_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    # ------------------------------------------------------------------ #
    # Identity fields                                                      #
    # ------------------------------------------------------------------ #
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Email is also queried frequently (recovery comms)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

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
    orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        "Order", back_populates="customer", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(  # noqa: F821
        "Payment", back_populates="customer", cascade="all, delete-orphan"
    )
    checkout_events: Mapped[list["CheckoutEvent"]] = relationship(  # noqa: F821
        "CheckoutEvent", back_populates="customer", cascade="all, delete-orphan"
    )
    recovery_cases: Mapped[list["RecoveryCase"]] = relationship(  # noqa: F821
        "RecoveryCase", back_populates="customer"
    )

    # ------------------------------------------------------------------ #
    # Extra indexes                                                        #
    # ------------------------------------------------------------------ #
    __table_args__ = (
        Index("ix_customers_email_name", "email", "name"),
    )

    def __repr__(self) -> str:
        return f"<Customer id={self.id} external_id={self.external_customer_id!r}>"
