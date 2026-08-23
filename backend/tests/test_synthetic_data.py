"""
Tests for Stage 3 — Synthetic Data Generation and Database Seeding.

Verifies:
1.  Minimum record counts exist in the database.
2.  Foreign-key integrity (no orphaned rows).
3.  External IDs are unique.
4.  Payment amounts are valid (> 0, finite).
5.  Checkout event timestamps are logically ordered per order.
6.  Recovery cases reference valid customers / orders.
7.  Generator is deterministic (same seed → same output).
8.  Required revenue-at-risk scenarios are represented.
9.  High-value cases (>= ₹10 000) exist.
10. Repeated-failure orders exist (3+ failures on same order).
11. Existing DB connectivity test still passes (implicit — same engine).

These tests require:
  - DATABASE_URL to be set
  - Alembic migrations applied
  - Seed data inserted (python -m data.synthetic.seed_data)
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.database import engine
from backend.app.models.checkout_event import CheckoutEventType
from backend.app.models.recovery_case import CaseStatus, CaseType
from data.synthetic.scenarios import generate, RANDOM_SEED


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def db():
    """Read-only session for the whole test module."""
    with Session(engine) as session:
        yield session


@pytest.fixture(scope="module")
def dataset():
    """In-memory dataset generated from the canonical seed."""
    return generate(seed=RANDOM_SEED)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Minimum record counts
# ══════════════════════════════════════════════════════════════════════════════

class TestMinimumCounts:

    def test_customers_minimum(self, db):
        count = db.execute(text("SELECT COUNT(*) FROM customers")).scalar()
        assert count >= 100, f"Expected ≥100 customers, got {count}"

    def test_orders_minimum(self, db):
        count = db.execute(text("SELECT COUNT(*) FROM orders")).scalar()
        assert count >= 150, f"Expected ≥150 orders, got {count}"

    def test_payments_minimum(self, db):
        count = db.execute(text("SELECT COUNT(*) FROM payments")).scalar()
        assert count >= 200, f"Expected ≥200 payments, got {count}"

    def test_checkout_events_minimum(self, db):
        count = db.execute(text("SELECT COUNT(*) FROM checkout_events")).scalar()
        assert count >= 200, f"Expected ≥200 checkout events, got {count}"

    def test_recovery_cases_minimum(self, db):
        count = db.execute(text("SELECT COUNT(*) FROM recovery_cases")).scalar()
        assert count >= 50, f"Expected ≥50 recovery cases, got {count}"


# ══════════════════════════════════════════════════════════════════════════════
# 2. Foreign-key integrity (no orphaned rows)
# ══════════════════════════════════════════════════════════════════════════════

class TestForeignKeyIntegrity:

    def test_orders_all_have_valid_customer(self, db):
        orphans = db.execute(
            text("""
                SELECT COUNT(*) FROM orders o
                LEFT JOIN customers c ON o.customer_id = c.id
                WHERE c.id IS NULL
            """)
        ).scalar()
        assert orphans == 0, f"{orphans} orders have no matching customer"

    def test_payments_all_have_valid_order(self, db):
        orphans = db.execute(
            text("""
                SELECT COUNT(*) FROM payments p
                LEFT JOIN orders o ON p.order_id = o.id
                WHERE o.id IS NULL
            """)
        ).scalar()
        assert orphans == 0, f"{orphans} payments have no matching order"

    def test_payments_all_have_valid_customer(self, db):
        orphans = db.execute(
            text("""
                SELECT COUNT(*) FROM payments p
                LEFT JOIN customers c ON p.customer_id = c.id
                WHERE c.id IS NULL
            """)
        ).scalar()
        assert orphans == 0

    def test_checkout_events_all_have_valid_customer(self, db):
        orphans = db.execute(
            text("""
                SELECT COUNT(*) FROM checkout_events ce
                LEFT JOIN customers c ON ce.customer_id = c.id
                WHERE c.id IS NULL
            """)
        ).scalar()
        assert orphans == 0

    def test_recovery_cases_all_have_valid_customer(self, db):
        orphans = db.execute(
            text("""
                SELECT COUNT(*) FROM recovery_cases rc
                LEFT JOIN customers c ON rc.customer_id = c.id
                WHERE c.id IS NULL
            """)
        ).scalar()
        assert orphans == 0

    def test_recovery_cases_all_have_valid_order(self, db):
        orphans = db.execute(
            text("""
                SELECT COUNT(*) FROM recovery_cases rc
                LEFT JOIN orders o ON rc.order_id = o.id
                WHERE o.id IS NULL
            """)
        ).scalar()
        assert orphans == 0

    def test_recovery_cases_payment_fk_when_set(self, db):
        """Where payment_id is not null, it must reference a real payment."""
        orphans = db.execute(
            text("""
                SELECT COUNT(*) FROM recovery_cases rc
                LEFT JOIN payments p ON rc.payment_id = p.id
                WHERE rc.payment_id IS NOT NULL AND p.id IS NULL
            """)
        ).scalar()
        assert orphans == 0


# ══════════════════════════════════════════════════════════════════════════════
# 3. External IDs are unique
# ══════════════════════════════════════════════════════════════════════════════

class TestUniqueness:

    def test_customer_external_ids_unique(self, db):
        dupes = db.execute(
            text("""
                SELECT COUNT(*) FROM (
                    SELECT external_customer_id
                    FROM customers
                    GROUP BY external_customer_id
                    HAVING COUNT(*) > 1
                ) sub
            """)
        ).scalar()
        assert dupes == 0, f"{dupes} duplicate external_customer_id values"

    def test_order_external_ids_unique(self, db):
        dupes = db.execute(
            text("""
                SELECT COUNT(*) FROM (
                    SELECT external_order_id
                    FROM orders
                    GROUP BY external_order_id
                    HAVING COUNT(*) > 1
                ) sub
            """)
        ).scalar()
        assert dupes == 0

    def test_payment_external_ids_unique_when_set(self, db):
        """external_payment_id is nullable; non-null values must be unique."""
        dupes = db.execute(
            text("""
                SELECT COUNT(*) FROM (
                    SELECT external_payment_id
                    FROM payments
                    WHERE external_payment_id IS NOT NULL
                    GROUP BY external_payment_id
                    HAVING COUNT(*) > 1
                ) sub
            """)
        ).scalar()
        assert dupes == 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. Payment amounts are valid
# ══════════════════════════════════════════════════════════════════════════════

class TestPaymentAmounts:

    def test_no_zero_or_negative_amounts_payments(self, db):
        bad = db.execute(
            text("SELECT COUNT(*) FROM payments WHERE amount <= 0")
        ).scalar()
        assert bad == 0, f"{bad} payments with amount <= 0"

    def test_no_zero_or_negative_amounts_orders(self, db):
        bad = db.execute(
            text("SELECT COUNT(*) FROM orders WHERE amount <= 0")
        ).scalar()
        assert bad == 0

    def test_no_zero_risk_amount_recovery_cases(self, db):
        bad = db.execute(
            text("SELECT COUNT(*) FROM recovery_cases WHERE risk_amount <= 0")
        ).scalar()
        assert bad == 0

    def test_currency_is_inr(self, db):
        bad = db.execute(
            text("SELECT COUNT(*) FROM payments WHERE currency != 'INR'")
        ).scalar()
        assert bad == 0


# ══════════════════════════════════════════════════════════════════════════════
# 5. Checkout event timestamps are logically ordered
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckoutEventOrdering:

    def test_checkout_started_before_payment_initiated(self, db):
        """
        For any order: the first CHECKOUT_STARTED must be earlier than
        the first PAYMENT_INITIATED (if both exist).
        """
        violations = db.execute(
            text("""
                SELECT COUNT(*) FROM (
                    SELECT
                        ce.order_id,
                        MIN(CASE WHEN ce.event_type = 'CHECKOUT_STARTED'
                                 THEN ce.occurred_at END) AS started,
                        MIN(CASE WHEN ce.event_type = 'PAYMENT_INITIATED'
                                 THEN ce.occurred_at END) AS initiated
                    FROM checkout_events ce
                    WHERE ce.order_id IS NOT NULL
                    GROUP BY ce.order_id
                    HAVING
                        MIN(CASE WHEN ce.event_type = 'CHECKOUT_STARTED'
                                 THEN ce.occurred_at END) IS NOT NULL
                        AND
                        MIN(CASE WHEN ce.event_type = 'PAYMENT_INITIATED'
                                 THEN ce.occurred_at END) IS NOT NULL
                        AND
                        MIN(CASE WHEN ce.event_type = 'CHECKOUT_STARTED'
                                 THEN ce.occurred_at END)
                        >
                        MIN(CASE WHEN ce.event_type = 'PAYMENT_INITIATED'
                                 THEN ce.occurred_at END)
                ) violations
            """)
        ).scalar()
        assert violations == 0, (
            f"{violations} orders where CHECKOUT_STARTED is after PAYMENT_INITIATED"
        )

    def test_payment_initiated_before_payment_result(self, db):
        """
        For any order: PAYMENT_INITIATED must be before PAYMENT_SUCCESS/FAILED.
        """
        violations = db.execute(
            text("""
                SELECT COUNT(*) FROM (
                    SELECT
                        ce.order_id,
                        MIN(CASE WHEN ce.event_type = 'PAYMENT_INITIATED'
                                 THEN ce.occurred_at END) AS initiated,
                        MIN(CASE WHEN ce.event_type IN ('PAYMENT_SUCCESS','PAYMENT_FAILED')
                                 THEN ce.occurred_at END) AS result
                    FROM checkout_events ce
                    WHERE ce.order_id IS NOT NULL
                    GROUP BY ce.order_id
                    HAVING
                        MIN(CASE WHEN ce.event_type = 'PAYMENT_INITIATED'
                                 THEN ce.occurred_at END) IS NOT NULL
                        AND
                        MIN(CASE WHEN ce.event_type IN ('PAYMENT_SUCCESS','PAYMENT_FAILED')
                                 THEN ce.occurred_at END) IS NOT NULL
                        AND
                        MIN(CASE WHEN ce.event_type = 'PAYMENT_INITIATED'
                                 THEN ce.occurred_at END)
                        >
                        MIN(CASE WHEN ce.event_type IN ('PAYMENT_SUCCESS','PAYMENT_FAILED')
                                 THEN ce.occurred_at END)
                ) v
            """)
        ).scalar()
        assert violations == 0


# ══════════════════════════════════════════════════════════════════════════════
# 6. Revenue-at-risk scenarios are represented
# ══════════════════════════════════════════════════════════════════════════════

class TestScenarioCoverage:

    def test_payment_failure_cases_exist(self, db):
        count = db.execute(
            text("SELECT COUNT(*) FROM recovery_cases WHERE case_type = 'PAYMENT_FAILURE'")
        ).scalar()
        assert count >= 10, f"Expected ≥10 PAYMENT_FAILURE cases, got {count}"

    def test_checkout_abandonment_cases_exist(self, db):
        count = db.execute(
            text("SELECT COUNT(*) FROM recovery_cases WHERE case_type = 'CHECKOUT_ABANDONMENT'")
        ).scalar()
        assert count >= 10, f"Expected ≥10 CHECKOUT_ABANDONMENT cases, got {count}"

    def test_subscription_failure_cases_exist(self, db):
        count = db.execute(
            text("SELECT COUNT(*) FROM recovery_cases WHERE case_type = 'SUBSCRIPTION_FAILURE'")
        ).scalar()
        assert count >= 5, f"Expected ≥5 SUBSCRIPTION_FAILURE cases, got {count}"

    def test_high_value_cases_exist(self, db):
        count = db.execute(
            text("SELECT COUNT(*) FROM recovery_cases WHERE risk_amount >= 10000")
        ).scalar()
        assert count >= 5, f"Expected ≥5 high-value cases, got {count}"

    def test_repeated_failure_orders_exist(self, db):
        """Orders with 3 or more failed payment attempts."""
        count = db.execute(
            text("""
                SELECT COUNT(*) FROM (
                    SELECT order_id
                    FROM payments
                    WHERE status = 'FAILED'
                    GROUP BY order_id
                    HAVING COUNT(*) >= 3
                ) sub
            """)
        ).scalar()
        assert count >= 5, f"Expected ≥5 orders with 3+ failures, got {count}"

    def test_recovered_cases_exist(self, db):
        count = db.execute(
            text("SELECT COUNT(*) FROM recovery_cases WHERE status = 'RECOVERED'")
        ).scalar()
        assert count >= 5, f"Expected ≥5 RECOVERED cases, got {count}"

    def test_open_cases_exist(self, db):
        count = db.execute(
            text("SELECT COUNT(*) FROM recovery_cases WHERE status = 'OPEN'")
        ).scalar()
        assert count >= 30, f"Expected ≥30 OPEN cases, got {count}"

    def test_successful_payments_exist(self, db):
        count = db.execute(
            text("SELECT COUNT(*) FROM payments WHERE status = 'SUCCESS'")
        ).scalar()
        assert count >= 50, f"Expected ≥50 successful payments, got {count}"

    def test_failed_payments_exist(self, db):
        count = db.execute(
            text("SELECT COUNT(*) FROM payments WHERE status = 'FAILED'")
        ).scalar()
        assert count >= 80, f"Expected ≥80 failed payments, got {count}"

    def test_checkout_abandonment_events_exist(self, db):
        count = db.execute(
            text("SELECT COUNT(*) FROM checkout_events WHERE event_type = 'CHECKOUT_ABANDONED'")
        ).scalar()
        assert count >= 20, f"Expected ≥20 CHECKOUT_ABANDONED events, got {count}"

    def test_loyal_customer_history_exists(self, db):
        """
        At least one customer should have 5+ successful payments
        (the S01 loyal customer scenario).
        """
        count = db.execute(
            text("""
                SELECT COUNT(*) FROM (
                    SELECT customer_id
                    FROM payments
                    WHERE status = 'SUCCESS'
                    GROUP BY customer_id
                    HAVING COUNT(*) >= 5
                ) sub
            """)
        ).scalar()
        assert count >= 5, f"Expected ≥5 customers with 5+ successes, got {count}"


# ══════════════════════════════════════════════════════════════════════════════
# 7. Generator determinism
# ══════════════════════════════════════════════════════════════════════════════

class TestDeterminism:

    def test_same_seed_produces_same_customer_count(self):
        d1 = generate(seed=RANDOM_SEED)
        d2 = generate(seed=RANDOM_SEED)
        assert len(d1.customers) == len(d2.customers)

    def test_same_seed_produces_same_order_count(self):
        d1 = generate(seed=RANDOM_SEED)
        d2 = generate(seed=RANDOM_SEED)
        assert len(d1.orders) == len(d2.orders)

    def test_same_seed_produces_same_first_customer_id(self):
        d1 = generate(seed=RANDOM_SEED)
        d2 = generate(seed=RANDOM_SEED)
        assert d1.customers[0].external_customer_id == d2.customers[0].external_customer_id

    def test_same_seed_produces_same_first_order_amount(self):
        d1 = generate(seed=RANDOM_SEED)
        d2 = generate(seed=RANDOM_SEED)
        assert d1.orders[0].amount == d2.orders[0].amount

    def test_different_seeds_produce_different_names(self):
        d1 = generate(seed=42)
        d2 = generate(seed=99)
        names1 = {c.name for c in d1.customers}
        names2 = {c.name for c in d2.customers}
        # With different seeds the pools are random — highly unlikely to be equal
        assert names1 != names2

    def test_in_memory_dataset_external_ids_are_unique(self):
        d = generate(seed=RANDOM_SEED)
        cids = [c.external_customer_id for c in d.customers]
        assert len(cids) == len(set(cids)), "Duplicate external_customer_id in generated data"

    def test_in_memory_order_ids_are_unique(self):
        d = generate(seed=RANDOM_SEED)
        oids = [o.external_order_id for o in d.orders]
        assert len(oids) == len(set(oids))

    def test_in_memory_payment_ids_are_unique(self):
        d = generate(seed=RANDOM_SEED)
        pids = [p.external_payment_id for p in d.payments if p.external_payment_id]
        assert len(pids) == len(set(pids))
