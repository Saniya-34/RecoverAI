"""
AgentAction model — records what the AI agent decided to do for a RecoveryCase.

This model is a decision/result log only — it does NOT execute anything.
Actual execution of recovery actions (sending emails, retrying payments, etc.)
will be implemented in future stages.

RecoverAI needs this to:
- Store every decision the agent makes, with its reasoning
- Track whether an action was executed successfully
- Feed the audit trail with structured, explainable decisions
- Allow the agent to inspect prior actions before choosing the next one
"""

import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class ActionType(str, enum.Enum):
    """
    Types of recovery actions the AI agent may decide to take.
    Stored as PostgreSQL ENUM — extend by adding values + migration.
    """
    RETRY_PAYMENT    = "RETRY_PAYMENT"
    SEND_PAYMENT_LINK = "SEND_PAYMENT_LINK"
    SEND_REMINDER    = "SEND_REMINDER"
    WAIT             = "WAIT"
    ESCALATE         = "ESCALATE"
    STOP             = "STOP"


class ActionStatus(str, enum.Enum):
    """
    Execution status of the action.
    PENDING → EXECUTED | FAILED | SKIPPED
    """
    PENDING   = "PENDING"
    EXECUTED  = "EXECUTED"
    FAILED    = "FAILED"
    SKIPPED   = "SKIPPED"


class AgentAction(Base):
    __tablename__ = "agent_actions"

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ------------------------------------------------------------------ #
    # Foreign key to RecoveryCase                                          #
    # ------------------------------------------------------------------ #
    recovery_case_id: Mapped[int] = mapped_column(
        ForeignKey("recovery_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # What the agent decided                                               #
    # ------------------------------------------------------------------ #
    action_type: Mapped[ActionType] = mapped_column(
        Enum(ActionType, name="action_type", create_type=True),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Why the agent made this decision — explainability field             #
    # Stored as TEXT to allow rich LLM reasoning output                  #
    # ------------------------------------------------------------------ #
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------ #
    # Execution status                                                     #
    # ------------------------------------------------------------------ #
    status: Mapped[ActionStatus] = mapped_column(
        Enum(ActionStatus, name="action_status", create_type=True),
        nullable=False,
        default=ActionStatus.PENDING,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # When the action was actually executed (null until execution)        #
    # ------------------------------------------------------------------ #
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ------------------------------------------------------------------ #
    # Structured result of execution — e.g. gateway response, error msg  #
    # JSON allows flexible schema per action type                         #
    # ------------------------------------------------------------------ #
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # ------------------------------------------------------------------ #
    # Timestamps                                                           #
    # ------------------------------------------------------------------ #
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    recovery_case: Mapped["RecoveryCase"] = relationship(  # noqa: F821
        "RecoveryCase", back_populates="agent_actions"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # noqa: F821
        "AuditLog", back_populates="agent_action"
    )

    # ------------------------------------------------------------------ #
    # Index — "all actions for a case ordered by creation" is the        #
    # agent's primary lookup when deciding the next action               #
    # ------------------------------------------------------------------ #
    __table_args__ = (
        Index("ix_agent_actions_case_status", "recovery_case_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentAction id={self.id} type={self.action_type.value!r} "
            f"status={self.status.value!r} case_id={self.recovery_case_id}>"
        )
