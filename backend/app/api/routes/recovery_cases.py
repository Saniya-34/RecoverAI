"""
backend/app/api/routes/recovery_cases.py

Read endpoints for RecoveryCase.

GET /api/recovery-cases/{case_id}
    Returns full case detail including customer, order, and payment context.
    Intended for consumption by the AI agent in Stage 5+.

GET /api/recovery-cases
    Returns a paginated, filterable list of recovery cases.
    Supports ?status= and ?type= query parameters.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.database.dependencies import get_db
from backend.app.models.recovery_case import CaseStatus, CaseType, RecoveryCase
from backend.app.schemas.revenue_risk import (
    CustomerSummary,
    OrderSummary,
    PaymentSummary,
    RecoveryCaseListResponse,
    RecoveryCaseResponse,
)

router = APIRouter(prefix="/api", tags=["recovery-cases"])


# ── Explanation builder ───────────────────────────────────────────────────────

_BASE_EXPLANATIONS: dict[CaseType, str] = {
    CaseType.PAYMENT_FAILURE:      "Payment failed while the order remains unpaid.",
    CaseType.CHECKOUT_ABANDONMENT: "Checkout was abandoned before successful payment.",
    CaseType.SUBSCRIPTION_FAILURE: "Recurring subscription payment failed.",
    CaseType.OTHER:                "Revenue at risk — see case details.",
}

_STATUS_SUFFIXES: dict[CaseStatus, str] = {
    CaseStatus.RECOVERED:     " Case has been recovered.",
    CaseStatus.NOT_RECOVERED: " Recovery was not successful.",
    CaseStatus.STOPPED:       " Recovery was stopped.",
}


def _explain(case: RecoveryCase) -> str:
    base = _BASE_EXPLANATIONS.get(case.case_type, "Revenue at risk.")
    return base + _STATUS_SUFFIXES.get(case.status, "")


# ── Response builder ──────────────────────────────────────────────────────────

def _to_response(case: RecoveryCase) -> RecoveryCaseResponse:
    return RecoveryCaseResponse(
        id=case.id,
        case_type=case.case_type.value,
        status=case.status.value,
        risk_amount=case.risk_amount,
        currency="INR",
        detected_at=case.detected_at,
        resolved_at=case.resolved_at,
        explanation=_explain(case),
        customer=CustomerSummary(
            id=case.customer.id,
            external_customer_id=case.customer.external_customer_id,
            name=case.customer.name,
            email=case.customer.email,
        ),
        order=OrderSummary(
            id=case.order.id,
            external_order_id=case.order.external_order_id,
            amount=case.order.amount,
            currency=case.order.currency,
            status=case.order.status,
        ),
        payment=(
            PaymentSummary(
                id=case.payment.id,
                external_payment_id=case.payment.external_payment_id,
                amount=case.payment.amount,
                currency=case.payment.currency,
                status=case.payment.status,
                failure_reason=case.payment.failure_reason,
                payment_method=case.payment.payment_method,
            )
            if case.payment
            else None
        ),
    )


# ── Query helper ──────────────────────────────────────────────────────────────

def _with_eager_loads(stmt: Select) -> Select:
    """Apply selectinload for all required relationships."""
    return stmt.options(
        selectinload(RecoveryCase.customer),
        selectinload(RecoveryCase.order),
        selectinload(RecoveryCase.payment),
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get(
    "/recovery-cases/{case_id}",
    response_model=RecoveryCaseResponse,
    summary="Get a single recovery case by ID",
    description=(
        "Returns full details of one RecoveryCase including customer, order, "
        "and payment context. Intended for consumption by the AI agent."
    ),
)
def get_recovery_case(
    case_id: int,
    db: Session = Depends(get_db),
) -> RecoveryCaseResponse:
    case = db.execute(
        _with_eager_loads(
            select(RecoveryCase).where(RecoveryCase.id == case_id)
        )
    ).scalars().first()

    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RecoveryCase {case_id} not found.",
        )

    return _to_response(case)


@router.get(
    "/recovery-cases",
    response_model=RecoveryCaseListResponse,
    summary="List recovery cases",
    description=(
        "Returns a paginated list of recovery cases. "
        "Optionally filter by ?status= and/or ?type=."
    ),
)
def list_recovery_cases(
    case_status: str | None = Query(
        None,
        alias="status",
        description="Filter by status: OPEN, IN_PROGRESS, RECOVERED, NOT_RECOVERED, STOPPED",
    ),
    case_type: str | None = Query(
        None,
        alias="type",
        description="Filter by type: PAYMENT_FAILURE, CHECKOUT_ABANDONMENT, SUBSCRIPTION_FAILURE, OTHER",
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum records to return."),
    offset: int = Query(0, ge=0, description="Number of records to skip."),
    db: Session = Depends(get_db),
) -> RecoveryCaseListResponse:

    stmt: Select = select(RecoveryCase)

    if case_status:
        try:
            stmt = stmt.where(RecoveryCase.status == CaseStatus(case_status))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid status '{case_status}'. "
                    f"Valid values: {[s.value for s in CaseStatus]}"
                ),
            )

    if case_type:
        try:
            stmt = stmt.where(RecoveryCase.case_type == CaseType(case_type))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid type '{case_type}'. "
                    f"Valid values: {[t.value for t in CaseType]}"
                ),
            )

    # Total count without pagination
    total: int = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar() or 0

    # Paginated results with eager-loaded relationships
    cases = db.execute(
        _with_eager_loads(
            stmt.order_by(RecoveryCase.detected_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return RecoveryCaseListResponse(
        total=total,
        cases=[_to_response(c) for c in cases],
    )
