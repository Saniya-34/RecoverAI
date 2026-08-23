"""
AuditLog model — immutable history of all important system and agent events.

Every significant action (agent decision, status change, recovery attempt)
must produce an audit log entry. This table is append-only by convention:
rows are never updated or deleted.

RecoverAI needs this to:
- Provide a complete, traceable history of every recovery decision
- Demonstrate explainability (required for trust in an AI-driven system)
- Support compliance / debugging / post-mortem analysis
- Allow reconstruction of the exact sequence of events for any case
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # Foreign keys — both nullable so we can log system-wide events too  #
    # ------------------------------------------------------------------ #
    recovery_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("recovery_cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_action_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_actions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # What happened — free-form string, e.g.                             #
    # "CASE_OPENED", "ACTION_EXECUTED", "PAYMENT_RETRIED", "CASE_CLOSED" #
    # Kept as VARCHAR (not enum) so new event types need no migration     #
    # ------------------------------------------------------------------ #
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )

    # ------------------------------------------------------------------ #
    # Who/what caused this event                                          #
    # e.g. "AGENT", "SYSTEM", "WEBHOOK", "MANUAL:admin@example.com"     #
    # ------------------------------------------------------------------ #
    actor: Mapped[str] = mapped_column(String(255), nullable=False)

    # ------------------------------------------------------------------ #
    # Rich structured details — JSON for maximum flexibility             #
    # e.g. {"old_status": "OPEN", "new_status": "IN_PROGRESS",           #
    #        "reason": "Agent selected RETRY_PAYMENT"}                   #
    # ------------------------------------------------------------------ #
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # ------------------------------------------------------------------ #
    # Timestamp — created_at only; audit logs are never updated          #
    # ------------------------------------------------------------------ #
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    recovery_case: Mapped["RecoveryCase | None"] = relationship(  # noqa: F821
        "RecoveryCase", back_populates="audit_logs"
    )
    agent_action: Mapped["AgentAction | None"] = relationship(  # noqa: F821
        "AgentAction", back_populates="audit_logs"
    )

    # ------------------------------------------------------------------ #
    # Composite index — "full audit trail for a case ordered by time"    #
    # is the primary read pattern                                         #
    # ------------------------------------------------------------------ #
    __table_args__ = (
        Index("ix_audit_logs_case_created", "recovery_case_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} event={self.event_type!r} "
            f"actor={self.actor!r} case_id={self.recovery_case_id}>"
        )
