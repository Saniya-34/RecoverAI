"""
backend/app/api/routes/audit.py

GET /api/recovery-cases/{case_id}/audit

Returns the audit trail for a RecoveryCase — all AuditLog rows in
chronological order. Used by the dashboard audit history panel.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database.dependencies import get_db
from backend.app.models.audit_log import AuditLog
from backend.app.models.recovery_case import RecoveryCase

router = APIRouter(prefix="/api", tags=["audit"])


class AuditLogEntry(BaseModel):
    id: int
    event_type: str
    actor: str
    details: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditTrailResponse(BaseModel):
    case_id: int
    total: int
    entries: list[AuditLogEntry]


@router.get(
    "/recovery-cases/{case_id}/audit",
    response_model=AuditTrailResponse,
    summary="Get audit trail for a recovery case",
    description=(
        "Returns all AuditLog entries for the specified RecoveryCase "
        "in chronological order. Used by the dashboard audit history panel."
    ),
)
def get_case_audit(
    case_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> AuditTrailResponse:

    # Verify the case exists
    case = db.get(RecoveryCase, case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RecoveryCase {case_id} not found.",
        )

    logs = db.execute(
        select(AuditLog)
        .where(AuditLog.recovery_case_id == case_id)
        .order_by(AuditLog.created_at.asc())
        .limit(limit)
    ).scalars().all()

    total = db.execute(
        select(AuditLog)
        .where(AuditLog.recovery_case_id == case_id)
    ).scalars()

    return AuditTrailResponse(
        case_id=case_id,
        total=len(logs),
        entries=[
            AuditLogEntry(
                id=log.id,
                event_type=log.event_type,
                actor=log.actor,
                details=log.details,
                created_at=log.created_at,
            )
            for log in logs
        ],
    )
