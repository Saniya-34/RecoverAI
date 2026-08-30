"""
RecoveryCase model — the central entity of RecoverAI.

Represents one detected revenue-at-risk situation.
Each case ties together a customer, an order, and optionally a specific
payment, and tracks the full lifecycle from detection to resolution.

RecoverAI needs this to:
- Record every revenue-at-risk event in one place
- Track the status of recovery attempts over time
- Know how much money is at stake (risk_amount)
- Link to the AI agent's decisions (AgentAction) and the audit trail
"""

import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class CaseType(str, enum.Enum):
    """
    What kind of revenue-at-risk event triggered this case.
    Stored as a PostgreSQL ENUM — extend by adding values + migration.
    """
    PAYMENT_FAILURE       = "PAYMENT_FAILURE"
    CHECKOUT_ABANDONMENT  = "CHECKOUT_ABANDONMENT"
    SUBSCRIPTION_FAILURE  = "SUBSCRIPTION_FAILURE"
    OTHER                 = "OTHER"


class CaseStatus(str, enum.Enum):
    """
    Lifecycle status of a RecoveryCase.
    OPEN → IN_PROGRESS → RECOVERED | NOT_RECOVERED | STOPPED
    """
    OPEN           = "OPEN"
    IN_PROGRESS    = "IN_PROGRESS"
    RECOVERED      = "RECOVERED"
    NOT_RECOVERED  = "NOT_RECOVERED"
    STOPPED        = "STOPPED"


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # Foreign keys                                                         #
    # ------------------------------------------------------------------ #
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # payment_id is optional — checkout abandonment has no payment yet
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Case classification                                                  #
    # ------------------------------------------------------------------ #
    case_type: Mapped[CaseType] = mapped_column(
        Enum(CaseType, name="case_type", create_type=True),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Revenue at stake — NUMERIC, never FLOAT                             #
    # ------------------------------------------------------------------ #
    risk_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    recovered_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False, default=Decimal("0.00")
    )


    # ------------------------------------------------------------------ #
    # Lifecycle status                                                     #
    # ------------------------------------------------------------------ #
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, name="case_status", create_type=True),
        nullable=False,
        default=CaseStatus.OPEN,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Timestamps                                                           #
    # ------------------------------------------------------------------ #
    # detected_at: when RecoverAI first identified this revenue risk
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    # resolved_at: when the case reached a terminal status
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    customer: Mapped["Customer"] = relationship(  # noqa: F821
        "Customer", back_populates="recovery_cases"
    )
    order: Mapped["Order"] = relationship(  # noqa: F821
        "Order", back_populates="recovery_cases"
    )
    payment: Mapped["Payment | None"] = relationship(  # noqa: F821
        "Payment", back_populates="recovery_cases"
    )
    agent_actions: Mapped[list["AgentAction"]] = relationship(  # noqa: F821
        "AgentAction", back_populates="recovery_case", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # noqa: F821
        "AuditLog", back_populates="recovery_case", cascade="all, delete-orphan"
    )

    # ------------------------------------------------------------------ #
    # Composite indexes for common agent queries                           #
    # ------------------------------------------------------------------ #
    __table_args__ = (
        # "Open cases for a customer" — agent polling query
        Index("ix_recovery_cases_customer_status", "customer_id", "status"),
        # "Open cases by type" — batch processing
        Index("ix_recovery_cases_type_status", "case_type", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<RecoveryCase id={self.id} type={self.case_type.value!r} "
            f"status={self.status.value!r} risk_amount={self.risk_amount}>"
        )
