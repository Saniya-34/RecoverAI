"""
Tests for Stage 4 — Merchant Simulation and Revenue-at-Risk Detection.

Tests are organised into three groups:

A. Unit tests for the RevenueRiskDetector (pure logic, uses a real DB session).
B. Integration tests via the FastAPI TestClient (full HTTP stack).
C. Idempotency and deduplication tests.

All tests use isolated data with unique external IDs so they do not
depend on seed data and do not interfere with each other.
Each test that writes data rolls back or uses independent IDs.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import engine
from backend.app.main import app
from backend.app.models.checkout_event import CheckoutEvent
from backend.app.models.customer import Customer
from backend.app.models.order import Order
from backend.app.models.payment import Payment
from backend.app.models.recovery_case import CaseStatus, CaseType, RecoveryCase
from backend.app.services.revenue_risk import RevenueRiskDetector

client = TestClient(app)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def uid() -> str:
    return str(uuid.uuid4())[:12]


def event_payload(
    event_type: str,
    *,
    customer_id: str | None = None,
    order_id: str | None = None,
    payment_id: str | None = None,
    amount: str = "2499.00",
    failure_reason: str | None = None,
    payment_method: str | None = "CARD",
    event_id: str | None = None,
) -> dict:
    p: dict = {
        "external_event_id": event_id or f"EVT-{uid()}",
        "event_type": event_type,
        "external_customer_id": customer_id or f"CUST-{uid()}",
        "external_order_id": order_id or f"ORD-{uid()}",
        "currency": "INR",
    }
    if event_type in {"CHECKOUT_STARTED", "PAYMENT_INITIATED", "PAYMENT_SUCCESS", "PAYMENT_FAILED"}:
        p["amount"] = amount
    if event_type in {"PAYMENT_INITIATED", "PAYMENT_SUCCESS", "PAYMENT_FAILED"}:
        p["external_payment_id"] = payment_id or f"PAY-{uid()}"
        p["payment_method"] = payment_method
    if event_type == "PAYMENT_FAILED":
        p["failure_reason"] = failure_reason or "temporary_bank_error"
    return p


# ──────────────────────────────────────────────────────────────────────────────
# A. Unit tests — RevenueRiskDetector
# ──────────────────────────────────────────────────────────────────────────────

class TestRevenueRiskDetector:
    """
    Tests run against a real DB session, rolled back after each test
    to keep the database clean.
    """

    @pytest.fixture(autouse=True)
    def rollback_session(self):
        """Each test gets its own transaction that is rolled back."""
        with Session(engine) as session:
            with session.begin():
                self.session = session
                self.detector = RevenueRiskDetector(session)
                yield
                session.rollback()

    def _make_customer(self) -> Customer:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        c = Customer(external_customer_id=f"UC-{uid()}", created_at=now, updated_at=now)
        self.session.add(c)
        self.session.flush()
        return c

    def _make_order(self, customer: Customer, amount: Decimal = Decimal("1000.00")) -> Order:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        o = Order(
            external_order_id=f"UO-{uid()}",
            customer_id=customer.id,
            amount=amount,
            currency="INR",
            status="PENDING",
            created_at=now,
            updated_at=now,
        )
        self.session.add(o)
        self.session.flush()
        return o

    def _make_payment(self, order: Order, customer: Customer, status: str) -> Payment:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        p = Payment(
            external_payment_id=f"UP-{uid()}",
            order_id=order.id,
            customer_id=customer.id,
            amount=order.amount,
            currency="INR",
            status=status,
            payment_method="CARD",
            attempted_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(p)
        self.session.flush()
        return p

    # ── Tests ─────────────────────────────────────────────────────────────────

    def test_payment_failed_creates_recovery_case(self):
        c = self._make_customer()
        o = self._make_order(c)
        p = self._make_payment(o, c, "FAILED")

        result = self.detector.evaluate("PAYMENT_FAILED", c, o, p)

        assert result.revenue_at_risk is True
        assert result.recovery_case is not None
        assert result.recovery_case.case_type == CaseType.PAYMENT_FAILURE
        assert result.recovery_case.status == CaseStatus.OPEN
        assert result.recovery_case.risk_amount == o.amount

    def test_payment_failed_skipped_when_order_already_paid(self):
        c = self._make_customer()
        o = self._make_order(c)
        self._make_payment(o, c, "SUCCESS")   # order already paid
        p = self._make_payment(o, c, "FAILED")

        result = self.detector.evaluate("PAYMENT_FAILED", c, o, p)

        assert result.revenue_at_risk is False
        assert result.recovery_case is None

    def test_payment_failed_deduplication(self):
        """Two PAYMENT_FAILED events for the same order → one case."""
        c = self._make_customer()
        o = self._make_order(c)
        p1 = self._make_payment(o, c, "FAILED")
        p2 = self._make_payment(o, c, "FAILED")

        r1 = self.detector.evaluate("PAYMENT_FAILED", c, o, p1)
        r2 = self.detector.evaluate("PAYMENT_FAILED", c, o, p2)

        assert r1.revenue_at_risk is True
        assert r2.revenue_at_risk is True
        # Both reference the same case
        assert r1.recovery_case.id == r2.recovery_case.id

    def test_checkout_abandoned_creates_recovery_case(self):
        c = self._make_customer()
        o = self._make_order(c, Decimal("3000.00"))

        result = self.detector.evaluate("CHECKOUT_ABANDONED", c, o, None)

        assert result.revenue_at_risk is True
        assert result.recovery_case.case_type == CaseType.CHECKOUT_ABANDONMENT
        assert result.recovery_case.risk_amount == Decimal("3000.00")

    def test_checkout_abandoned_skipped_when_paid(self):
        c = self._make_customer()
        o = self._make_order(c)
        self._make_payment(o, c, "SUCCESS")

        result = self.detector.evaluate("CHECKOUT_ABANDONED", c, o, None)

        assert result.revenue_at_risk is False
        assert result.recovery_case is None

    def test_payment_success_closes_open_case(self):
        c = self._make_customer()
        o = self._make_order(c)
        p_fail = self._make_payment(o, c, "FAILED")

        # Create the open case
        open_result = self.detector.evaluate("PAYMENT_FAILED", c, o, p_fail)
        assert open_result.recovery_case.status == CaseStatus.OPEN

        # Now payment succeeds
        p_succ = self._make_payment(o, c, "SUCCESS")
        result = self.detector.evaluate("PAYMENT_SUCCESS", c, o, p_succ)

        assert result.revenue_at_risk is False
        # Reload the case to check it was updated
        self.session.refresh(open_result.recovery_case)
        assert open_result.recovery_case.status == CaseStatus.RECOVERED

    def test_neutral_events_return_no_risk(self):
        c = self._make_customer()
        o = self._make_order(c)

        for et in ("CHECKOUT_STARTED", "PAYMENT_INITIATED"):
            result = self.detector.evaluate(et, c, o, None)
            assert result.revenue_at_risk is False
            assert result.recovery_case is None


# ──────────────────────────────────────────────────────────────────────────────
# B. Integration tests — FastAPI HTTP layer
# ──────────────────────────────────────────────────────────────────────────────

class TestEventAPI:

    def test_health_still_works(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_payment_failed_returns_risk(self):
        cust = f"CUST-{uid()}"
        order = f"ORD-{uid()}"
        pay = f"PAY-{uid()}"

        client.post("/api/events", json=event_payload(
            "CHECKOUT_STARTED", customer_id=cust, order_id=order))
        client.post("/api/events", json=event_payload(
            "PAYMENT_INITIATED", customer_id=cust, order_id=order, payment_id=pay))

        r = client.post("/api/events", json=event_payload(
            "PAYMENT_FAILED", customer_id=cust, order_id=order, payment_id=pay,
            failure_reason="insufficient_funds"))

        assert r.status_code == 200
        body = r.json()
        assert body["event_processed"] is True
        assert body["revenue_at_risk"] is True
        assert body["case_type"] == "PAYMENT_FAILURE"
        assert body["case_id"] is not None
        assert Decimal(str(body["risk_amount"])) == Decimal("2499.00")

    def test_payment_success_no_risk(self):
        cust = f"CUST-{uid()}"
        order = f"ORD-{uid()}"
        pay = f"PAY-{uid()}"

        client.post("/api/events", json=event_payload(
            "CHECKOUT_STARTED", customer_id=cust, order_id=order))
        client.post("/api/events", json=event_payload(
            "PAYMENT_INITIATED", customer_id=cust, order_id=order, payment_id=pay))
        r = client.post("/api/events", json=event_payload(
            "PAYMENT_SUCCESS", customer_id=cust, order_id=order, payment_id=pay))

        assert r.status_code == 200
        body = r.json()
        assert body["revenue_at_risk"] is False
        assert body["case_id"] is None

    def test_checkout_abandoned_creates_case(self):
        cust = f"CUST-{uid()}"
        order = f"ORD-{uid()}"

        client.post("/api/events", json=event_payload(
            "CHECKOUT_STARTED", customer_id=cust, order_id=order))
        r = client.post("/api/events", json={
            "external_event_id": f"EVT-{uid()}",
            "event_type": "CHECKOUT_ABANDONED",
            "external_customer_id": cust,
            "external_order_id": order,
        })

        assert r.status_code == 200
        body = r.json()
        assert body["revenue_at_risk"] is True
        assert body["case_type"] == "CHECKOUT_ABANDONMENT"

    def test_payment_failed_already_paid_no_risk(self):
        """Order already has a SUCCESS payment — PAYMENT_FAILED should not create a case."""
        cust = f"CUST-{uid()}"
        order = f"ORD-{uid()}"
        pay_ok = f"PAY-{uid()}"
        pay_fail = f"PAY-{uid()}"

        client.post("/api/events", json=event_payload(
            "CHECKOUT_STARTED", customer_id=cust, order_id=order))
        client.post("/api/events", json=event_payload(
            "PAYMENT_INITIATED", customer_id=cust, order_id=order, payment_id=pay_ok))
        client.post("/api/events", json=event_payload(
            "PAYMENT_SUCCESS", customer_id=cust, order_id=order, payment_id=pay_ok))

        r = client.post("/api/events", json=event_payload(
            "PAYMENT_FAILED", customer_id=cust, order_id=order, payment_id=pay_fail,
            failure_reason="network_error"))

        assert r.status_code == 200
        body = r.json()
        assert body["revenue_at_risk"] is False

    def test_failure_then_success_closes_case(self):
        cust = f"CUST-{uid()}"
        order = f"ORD-{uid()}"
        pay1 = f"PAY-{uid()}"
        pay2 = f"PAY-{uid()}"

        client.post("/api/events", json=event_payload(
            "CHECKOUT_STARTED", customer_id=cust, order_id=order))
        client.post("/api/events", json=event_payload(
            "PAYMENT_INITIATED", customer_id=cust, order_id=order, payment_id=pay1))
        fail_r = client.post("/api/events", json=event_payload(
            "PAYMENT_FAILED", customer_id=cust, order_id=order, payment_id=pay1,
            failure_reason="card_expired"))

        case_id = fail_r.json()["case_id"]
        assert case_id is not None

        client.post("/api/events", json=event_payload(
            "PAYMENT_INITIATED", customer_id=cust, order_id=order, payment_id=pay2,
            payment_method="UPI"))
        client.post("/api/events", json=event_payload(
            "PAYMENT_SUCCESS", customer_id=cust, order_id=order, payment_id=pay2,
            payment_method="UPI"))

        # Verify case is now RECOVERED
        get_r = client.get(f"/api/recovery-cases/{case_id}")
        assert get_r.status_code == 200
        assert get_r.json()["status"] == "RECOVERED"

    def test_invalid_event_type_rejected(self):
        r = client.post("/api/events", json={
            "external_event_id": f"EVT-{uid()}",
            "event_type": "BOGUS_EVENT",
            "external_customer_id": f"CUST-{uid()}",
            "external_order_id": f"ORD-{uid()}",
        })
        assert r.status_code == 422

    def test_payment_failed_missing_failure_reason_rejected(self):
        r = client.post("/api/events", json={
            "external_event_id": f"EVT-{uid()}",
            "event_type": "PAYMENT_FAILED",
            "external_customer_id": f"CUST-{uid()}",
            "external_order_id": f"ORD-{uid()}",
            "external_payment_id": f"PAY-{uid()}",
            "amount": "500.00",
            # failure_reason intentionally omitted
        })
        assert r.status_code == 422

    def test_missing_order_id_rejected(self):
        r = client.post("/api/events", json={
            "external_event_id": f"EVT-{uid()}",
            "event_type": "CHECKOUT_STARTED",
            "external_customer_id": f"CUST-{uid()}",
            "amount": "500.00",
            # external_order_id intentionally omitted
        })
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# C. Idempotency and deduplication tests
# ──────────────────────────────────────────────────────────────────────────────

class TestIdempotency:

    def test_duplicate_event_id_returns_duplicate_flag(self):
        cust = f"CUST-{uid()}"
        order = f"ORD-{uid()}"
        pay = f"PAY-{uid()}"
        fixed_eid = f"IDEM-EVT-{uid()}"

        payload = {
            "external_event_id": fixed_eid,
            "event_type": "PAYMENT_FAILED",
            "external_customer_id": cust,
            "external_order_id": order,
            "external_payment_id": pay,
            "amount": "1500.00",
            "payment_method": "CARD",
            "failure_reason": "bank_timeout",
        }

        r1 = client.post("/api/events", json=payload)
        r2 = client.post("/api/events", json=payload)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["event_processed"] is True
        assert r1.json()["duplicate"] is False
        assert r2.json()["duplicate"] is True
        assert r2.json()["event_processed"] is False

    def test_duplicate_event_no_extra_checkout_event_row(self):
        cust = f"CUST-{uid()}"
        order = f"ORD-{uid()}"
        fixed_eid = f"IDEM-EVT-{uid()}"

        payload = {
            "external_event_id": fixed_eid,
            "event_type": "CHECKOUT_STARTED",
            "external_customer_id": cust,
            "external_order_id": order,
            "amount": "999.00",
        }

        client.post("/api/events", json=payload)
        client.post("/api/events", json=payload)

        # Exactly one CheckoutEvent should exist with this event ID
        with Session(engine) as db:
            count = db.execute(
                select(CheckoutEvent).where(
                    CheckoutEvent.event_metadata["external_event_id"].as_string() == fixed_eid
                )
            ).scalars().all()
        assert len(count) == 1

    def test_multiple_failures_same_order_one_case(self):
        """Three PAYMENT_FAILED events for the same order → one OPEN case."""
        cust = f"CUST-{uid()}"
        order = f"ORD-{uid()}"

        client.post("/api/events", json=event_payload(
            "CHECKOUT_STARTED", customer_id=cust, order_id=order))

        case_ids = []
        for _ in range(3):
            pay = f"PAY-{uid()}"
            client.post("/api/events", json=event_payload(
                "PAYMENT_INITIATED", customer_id=cust, order_id=order, payment_id=pay))
            r = client.post("/api/events", json=event_payload(
                "PAYMENT_FAILED", customer_id=cust, order_id=order, payment_id=pay,
                failure_reason="insufficient_funds"))
            case_ids.append(r.json().get("case_id"))

        # All three responses should reference the same case
        assert len(set(case_ids)) == 1, f"Expected 1 unique case_id, got {set(case_ids)}"

        # Verify only one OPEN case exists for this order in the DB
        with Session(engine) as db:
            order_row = db.execute(
                select(Order).where(Order.external_order_id == order)
            ).scalars().first()
            assert order_row is not None
            cases = db.execute(
                select(RecoveryCase).where(
                    RecoveryCase.order_id == order_row.id,
                    RecoveryCase.status == CaseStatus.OPEN,
                )
            ).scalars().all()
        assert len(cases) == 1


# ──────────────────────────────────────────────────────────────────────────────
# D. RecoveryCase read API
# ──────────────────────────────────────────────────────────────────────────────

class TestRecoveryCaseAPI:

    def _create_case(self) -> int:
        """Helper: create a PAYMENT_FAILURE case and return its ID."""
        cust = f"CUST-{uid()}"
        order = f"ORD-{uid()}"
        pay = f"PAY-{uid()}"
        client.post("/api/events", json=event_payload(
            "CHECKOUT_STARTED", customer_id=cust, order_id=order))
        client.post("/api/events", json=event_payload(
            "PAYMENT_INITIATED", customer_id=cust, order_id=order, payment_id=pay))
        r = client.post("/api/events", json=event_payload(
            "PAYMENT_FAILED", customer_id=cust, order_id=order, payment_id=pay,
            failure_reason="network_error"))
        return r.json()["case_id"]

    def test_get_case_returns_full_detail(self):
        case_id = self._create_case()
        r = client.get(f"/api/recovery-cases/{case_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == case_id
        assert body["case_type"] == "PAYMENT_FAILURE"
        assert body["status"] == "OPEN"
        assert "customer" in body
        assert "order" in body
        assert "payment" in body
        assert "explanation" in body
        assert Decimal(str(body["risk_amount"])) > 0

    def test_get_case_404_for_missing(self):
        r = client.get("/api/recovery-cases/999999999")
        assert r.status_code == 404

    def test_list_cases_returns_results(self):
        self._create_case()
        r = client.get("/api/recovery-cases?status=OPEN")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        assert len(body["cases"]) >= 1

    def test_list_cases_invalid_status_rejected(self):
        r = client.get("/api/recovery-cases?status=BOGUS")
        assert r.status_code == 422

    def test_list_cases_type_filter(self):
        self._create_case()
        r = client.get("/api/recovery-cases?type=PAYMENT_FAILURE")
        assert r.status_code == 200
        body = r.json()
        for c in body["cases"]:
            assert c["case_type"] == "PAYMENT_FAILURE"

    def test_list_cases_pagination(self):
        # Create 3 cases
        for _ in range(3):
            self._create_case()
        r = client.get("/api/recovery-cases?limit=2&offset=0")
        assert r.status_code == 200
        assert len(r.json()["cases"]) <= 2
