"""
backend/app/api/routes/agent.py

POST /api/recovery-cases/{case_id}/run-agent

Triggers the LangGraph recovery agent for a single RecoveryCase.

Flow
────
1. Validate case exists and is eligible (OPEN or IN_PROGRESS).
2. Run RecoveryAgent.run() — full LangGraph workflow.
3. Return AgentRunResponse (no internal chain-of-thought exposed).

The route does NOT own the transaction — RecoveryAgent.run() commits
or rolls back internally after the graph completes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.agents.recovery_agent import RecoveryAgent
from backend.app.database.dependencies import get_db
from backend.app.schemas.recovery_agent import AgentRunResponse

router = APIRouter(prefix="/api", tags=["agent"])


@router.post(
    "/recovery-cases/{case_id}/run-agent",
    response_model=AgentRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run the AI recovery agent on a case",
    description=(
        "Triggers the LangGraph recovery agent for the specified RecoveryCase. "
        "The agent investigates the case, asks Gemini for a recovery decision, "
        "validates it through a deterministic policy gate, executes a simulated "
        "action, and records the result. "
        "Only OPEN or IN_PROGRESS cases are eligible."
    ),
)
def run_agent(
    case_id: int,
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    agent = RecoveryAgent()
    result = agent.run(case_id=case_id, db=db)

    if not result.success:
        # Distinguish 404 from other errors
        if result.error and "not found" in result.error.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.error,
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.error or "Agent workflow failed.",
        )

    return result.response
