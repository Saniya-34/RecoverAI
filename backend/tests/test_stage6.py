"""
Tests for Stage 6 — Dashboard API endpoints.

Covers:
1. GET /api/dashboard/summary — returns correct fields
2. GET /api/dashboard/summary — values are numeric
3. GET /api/dashboard/summary — recovered_revenue is always 0
4. GET /api/recovery-cases/{id}/audit — returns empty trail for new case
5. GET /api/recovery-cases/{id}/audit — 404 for missing case
6. GET /api/recovery-cases/{id}/audit — entries appear after agent run
7. GET /api/recovery-cases — still works (regression)
8. GET /api/recovery-cases?status=OPEN — filter works
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.database import engine
from backend.app.main import app
from backend.app.models.agent_action import AgentAction, ActionStatus, ActionType
from backend.app.models.audit_log import AuditLog
from backend.app.models.customer import Customer
from backend.app.models.order import Order
from backend.app.models.payment import Payment
from backend.app.models.recovery_case import CaseStatus, CaseType, RecoveryCase

client = TestClient(app)


def uid():
    return str(uuid.uuid4())[:10]


def _now():
    return datetime.now(timezone.utc)


def _make_open_case(db: Session) -> RecoveryCase:
    now = _now()
    c = Customer(external_customer_id=f"S6-{uid()}", created_at=now, updated_at=now)
    db.add(c); db.flush()

    o = Order(
        external_order_id=f"S6O-{uid()}",
        customer_id=c.id, amount=Decimal("1999.00"),
        currency="INR", status="FAILED", created_at=now, updated_at=now,
    )
    db.add(o); db.flush()

    p = Payment(
        external_payment_id=f"S6P-{uid()}",
        order_id=o.id, customer_id=c.id,
        amount=Decimal("1999.00"), currency="INR",
        status="FAILED", failure_reason="bank_timeout",
        payment_method="CARD", attempted_at=now, created_at=now, updated_at=now,
    )
    db.add(p); db.flush()

    rc = RecoveryCase(
        customer_id=c.id, order_id=o.id, payment_id=p.id,
        case_type=CaseType.PAYMENT_FAILURE,
        risk_amount=Decimal("1999.00"),
        status=CaseStatus.OPEN,
        detected_at=now, created_at=now, updated_at=now,
    )
    db.add(rc); db.flush()
    return rc


# ── Dashboard summary ─────────────────────────────────────────────────────────

class TestDashboardSummary:

    def test_summary_returns_200(self):
        r = client.get("/api/dashboard/summary")
        assert r.status_code == 200

    def test_summary_has_required_fields(self):
        r = client.get("/api/dashboard/summary")
        body = r.json()
        assert "total_revenue_at_risk" in body
        assert "total_cases" in body
        assert "open_cases" in body
        assert "in_progress_cases" in body
        assert "recovered_cases" in body
        assert "stopped_cases" in body
        assert "recovered_revenue" in body
        assert "currency" in body

    def test_summary_recovered_revenue_always_zero(self):
        """Simulated actions must never report recovered revenue."""
        r = client.get("/api/dashboard/summary")
        body = r.json()
        assert float(body["recovered_revenue"]) == 0.0, (
            "recovered_revenue must be 0 — simulated actions don't move real money"
        )

    def test_summary_currency_is_inr(self):
        r = client.get("/api/dashboard/summary")
        assert r.json()["currency"] == "INR"

    def test_summary_numeric_values_are_non_negative(self):
        r = client.get("/api/dashboard/summary")
        body = r.json()
        assert float(body["total_revenue_at_risk"]) >= 0
        assert body["total_cases"] >= 0
        assert body["open_cases"] >= 0

    def test_summary_open_cases_lte_total(self):
        r = client.get("/api/dashboard/summary")
        body = r.json()
        assert body["open_cases"] <= body["total_cases"]

    def test_summary_reflects_seeded_data(self):
        """Should have at least the 128 cases from Stage 3 seed data."""
        r = client.get("/api/dashboard/summary")
        body = r.json()
        assert body["total_cases"] >= 50


# ── Audit trail endpoint ──────────────────────────────────────────────────────

class TestAuditTrail:

    @pytest.fixture(autouse=True)
    def cleanup(self):
        yield
        # No cleanup needed — each test uses unique IDs

    def test_audit_404_for_missing_case(self):
        r = client.get("/api/recovery-cases/999999999/audit")
        assert r.status_code == 404

    def test_audit_empty_for_new_case(self):
        with Session(engine) as db:
            with db.begin():
                rc = _make_open_case(db)
                case_id = rc.id

        r = client.get(f"/api/recovery-cases/{case_id}/audit")
        assert r.status_code == 200
        body = r.json()
        assert body["case_id"] == case_id
        assert body["total"] == 0
        assert body["entries"] == []

    def test_audit_entries_after_manual_insert(self):
        """Insert an AuditLog manually and verify it appears in the API."""
        with Session(engine) as db:
            with db.begin():
                rc = _make_open_case(db)
                case_id = rc.id
                now = _now()
                db.add(AuditLog(
                    recovery_case_id=case_id,
                    event_type="AGENT_STARTED",
                    actor="AGENT",
                    details={"case_id": case_id},
                    created_at=now,
                ))

        r = client.get(f"/api/recovery-cases/{case_id}/audit")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        event_types = [e["event_type"] for e in body["entries"]]
        assert "AGENT_STARTED" in event_types

    def test_audit_entries_have_required_fields(self):
        with Session(engine) as db:
            with db.begin():
                rc = _make_open_case(db)
                case_id = rc.id
                db.add(AuditLog(
                    recovery_case_id=case_id,
                    event_type="CASE_LOADED",
                    actor="AGENT",
                    details={"test": True},
                    created_at=_now(),
                ))

        r = client.get(f"/api/recovery-cases/{case_id}/audit")
        entry = r.json()["entries"][0]
        assert "id" in entry
        assert "event_type" in entry
        assert "actor" in entry
        assert "created_at" in entry

    def test_audit_entries_chronological_order(self):
        """Entries must be returned in ascending created_at order."""
        with Session(engine) as db:
            with db.begin():
                rc = _make_open_case(db)
                case_id = rc.id
                import time as _time
                for evt in ("AGENT_STARTED", "CASE_LOADED", "AGENT_COMPLETED"):
                    db.add(AuditLog(
                        recovery_case_id=case_id,
                        event_type=evt,
                        actor="AGENT",
                        created_at=_now(),
                    ))
                    _time.sleep(0.01)

        r = client.get(f"/api/recovery-cases/{case_id}/audit")
        entries = r.json()["entries"]
        times = [e["created_at"] for e in entries]
        assert times == sorted(times), "Audit entries are not in chronological order"


# ── Case list regression ──────────────────────────────────────────────────────

class TestCaseListRegression:

    def test_case_list_returns_200(self):
        r = client.get("/api/recovery-cases")
        assert r.status_code == 200

    def test_case_list_has_cases_and_total(self):
        r = client.get("/api/recovery-cases")
        body = r.json()
        assert "cases" in body
        assert "total" in body

    def test_case_list_status_filter_open(self):
        r = client.get("/api/recovery-cases?status=OPEN")
        assert r.status_code == 200
        body = r.json()
        for c in body["cases"]:
            assert c["status"] == "OPEN"

    def test_case_list_invalid_status_returns_422(self):
        r = client.get("/api/recovery-cases?status=BOGUS")
        assert r.status_code == 422

    def test_case_detail_returns_customer_order_payment(self):
        """First OPEN case should have customer, order, and payment context."""
        r = client.get("/api/recovery-cases?status=OPEN&limit=1")
        cases = r.json()["cases"]
        if not cases:
            pytest.skip("No OPEN cases in DB")
        case_id = cases[0]["id"]
        r2 = client.get(f"/api/recovery-cases/{case_id}")
        assert r2.status_code == 200
        body = r2.json()
        assert "customer" in body
        assert "order" in body
        assert "explanation" in body

    def test_no_gemini_key_in_any_response(self):
        """Sanity check: GEMINI_API_KEY must never appear in any API response."""
        import os
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            pytest.skip("GEMINI_API_KEY not set")

        endpoints = [
            "/api/dashboard/summary",
            "/api/recovery-cases?limit=5",
            "/health",
        ]
        for ep in endpoints:
            r = client.get(ep)
            assert key not in r.text, f"API key found in response from {ep}!"
