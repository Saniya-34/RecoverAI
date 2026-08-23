"""
backend/app/schemas/revenue_risk.py

Pydantic schemas for the RecoveryCase read API.

GET /api/recovery-cases/{case_id}
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class CustomerSummary(BaseModel):
    id: int
    external_customer_id: str
    name: str | None
    email: str | None

    model_config = {"from_attributes": True}


class OrderSummary(BaseModel):
    id: int
    external_order_id: str
    amount: Decimal
    currency: str
    status: str

    model_config = {"from_attributes": True}


class PaymentSummary(BaseModel):
    id: int
    external_payment_id: str | None
    amount: Decimal
    currency: str
    status: str
    failure_reason: str | None
    payment_method: str | None

    model_config = {"from_attributes": True}


class RecoveryCaseResponse(BaseModel):
    """
    Full recovery case detail — consumed by the GET endpoint and
    later by the AI agent.
    """

    id: int
    case_type: str
    status: str
    risk_amount: Decimal
    currency: str = "INR"
    detected_at: datetime
    resolved_at: datetime | None
    explanation: str

    customer: CustomerSummary
    order: OrderSummary
    payment: PaymentSummary | None

    model_config = {"from_attributes": True}


class RecoveryCaseListResponse(BaseModel):
    total: int
    cases: list[RecoveryCaseResponse]
