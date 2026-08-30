"""
backend/app/schemas/recovery_agent.py

Pydantic schemas for the AI recovery agent.

These schemas define the contract between:
- The LangGraph agent and the Gemini model (structured output)
- The FastAPI route and the caller (HTTP response)

The Gemini model MUST return a RecoveryDecision.
The agent route returns an AgentRunResponse.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ── Constants ─────────────────────────────────────────────────────────────────

ALLOWED_DECISIONS = frozenset({"RECOVER", "WAIT", "STOP"})

ALLOWED_ACTIONS = frozenset({
    "RETRY_PAYMENT",
    "SEND_PAYMENT_LINK",
    "SEND_REMINDER",
    "WAIT",
    "STOP",
})

# Maps each decision to the actions it permits
DECISION_ACTION_MAP: dict[str, frozenset[str]] = {
    "RECOVER": frozenset({"RETRY_PAYMENT", "SEND_PAYMENT_LINK", "SEND_REMINDER"}),
    "WAIT":    frozenset({"WAIT"}),
    "STOP":    frozenset({"STOP"}),
}


# ── Structured LLM output ─────────────────────────────────────────────────────

class RecoveryDecision(BaseModel):
    """
    Structured output the Gemini model must produce.

    Validated before any action is executed so the agent can never
    act on a malformed or hallucinated model response.
    """

    decision: Literal["RECOVER", "WAIT", "STOP"] = Field(
        ...,
        description="Top-level recovery decision.",
    )
    action: Literal[
        "RETRY_PAYMENT",
        "SEND_PAYMENT_LINK",
        "SEND_REMINDER",
        "WAIT",
        "STOP",
    ] = Field(
        ...,
        description="Specific action to execute. Must be consistent with decision.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence in the decision (0.0 – 1.0).",
    )
    reason: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Short human-readable explanation of the decision.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Specific facts from the database used to reach this decision.",
    )

    @field_validator("action")
    @classmethod
    def action_must_match_decision(cls, v: str, info) -> str:
        decision = info.data.get("decision")
        if decision and v not in DECISION_ACTION_MAP.get(decision, set()):
            allowed = DECISION_ACTION_MAP.get(decision, set())
            raise ValueError(
                f"action '{v}' is not allowed for decision '{decision}'. "
                f"Allowed: {sorted(allowed)}"
            )
        return v


# ── API response ──────────────────────────────────────────────────────────────

class ActionResult(BaseModel):
    """Result of a simulated action execution."""
    success: bool
    action: str
    simulated: bool = True
    message: str | None = None
    payment_outcome: str = "WAIT"


class AgentRunResponse(BaseModel):
    """
    HTTP response from POST /api/recovery-cases/{case_id}/run-agent.

    Chain-of-thought is intentionally NOT exposed.
    Only the final decision, action, and supporting evidence are returned.
    """

    case_id: int
    decision: str
    action: str
    risk_amount: Decimal
    recovered_amount: Decimal = Decimal("0.00")
    currency: str = "INR"
    confidence: float
    reason: str
    evidence: list[str]
    action_result: ActionResult
    policy_override: bool = Field(
        False,
        description="True if the policy gate overrode the model's decision.",
    )
    agent_action_id: int | None = None
    completed_at: datetime

    model_config = {"from_attributes": True}
