"""
backend/app/api/dashboard.py

GET /api/dashboard/summary

Returns aggregated merchant metrics for the dashboard summary cards.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database.dependencies import get_db
from backend.app.models.recovery_case import CaseStatus, RecoveryCase

router = APIRouter(prefix="/api", tags=["dashboard"])


class DashboardSummary(BaseModel):
    total_revenue_at_risk: Decimal
    total_cases: int
    open_cases: int
    in_progress_cases: int
    recovered_cases: int
    stopped_cases: int
    recovered_revenue: Decimal
    currency: str = "INR"
    note: str = (
        "recovered_revenue represents simulated recovered revenue from successful recovery cases."
    )


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummary,
    summary="Get merchant dashboard summary",
    description=(
        "Returns aggregated revenue-at-risk metrics for the dashboard, including simulated recovered revenue."
    ),
)
def get_dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummary:

    # Total revenue at risk (all OPEN + IN_PROGRESS cases)
    at_risk_row = db.execute(
        select(func.coalesce(func.sum(RecoveryCase.risk_amount), 0)).where(
            RecoveryCase.status.in_([CaseStatus.OPEN, CaseStatus.IN_PROGRESS])
        )
    ).scalar()

    total_cases = db.execute(
        select(func.count(RecoveryCase.id))
    ).scalar() or 0

    open_cases = db.execute(
        select(func.count(RecoveryCase.id)).where(
            RecoveryCase.status == CaseStatus.OPEN
        )
    ).scalar() or 0

    in_progress = db.execute(
        select(func.count(RecoveryCase.id)).where(
            RecoveryCase.status == CaseStatus.IN_PROGRESS
        )
    ).scalar() or 0

    recovered = db.execute(
        select(func.count(RecoveryCase.id)).where(
            RecoveryCase.status == CaseStatus.RECOVERED
        )
    ).scalar() or 0

    stopped = db.execute(
        select(func.count(RecoveryCase.id)).where(
            RecoveryCase.status == CaseStatus.STOPPED
        )
    ).scalar() or 0

    recovered_revenue = db.execute(
        select(func.coalesce(func.sum(RecoveryCase.recovered_amount), 0))
    ).scalar() or 0

    return DashboardSummary(
        total_revenue_at_risk=Decimal(str(at_risk_row or 0)),
        total_cases=total_cases,
        open_cases=open_cases,
        in_progress_cases=in_progress,
        recovered_cases=recovered,
        stopped_cases=stopped,
        recovered_revenue=Decimal(str(recovered_revenue)),
    )
