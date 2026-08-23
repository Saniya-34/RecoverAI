"""
Tests for Stage 2 — Domain Model Design.

Verifies:
1. All expected tables exist after migration.
2. Foreign-key relationships are structurally valid (inspect metadata).
3. Enum types are registered correctly.
4. Basic ORM round-trip: insert + query for each model.
5. Monetary fields use NUMERIC, not FLOAT.
6. The existing DB connectivity test is unaffected.

These tests require a live PostgreSQL connection (DATABASE_URL must be set
and migrations must have been applied before running).
"""

import os
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.app.database import engine
from backend.app.models import (
    AgentAction,
    ActionStatus,
    ActionType,
    AuditLog,
    CaseStatus,
    CaseType,
    CheckoutEvent,
    CheckoutEventType,
    Customer,
    Order,
    Payment,
    RecoveryCase,
)


# ======================================================================== #
# Helpers                                                                   #
# ======================================================================== #

EXPECTED_TABLES = {
    "customers",
    "orders",
    "payments",
    "checkout_events",
    "recovery_cases",
    "agent_actions",
    "audit_logs",
}


@pytest.fixture(scope="module")
def db():
    """Provide a SQLAlchemy session for the test module, rolled back after."""
    with Session(engine) as session:
        with session.begin():
            yield session
            session.rollback()


# ======================================================================== #
# 1. Schema existence                                                       #
# ======================================================================== #

class TestSchemaExists:

    def test_database_url_set(self):
        assert os.getenv("DATABASE_URL"), "DATABASE_URL must be set"

    def test_all_tables_exist(self):
        inspector = inspect(engine)
        existing = set(inspector.get_table_names())
        missing = EXPECTED_TABLES - existing
        assert not missing, f"Missing tables after migration: {missing}"

    def test_expected_table_count(self):
        inspector = inspect(engine)
        existing = set(inspector.get_table_names())
        # At least our 7 tables must exist (there may be alembic_version too)
        assert EXPECTED_TABLES.issubset(existing)


# ======================================================================== #
# 2. Foreign key constraints                                                #
# ======================================================================== #

class TestForeignKeys:

    def _fk_targets(self, table_name):
        inspector = inspect(engine)
        return {
            fk["referred_table"]
            for fk in inspector.get_foreign_keys(table_name)
        }

    def test_orders_fk_to_customers(self):
        assert "customers" in self._fk_targets("orders")

    def test_payments_fk_to_orders_and_customers(self):
        targets = self._fk_targets("payments")
        assert "orders" in targets
        assert "customers" in targets

    def test_checkout_events_fk_to_customers(self):
        assert "customers" in self._fk_targets("checkout_events")

    def test_recovery_cases_fk_to_customer_order_payment(self):
        targets = self._fk_targets("recovery_cases")
        assert "customers" in targets
        assert "orders" in targets
        assert "payments" in targets

    def test_agent_actions_fk_to_recovery_cases(self):
        assert "recovery_cases" in self._fk_targets("agent_actions")

    def test_audit_logs_fk_to_recovery_cases_and_agent_actions(self):
        targets = self._fk_targets("audit_logs")
        assert "recovery_cases" in targets
        assert "agent_actions" in targets


# ======================================================================== #
# 3. Numeric (not float) for monetary columns                              #
# ======================================================================== #

class TestMonetaryColumnTypes:

    def _col_type(self, table_name, col_name):
        inspector = inspect(engine)
        cols = {c["name"]: c for c in inspector.get_columns(table_name)}
        return type(cols[col_name]["type"]).__name__.upper()

    def test_orders_amount_is_numeric(self):
        t = self._col_type("orders", "amount")
        assert "NUMERIC" in t or "DECIMAL" in t, f"Expected NUMERIC, got {t}"

    def test_payments_amount_is_numeric(self):
        t = self._col_type("payments", "amount")
        assert "NUMERIC" in t or "DECIMAL" in t, f"Expected NUMERIC, got {t}"

    def test_checkout_events_amount_is_numeric(self):
        t = self._col_type("checkout_events", "amount")
        assert "NUMERIC" in t or "DECIMAL" in t, f"Expected NUMERIC, got {t}"

    def test_recovery_cases_risk_amount_is_numeric(self):
        t = self._col_type("recovery_cases", "risk_amount")
        assert "NUMERIC" in t or "DECIMAL" in t, f"Expected NUMERIC, got {t}"


# ======================================================================== #
# 4. ORM round-trip — insert and query each model                          #
# ======================================================================== #

class TestOrmRoundTrip:
    """
    Each test inserts one or more rows and queries them back.
    The db fixture rolls back everything at the end of the module.
    """

    def test_create_customer(self, db):
        c = Customer(
            external_customer_id="test-cust-001",
            name="Alice Test",
            email="alice@example.com",
            phone="+911234567890",
        )
        db.add(c)
        db.flush()
        assert c.id is not None
        fetched = db.get(Customer, c.id)
        assert fetched.external_customer_id == "test-cust-001"
        assert fetched.email == "alice@example.com"

    def test_create_order(self, db):
        c = Customer(external_customer_id="test-cust-002", name="Bob Test")
        db.add(c)
        db.flush()

        o = Order(
            external_order_id="test-order-001",
            customer_id=c.id,
            amount=Decimal("1999.99"),
            currency="INR",
            status="PENDING",
        )
        db.add(o)
        db.flush()
        assert o.id is not None
        fetched = db.get(Order, o.id)
        assert fetched.amount == Decimal("1999.99")
        assert fetched.currency == "INR"

    def test_create_payment(self, db):
        c = Customer(external_customer_id="test-cust-003")
        db.add(c)
        db.flush()

        o = Order(
            external_order_id="test-order-002",
            customer_id=c.id,
            amount=Decimal("500.00"),
            currency="INR",
            status="PENDING",
        )
        db.add(o)
        db.flush()

        p = Payment(
            external_payment_id="test-pay-001",
            order_id=o.id,
            customer_id=c.id,
            amount=Decimal("500.00"),
            currency="INR",
            status="FAILED",
            failure_reason="INSUFFICIENT_FUNDS",
            payment_method="CARD",
        )
        db.add(p)
        db.flush()
        assert p.id is not None
        fetched = db.get(Payment, p.id)
        assert fetched.status == "FAILED"
        assert fetched.failure_reason == "INSUFFICIENT_FUNDS"

    def test_create_checkout_event(self, db):
        c = Customer(external_customer_id="test-cust-004")
        db.add(c)
        db.flush()

        evt = CheckoutEvent(
            customer_id=c.id,
            event_type=CheckoutEventType.CHECKOUT_ABANDONED,
            amount=Decimal("750.00"),
            event_metadata={"utm_source": "email", "cart_items": 3},
        )
        db.add(evt)
        db.flush()
        assert evt.id is not None
        fetched = db.get(CheckoutEvent, evt.id)
        assert fetched.event_type == CheckoutEventType.CHECKOUT_ABANDONED
        assert fetched.event_metadata["cart_items"] == 3

    def test_create_recovery_case(self, db):
        c = Customer(external_customer_id="test-cust-005")
        db.add(c)
        db.flush()

        o = Order(
            external_order_id="test-order-003",
            customer_id=c.id,
            amount=Decimal("2500.00"),
            currency="INR",
            status="PENDING",
        )
        db.add(o)
        db.flush()

        rc = RecoveryCase(
            customer_id=c.id,
            order_id=o.id,
            case_type=CaseType.PAYMENT_FAILURE,
            risk_amount=Decimal("2500.00"),
            status=CaseStatus.OPEN,
        )
        db.add(rc)
        db.flush()
        assert rc.id is not None
        fetched = db.get(RecoveryCase, rc.id)
        assert fetched.case_type == CaseType.PAYMENT_FAILURE
        assert fetched.status == CaseStatus.OPEN

    def test_create_agent_action(self, db):
        c = Customer(external_customer_id="test-cust-006")
        db.add(c)
        db.flush()

        o = Order(
            external_order_id="test-order-004",
            customer_id=c.id,
            amount=Decimal("100.00"),
            currency="INR",
            status="PENDING",
        )
        db.add(o)
        db.flush()

        rc = RecoveryCase(
            customer_id=c.id,
            order_id=o.id,
            case_type=CaseType.CHECKOUT_ABANDONMENT,
            risk_amount=Decimal("100.00"),
            status=CaseStatus.OPEN,
        )
        db.add(rc)
        db.flush()

        action = AgentAction(
            recovery_case_id=rc.id,
            action_type=ActionType.SEND_REMINDER,
            reason="Customer abandoned cart 2 hours ago.",
            status=ActionStatus.PENDING,
        )
        db.add(action)
        db.flush()
        assert action.id is not None
        fetched = db.get(AgentAction, action.id)
        assert fetched.action_type == ActionType.SEND_REMINDER
        assert fetched.status == ActionStatus.PENDING

    def test_create_audit_log(self, db):
        c = Customer(external_customer_id="test-cust-007")
        db.add(c)
        db.flush()

        o = Order(
            external_order_id="test-order-005",
            customer_id=c.id,
            amount=Decimal("300.00"),
            currency="INR",
            status="PENDING",
        )
        db.add(o)
        db.flush()

        rc = RecoveryCase(
            customer_id=c.id,
            order_id=o.id,
            case_type=CaseType.PAYMENT_FAILURE,
            risk_amount=Decimal("300.00"),
            status=CaseStatus.OPEN,
        )
        db.add(rc)
        db.flush()

        log = AuditLog(
            recovery_case_id=rc.id,
            event_type="CASE_OPENED",
            actor="SYSTEM",
            details={"trigger": "payment_webhook", "gateway": "razorpay"},
        )
        db.add(log)
        db.flush()
        assert log.id is not None
        fetched = db.get(AuditLog, log.id)
        assert fetched.event_type == "CASE_OPENED"
        assert fetched.details["trigger"] == "payment_webhook"


# ======================================================================== #
# 5. Relationship traversal                                                 #
# ======================================================================== #

class TestRelationships:

    def test_customer_orders_relationship(self, db):
        c = Customer(external_customer_id="test-rel-cust-001")
        db.add(c)
        db.flush()

        o1 = Order(
            external_order_id="test-rel-order-001",
            customer_id=c.id,
            amount=Decimal("100.00"),
            currency="INR",
            status="PENDING",
        )
        o2 = Order(
            external_order_id="test-rel-order-002",
            customer_id=c.id,
            amount=Decimal("200.00"),
            currency="INR",
            status="PENDING",
        )
        db.add_all([o1, o2])
        db.flush()

        db.refresh(c)
        assert len(c.orders) == 2

    def test_order_payments_relationship(self, db):
        c = Customer(external_customer_id="test-rel-cust-002")
        db.add(c)
        db.flush()

        o = Order(
            external_order_id="test-rel-order-003",
            customer_id=c.id,
            amount=Decimal("999.00"),
            currency="INR",
            status="PENDING",
        )
        db.add(o)
        db.flush()

        p1 = Payment(
            order_id=o.id, customer_id=c.id,
            amount=Decimal("999.00"), currency="INR", status="FAILED",
        )
        p2 = Payment(
            order_id=o.id, customer_id=c.id,
            amount=Decimal("999.00"), currency="INR", status="PENDING",
        )
        db.add_all([p1, p2])
        db.flush()

        db.refresh(o)
        assert len(o.payments) == 2

    def test_recovery_case_agent_actions_relationship(self, db):
        c = Customer(external_customer_id="test-rel-cust-003")
        db.add(c)
        db.flush()

        o = Order(
            external_order_id="test-rel-order-004",
            customer_id=c.id,
            amount=Decimal("500.00"),
            currency="INR",
            status="PENDING",
        )
        db.add(o)
        db.flush()

        rc = RecoveryCase(
            customer_id=c.id, order_id=o.id,
            case_type=CaseType.PAYMENT_FAILURE,
            risk_amount=Decimal("500.00"),
            status=CaseStatus.OPEN,
        )
        db.add(rc)
        db.flush()

        a1 = AgentAction(
            recovery_case_id=rc.id,
            action_type=ActionType.RETRY_PAYMENT,
            status=ActionStatus.PENDING,
        )
        a2 = AgentAction(
            recovery_case_id=rc.id,
            action_type=ActionType.SEND_REMINDER,
            status=ActionStatus.PENDING,
        )
        db.add_all([a1, a2])
        db.flush()

        db.refresh(rc)
        assert len(rc.agent_actions) == 2
