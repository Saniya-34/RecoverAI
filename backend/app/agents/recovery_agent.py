"""
backend/app/agents/recovery_agent.py

RecoveryAgent — high-level entry point for the LangGraph workflow.

The FastAPI route calls RecoveryAgent.run(case_id, db).
GeminiService is injected optionally for testing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.app.agents.graph import build_recovery_graph
from backend.app.models.recovery_case import CaseStatus, RecoveryCase
from backend.app.schemas.recovery_agent import ActionResult, AgentRunResponse
from backend.app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)

ELIGIBLE_STATUSES = frozenset({CaseStatus.OPEN, CaseStatus.IN_PROGRESS})


@dataclass
class AgentRunResult:
    success: bool
    response: AgentRunResponse | None
    error: str | None = None


class RecoveryAgent:
    """
    Orchestrates the LangGraph recovery workflow.

    Usage:
        agent = RecoveryAgent()
        result = agent.run(case_id=42, db=session)

    For testing, inject a mock GeminiService:
        agent = RecoveryAgent(gemini_service=mock_service)
    """

    def __init__(self, gemini_service: GeminiService | None = None) -> None:
        """
        gemini_service : Injectable mock for testing.
                         If None, the graph creates a real GeminiService.
        """
        self._gemini_service = gemini_service

    def run(self, case_id: int, db: Session) -> AgentRunResult:
        """
        Run the full recovery workflow for one RecoveryCase.

        Commits the transaction on success; rolls back on unhandled error.
        """
        # Pre-flight validation
        case = db.get(RecoveryCase, case_id)
        if not case:
            return AgentRunResult(
                success=False,
                response=None,
                error=f"RecoveryCase {case_id} not found.",
            )

        if case.status not in ELIGIBLE_STATUSES:
            return AgentRunResult(
                success=False,
                response=None,
                error=(
                    f"RecoveryCase {case_id} has status '{case.status.value}' "
                    f"and is not eligible. "
                    f"Only {[s.value for s in ELIGIBLE_STATUSES]} cases can be processed."
                ),
            )

        logger.info(
            "RecoveryAgent: starting workflow for case %d (type=%s risk=₹%s)",
            case_id, case.case_type.value, case.risk_amount,
        )

        try:
            graph = build_recovery_graph(db, gemini_service=self._gemini_service)
            final_state = graph.invoke(
                {
                    "recovery_case_id": case_id,
                    "errors": [],
                    "audit_events": [],
                    "completed": False,
                },
                config={"recursion_limit": 10},
            )
            db.commit()
            logger.info("RecoveryAgent: workflow complete for case %d", case_id)

        except Exception as exc:
            db.rollback()
            logger.error("RecoveryAgent: unhandled error for case %d — %s", case_id, exc)
            return AgentRunResult(
                success=False,
                response=None,
                error=f"Agent workflow error: {exc}",
            )

        action_result_dict = final_state.get("action_result") or {
            "success": False,
            "action": final_state.get("final_action", "STOP"),
            "simulated": True,
            "message": "No action was executed.",
        }

        response = AgentRunResponse(
            case_id=case_id,
            decision=final_state.get("final_decision", "STOP"),
            action=final_state.get("final_action", "STOP"),
            risk_amount=Decimal(final_state.get("risk_amount", "0")),
            currency=final_state.get("currency", "INR"),
            confidence=final_state.get("confidence", 0.0),
            reason=final_state.get("decision_reason") or final_state.get("policy_reason", ""),
            evidence=final_state.get("evidence", []),
            action_result=ActionResult(
                success=action_result_dict.get("success", False),
                action=action_result_dict.get("action", "STOP"),
                simulated=action_result_dict.get("simulated", True),
                message=action_result_dict.get("message"),
            ),
            policy_override=final_state.get("policy_overridden", False),
            agent_action_id=final_state.get("agent_action_id"),
            completed_at=datetime.now(timezone.utc),
        )

        return AgentRunResult(success=True, response=response)
