"""
backend/app/api/routes/events.py

POST /api/events — merchant event ingestion endpoint.

Flow
────
Request → EventRequest schema validation
        → EventProcessor.process()
            → idempotency check
            → resolve/create Customer, Order, Payment
            → persist CheckoutEvent
            → RevenueRiskDetector.evaluate()
        → EventResponse
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database.dependencies import get_db
from backend.app.schemas.event import EventRequest, EventResponse
from backend.app.services.event_processor import EventProcessor

router = APIRouter(prefix="/api", tags=["events"])


@router.post(
    "/events",
    response_model=EventResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest a merchant/payment event",
    description=(
        "Accepts a single merchant event (checkout start, payment attempt, etc.), "
        "stores it, and runs deterministic revenue-at-risk detection. "
        "Idempotent: submitting the same external_event_id twice returns a "
        "duplicate=true response without creating duplicate records."
    ),
)
def ingest_event(
    req: EventRequest,
    db: Session = Depends(get_db),
) -> EventResponse:
    try:
        with db.begin():
            processor = EventProcessor(db)
            result = processor.process(req)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    det = result.detection
    rc = det.recovery_case

    return EventResponse(
        event_processed=result.event_processed,
        duplicate=result.duplicate,
        revenue_at_risk=det.revenue_at_risk,
        risk_amount=rc.risk_amount if rc else None,
        currency="INR",
        case_id=rc.id if rc else None,
        case_type=rc.case_type.value if rc else None,
        case_status=rc.status.value if rc else None,
        reason=det.reason,
    )
