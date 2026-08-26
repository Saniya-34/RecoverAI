import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.database import engine
from backend.app.main import app
from backend.app.models.customer import Customer
from backend.app.models.order import Order
from backend.app.models.payment import Payment
from backend.app.models.recovery_case import CaseStatus, CaseType, RecoveryCase
from backend.app.models.agent_action import AgentAction, ActionType, ActionStatus

client = TestClient(app)


def uid():
    return str(uuid.uuid4())[:10]


def _now():
    return datetime.now(timezone.utc)


def _setup_test_data(db: Session):
    now = _now()
    # 1. Create a customer
    customer = Customer(
        external_customer_id=f"CUST-{uid()}",
        name="Test Customer",
        email="test@example.com",
        created_at=now,
        updated_at=now,
    )
    db.add(customer)
    db.flush()

    # 2. Create 3 payments for this customer
    # Order 1 (Failed Payment)
    order1 = Order(
        external_order_id=f"ORD1-{uid()}",
        customer_id=customer.id,
        amount=Decimal("1500.00"),
        currency="INR",
        status="FAILED",
        created_at=now,
        updated_at=now,
    )
    db.add(order1)
    db.flush()

    p1 = Payment(
        external_payment_id=f"PAY1-{uid()}",
        order_id=order1.id,
        customer_id=customer.id,
        amount=Decimal("1500.00"),
        currency="INR",
        status="FAILED",
        failure_reason="INSUFFICIENT_FUNDS",
        payment_method="CARD",
        attempted_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(p1)

    p2 = Payment(
        external_payment_id=f"PAY2-{uid()}",
        order_id=order1.id,
        customer_id=customer.id,
        amount=Decimal("1500.00"),
        currency="INR",
        status="SUCCESS",
        payment_method="UPI",
        attempted_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(p2)

    # Order 2 (Failed, becomes recovery case 1)
    order2 = Order(
        external_order_id=f"ORD2-{uid()}",
        customer_id=customer.id,
        amount=Decimal("2000.00"),
        currency="INR",
        status="FAILED",
        created_at=now,
        updated_at=now,
    )
    db.add(order2)
    db.flush()

    p3 = Payment(
        external_payment_id=f"PAY3-{uid()}",
        order_id=order2.id,
        customer_id=customer.id,
        amount=Decimal("2000.00"),
        currency="INR",
        status="FAILED",
        failure_reason="CARD_EXPIRED",
        payment_method="CARD",
        attempted_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(p3)
    db.flush()

    # Recovery case 1 (Other / Previous case)
    rc1 = RecoveryCase(
        customer_id=customer.id,
        order_id=order2.id,
        payment_id=p3.id,
        case_type=CaseType.PAYMENT_FAILURE,
        risk_amount=Decimal("2000.00"),
        status=CaseStatus.NOT_RECOVERED,
        detected_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(rc1)
    db.flush()

    # Add agent actions to recovery case 1
    action1 = AgentAction(
        recovery_case_id=rc1.id,
        action_type=ActionType.RETRY_PAYMENT,
        reason="Retrying card",
        status=ActionStatus.EXECUTED,
        executed_at=now,
        created_at=now,
    )
    action2 = AgentAction(
        recovery_case_id=rc1.id,
        action_type=ActionType.STOP,
        reason="Failed twice",
        status=ActionStatus.EXECUTED,
        executed_at=now,
        created_at=now,
    )
    db.add(action1)
    db.add(action2)

    # Order 3 (Current open case)
    order3 = Order(
        external_order_id=f"ORD3-{uid()}",
        customer_id=customer.id,
        amount=Decimal("3500.00"),
        currency="INR",
        status="FAILED",
        created_at=now,
        updated_at=now,
    )
    db.add(order3)
    db.flush()

    p4 = Payment(
        external_payment_id=f"PAY4-{uid()}",
        order_id=order3.id,
        customer_id=customer.id,
        amount=Decimal("3500.00"),
        currency="INR",
        status="FAILED",
        failure_reason="NETWORK_ERROR",
        payment_method="CARD",
        attempted_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(p4)
    db.flush()

    rc_current = RecoveryCase(
        customer_id=customer.id,
        order_id=order3.id,
        payment_id=p4.id,
        case_type=CaseType.PAYMENT_FAILURE,
        risk_amount=Decimal("3500.00"),
        status=CaseStatus.OPEN,
        detected_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(rc_current)
    db.flush()

    return rc_current.id, customer.id


def test_get_customer_history_success():
    with Session(engine) as db:
        with db.begin():
            case_id, customer_id = _setup_test_data(db)

    response = client.get(f"/api/recovery-cases/{case_id}/customer-history")
    assert response.status_code == 200
    data = response.json()

    # Aggregates validation
    # total payment attempts = 4 (p1, p2, p3, p4)
    assert data["total_payment_attempts"] == 4
    # successful = 1 (p2)
    assert data["successful_payments"] == 1
    # failed = 3 (p1, p3, p4)
    assert data["failed_payments"] == 3
    # success_rate = 1/4 = 0.25
    assert data["success_rate"] == 0.25
    # previous recovery attempts (AgentAction instances of OTHER recovery cases of this customer)
    # action1 and action2 belong to rc1 (which is not current case_id)
    assert data["previous_recovery_attempts"] == 2

    # Payments list validation
    assert len(data["payments"]) == 4
    # Check failure reason is passed
    failed_reasons = [p["failure_reason"] for p in data["payments"] if p["failure_reason"]]
    assert "INSUFFICIENT_FUNDS" in failed_reasons
    assert "CARD_EXPIRED" in failed_reasons
    assert "NETWORK_ERROR" in failed_reasons


def test_get_customer_history_404():
    response = client.get("/api/recovery-cases/999999/customer-history")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
