"""
data/synthetic/scenarios.py

Pure data-generation layer — no database access here.

Produces all synthetic records as plain Python dataclasses/dicts,
deterministically from a fixed random seed.  The seeder (seed_data.py)
is responsible for inserting them into PostgreSQL.

Scenario catalogue
──────────────────
S01  LOYAL_CUSTOMER_ONE_OFF_FAILURE   — many successes then one failure  → RECOVERABLE
S02  SINGLE_FAILURE_NEW_CUSTOMER      — first order, one failure         → RECOVERABLE
S03  REPEATED_FAILURES                — 3+ consecutive failures          → LOW_RECOVERY_PROBABILITY
S04  CHECKOUT_ABANDONMENT_CLEAN       — started but never paid           → RECOVERABLE_CHECKOUT
S05  CHECKOUT_ABANDONMENT_AFTER_FAIL  — started, payment failed, left   → RECOVERABLE_CHECKOUT
S06  HIGH_VALUE_FAILURE               — order ≥ ₹10 000, payment failed → RECOVERABLE_HIGH_VALUE
S07  SUBSCRIPTION_FAILURE             — recurring plan payment failed    → RECOVERABLE
S08  ALREADY_RECOVERED                — failed then succeeded later      → NOT_AT_RISK (closed case)
S09  CANCELLED_ORDER                  — customer cancelled before paying → NOT_RECOVERABLE
S10  STALE_ABANDONMENT                — abandoned 60+ days ago           → LOW_RECOVERY_PROBABILITY
S11  MIXED_HISTORY                    — successes + failures + recovery  → mixed baseline
S12  PURELY_SUCCESSFUL                — all payments succeeded           → baseline (no case)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Seed — change only if you want a different dataset layout
# ──────────────────────────────────────────────────────────────────────────────
RANDOM_SEED = 42

# ──────────────────────────────────────────────────────────────────────────────
# Reference data pools
# ──────────────────────────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Rahul", "Priya", "Amit", "Sneha", "Vikram", "Anjali", "Rohan", "Pooja",
    "Arjun", "Deepa", "Karan", "Meera", "Suresh", "Nisha", "Aditya", "Kavya",
    "Rajesh", "Sunita", "Manish", "Rekha", "Siddharth", "Ritu", "Nikhil",
    "Swati", "Vivek", "Preeti", "Gaurav", "Shilpa", "Tarun", "Ananya",
    "Akash", "Divya", "Mohit", "Pallavi", "Harsh", "Neha", "Varun", "Isha",
    "Sachin", "Tanvi", "Ravi", "Shruti", "Kunal", "Smita", "Ankit", "Jyoti",
    "Pankaj", "Madhuri", "Deepak", "Aarti",
]

LAST_NAMES = [
    "Sharma", "Verma", "Singh", "Patel", "Gupta", "Kumar", "Mehta", "Joshi",
    "Rao", "Nair", "Pillai", "Reddy", "Iyer", "Menon", "Tiwari", "Agarwal",
    "Banerjee", "Chatterjee", "Das", "Sen", "Bose", "Ghosh", "Mukherjee",
    "Mishra", "Pandey", "Shukla", "Srivastava", "Dubey", "Yadav", "Chauhan",
]

PAYMENT_METHODS = ["CARD", "UPI", "NETBANKING", "WALLET"]

FAILURE_REASONS = [
    "insufficient_funds",
    "temporary_bank_error",
    "bank_timeout",
    "network_error",
    "authentication_failed",
    "payment_declined",
    "card_expired",
    "do_not_honour",
    "transaction_limit_exceeded",
]

# Realistic INR order amounts (paise-accurate Decimal)
ORDER_AMOUNTS = [
    Decimal("299.00"), Decimal("499.00"), Decimal("999.00"),
    Decimal("1499.00"), Decimal("2499.00"), Decimal("4999.00"),
    Decimal("9999.00"), Decimal("14999.00"), Decimal("19999.00"),
    Decimal("24999.00"),
]

HIGH_VALUE_AMOUNTS = [
    Decimal("10000.00"), Decimal("14999.00"), Decimal("19999.00"),
    Decimal("24999.00"), Decimal("29999.00"),
]

# ──────────────────────────────────────────────────────────────────────────────
# Dataclasses — lightweight transport containers
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SyntheticCustomer:
    external_customer_id: str
    name: str
    email: str
    phone: str
    created_at: datetime
    scenario_tag: str          # which scenario bucket this customer belongs to
    ground_truth: str          # evaluation label for AI testing


@dataclass
class SyntheticOrder:
    external_order_id: str
    customer_ext_id: str       # reference to SyntheticCustomer.external_customer_id
    amount: Decimal
    currency: str
    status: str
    created_at: datetime


@dataclass
class SyntheticPayment:
    external_payment_id: str | None
    order_ext_id: str          # reference to SyntheticOrder.external_order_id
    customer_ext_id: str
    amount: Decimal
    currency: str
    status: str
    failure_reason: str | None
    payment_method: str
    attempted_at: datetime


@dataclass
class SyntheticCheckoutEvent:
    customer_ext_id: str
    order_ext_id: str | None
    event_type: str
    amount: Decimal | None
    event_metadata: dict[str, Any]
    occurred_at: datetime


@dataclass
class SyntheticRecoveryCase:
    customer_ext_id: str
    order_ext_id: str
    payment_ext_id: str | None   # None for abandonment cases
    case_type: str
    risk_amount: Decimal
    status: str
    ground_truth: str            # RECOVERABLE / LOW_RECOVERY_PROBABILITY / etc.
    detected_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Dataset container
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SyntheticDataset:
    customers: list[SyntheticCustomer] = field(default_factory=list)
    orders: list[SyntheticOrder] = field(default_factory=list)
    payments: list[SyntheticPayment] = field(default_factory=list)
    checkout_events: list[SyntheticCheckoutEvent] = field(default_factory=list)
    recovery_cases: list[SyntheticRecoveryCase] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Generator
# ──────────────────────────────────────────────────────────────────────────────

class SyntheticDataGenerator:
    """
    Generates a fully self-consistent synthetic dataset.

    All IDs are deterministic strings (no UUIDs) so that the same seed
    always produces the same dataset.  The seeder checks for existing
    external_customer_id rows before inserting, so re-runs are idempotent.
    """

    def __init__(self, seed: int = RANDOM_SEED) -> None:
        self.rng = random.Random(seed)
        self._cust_counter = 0
        self._order_counter = 0
        self._pay_counter = 0
        self._event_counter = 0
        self._case_counter = 0

        self.dataset = SyntheticDataset()

        # Index structures for cross-referencing during generation
        self._customer_index: dict[str, SyntheticCustomer] = {}
        self._order_index: dict[str, SyntheticOrder] = {}
        self._payment_index: dict[str, SyntheticPayment] = {}

    # ── ID helpers ────────────────────────────────────────────────────────────

    def _cust_id(self) -> str:
        self._cust_counter += 1
        return f"CUST{self._cust_counter:04d}"

    def _order_id(self) -> str:
        self._order_counter += 1
        return f"ORD{self._order_counter:05d}"

    def _pay_id(self) -> str:
        self._pay_counter += 1
        return f"PAY{self._pay_counter:05d}"

    def _event_id(self) -> str:
        self._event_counter += 1
        return f"EVT{self._event_counter:05d}"

    def _case_id(self) -> str:
        self._case_counter += 1
        return f"CASE{self._case_counter:04d}"

    # ── Reference helpers ─────────────────────────────────────────────────────

    def _random_name(self) -> str:
        return f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"

    def _make_email(self, cust_id: str) -> str:
        return f"{cust_id.lower()}@example.com"

    def _make_phone(self) -> str:
        return f"+91{self.rng.randint(7000000000, 9999999999)}"

    def _ago(self, days: int, hours: int = 0, jitter_hours: int = 0) -> datetime:
        """Return a UTC datetime N days (+ hours) ago, with optional jitter."""
        base = datetime.now(timezone.utc) - timedelta(days=days, hours=hours)
        if jitter_hours:
            base += timedelta(hours=self.rng.randint(0, jitter_hours))
        return base

    def _random_amount(self) -> Decimal:
        return self.rng.choice(ORDER_AMOUNTS)

    def _random_high_amount(self) -> Decimal:
        return self.rng.choice(HIGH_VALUE_AMOUNTS)

    def _random_failure(self) -> str:
        return self.rng.choice(FAILURE_REASONS)

    def _random_method(self) -> str:
        return self.rng.choice(PAYMENT_METHODS)

    # ── Core builders ─────────────────────────────────────────────────────────

    def _add_customer(
        self,
        scenario_tag: str,
        ground_truth: str,
        days_ago: int = 0,
    ) -> SyntheticCustomer:
        cid = self._cust_id()
        c = SyntheticCustomer(
            external_customer_id=cid,
            name=self._random_name(),
            email=self._make_email(cid),
            phone=self._make_phone(),
            created_at=self._ago(days_ago + self.rng.randint(0, 30)),
            scenario_tag=scenario_tag,
            ground_truth=ground_truth,
        )
        self.dataset.customers.append(c)
        self._customer_index[cid] = c
        return c

    def _add_order(
        self,
        customer: SyntheticCustomer,
        status: str,
        amount: Decimal | None = None,
        days_ago: int = 0,
    ) -> SyntheticOrder:
        oid = self._order_id()
        o = SyntheticOrder(
            external_order_id=oid,
            customer_ext_id=customer.external_customer_id,
            amount=amount or self._random_amount(),
            currency="INR",
            status=status,
            created_at=self._ago(days_ago, jitter_hours=2),
        )
        self.dataset.orders.append(o)
        self._order_index[oid] = o
        return o

    def _add_payment(
        self,
        order: SyntheticOrder,
        customer: SyntheticCustomer,
        status: str,
        failure_reason: str | None = None,
        method: str | None = None,
        days_ago: int = 0,
        hours_offset: int = 0,
    ) -> SyntheticPayment:
        pid = self._pay_id()
        p = SyntheticPayment(
            external_payment_id=pid if status != "PENDING" else None,
            order_ext_id=order.external_order_id,
            customer_ext_id=customer.external_customer_id,
            amount=order.amount,
            currency=order.currency,
            status=status,
            failure_reason=failure_reason,
            payment_method=method or self._random_method(),
            attempted_at=self._ago(days_ago, hours=hours_offset),
        )
        self.dataset.payments.append(p)
        self._payment_index[pid] = p
        return p

    def _add_checkout_events(
        self,
        customer: SyntheticCustomer,
        order: SyntheticOrder | None,
        scenario: str,           # "success" | "fail" | "abandon" | "fail_then_success" | "fail_then_abandon"
        days_ago: int = 0,
    ) -> None:
        """Emit a logically ordered sequence of checkout events."""
        t = self._ago(days_ago, jitter_hours=1)
        amount = order.amount if order else self._random_amount()
        oid = order.external_order_id if order else None

        def evt(etype: str, offset_minutes: int, meta: dict | None = None) -> None:
            self.dataset.checkout_events.append(SyntheticCheckoutEvent(
                customer_ext_id=customer.external_customer_id,
                order_ext_id=oid,
                event_type=etype,
                amount=amount,
                event_metadata=meta or {},
                occurred_at=t + timedelta(minutes=offset_minutes),
            ))

        if scenario == "success":
            evt("CHECKOUT_STARTED", 0, {"source": "direct"})
            evt("PAYMENT_INITIATED", 2, {"method": self._random_method()})
            evt("PAYMENT_SUCCESS", 4)

        elif scenario == "fail":
            evt("CHECKOUT_STARTED", 0, {"source": "email_campaign"})
            evt("PAYMENT_INITIATED", 2, {"method": self._random_method()})
            evt("PAYMENT_FAILED", 4, {"reason": self._random_failure()})

        elif scenario == "abandon":
            evt("CHECKOUT_STARTED", 0, {"source": "organic"})
            evt("CHECKOUT_ABANDONED", 8)

        elif scenario == "fail_then_success":
            evt("CHECKOUT_STARTED", 0, {"source": "retargeting"})
            evt("PAYMENT_INITIATED", 2, {"method": "CARD"})
            evt("PAYMENT_FAILED", 4, {"reason": "temporary_bank_error"})
            evt("PAYMENT_INITIATED", 10, {"method": "UPI"})
            evt("PAYMENT_SUCCESS", 12)

        elif scenario == "fail_then_abandon":
            evt("CHECKOUT_STARTED", 0, {"source": "push_notification"})
            evt("PAYMENT_INITIATED", 2, {"method": self._random_method()})
            evt("PAYMENT_FAILED", 4, {"reason": self._random_failure()})
            evt("CHECKOUT_ABANDONED", 20)

    def _add_recovery_case(
        self,
        customer: SyntheticCustomer,
        order: SyntheticOrder,
        payment: SyntheticPayment | None,
        case_type: str,
        status: str,
        ground_truth: str,
        days_ago: int = 0,
    ) -> SyntheticRecoveryCase:
        rc = SyntheticRecoveryCase(
            customer_ext_id=customer.external_customer_id,
            order_ext_id=order.external_order_id,
            payment_ext_id=payment.external_payment_id if payment else None,
            case_type=case_type,
            risk_amount=order.amount,
            status=status,
            ground_truth=ground_truth,
            detected_at=self._ago(days_ago),
        )
        self.dataset.recovery_cases.append(rc)
        return rc

    # ── Scenario builders ─────────────────────────────────────────────────────

    def _build_s01_loyal_one_off_failure(self, n: int = 20) -> None:
        """
        S01: Customer with 5–10 prior successful payments then one failure.
        Ground truth: RECOVERABLE
        """
        for i in range(n):
            c = self._add_customer("S01_LOYAL_ONE_OFF_FAILURE", "RECOVERABLE", days_ago=180)
            # 5–8 historical successful orders
            num_hist = self.rng.randint(5, 8)
            for h in range(num_hist):
                old_order = self._add_order(c, "PAID", days_ago=180 - h * 15)
                self._add_payment(old_order, c, "SUCCESS", days_ago=180 - h * 15, hours_offset=1)
                self._add_checkout_events(c, old_order, "success", days_ago=180 - h * 15)

            # The failing order (recent)
            days = self.rng.randint(1, 7)
            fail_order = self._add_order(c, "FAILED", days_ago=days)
            fail_pay = self._add_payment(
                fail_order, c, "FAILED",
                failure_reason=self.rng.choice(["temporary_bank_error", "bank_timeout", "network_error"]),
                days_ago=days, hours_offset=1,
            )
            self._add_checkout_events(c, fail_order, "fail", days_ago=days)
            self._add_recovery_case(
                c, fail_order, fail_pay,
                "PAYMENT_FAILURE", "OPEN", "RECOVERABLE", days_ago=days,
            )

    def _build_s02_new_customer_single_failure(self, n: int = 15) -> None:
        """
        S02: First-time customer, one payment fails.
        Ground truth: RECOVERABLE
        """
        for _ in range(n):
            c = self._add_customer("S02_NEW_CUSTOMER_FAILURE", "RECOVERABLE", days_ago=5)
            days = self.rng.randint(1, 5)
            order = self._add_order(c, "FAILED", days_ago=days)
            pay = self._add_payment(
                order, c, "FAILED",
                failure_reason=self.rng.choice(["insufficient_funds", "authentication_failed", "payment_declined"]),
                days_ago=days, hours_offset=1,
            )
            self._add_checkout_events(c, order, "fail", days_ago=days)
            self._add_recovery_case(
                c, order, pay, "PAYMENT_FAILURE", "OPEN", "RECOVERABLE", days_ago=days,
            )

    def _build_s03_repeated_failures(self, n: int = 12) -> None:
        """
        S03: Customer attempts payment 3–4 times, all fail.
        Ground truth: LOW_RECOVERY_PROBABILITY
        """
        for _ in range(n):
            c = self._add_customer("S03_REPEATED_FAILURES", "LOW_RECOVERY_PROBABILITY", days_ago=30)
            days = self.rng.randint(2, 14)
            order = self._add_order(c, "FAILED", days_ago=days)
            pays = []
            num_failures = self.rng.randint(3, 4)
            for attempt in range(num_failures):
                p = self._add_payment(
                    order, c, "FAILED",
                    failure_reason=self.rng.choice(FAILURE_REASONS),
                    days_ago=days, hours_offset=attempt * 3,
                )
                pays.append(p)
                self._add_checkout_events(c, order, "fail", days_ago=days - attempt)
            # Most recent failure anchors the case
            self._add_recovery_case(
                c, order, pays[-1], "PAYMENT_FAILURE", "OPEN",
                "LOW_RECOVERY_PROBABILITY", days_ago=days,
            )

    def _build_s04_clean_abandonment(self, n: int = 15) -> None:
        """
        S04: Customer starts checkout, no payment ever attempted.
        Ground truth: RECOVERABLE_CHECKOUT
        """
        for _ in range(n):
            c = self._add_customer("S04_CLEAN_ABANDONMENT", "RECOVERABLE_CHECKOUT", days_ago=10)
            days = self.rng.randint(1, 7)
            order = self._add_order(c, "ABANDONED", days_ago=days)
            self._add_checkout_events(c, order, "abandon", days_ago=days)
            self._add_recovery_case(
                c, order, None, "CHECKOUT_ABANDONMENT", "OPEN",
                "RECOVERABLE_CHECKOUT", days_ago=days,
            )

    def _build_s05_fail_then_abandon(self, n: int = 10) -> None:
        """
        S05: Payment fails, then customer abandons.
        Ground truth: RECOVERABLE_CHECKOUT
        """
        for _ in range(n):
            c = self._add_customer("S05_FAIL_THEN_ABANDON", "RECOVERABLE_CHECKOUT", days_ago=15)
            days = self.rng.randint(1, 10)
            order = self._add_order(c, "ABANDONED", days_ago=days)
            pay = self._add_payment(
                order, c, "FAILED",
                failure_reason=self.rng.choice(FAILURE_REASONS),
                days_ago=days, hours_offset=1,
            )
            self._add_checkout_events(c, order, "fail_then_abandon", days_ago=days)
            self._add_recovery_case(
                c, order, pay, "CHECKOUT_ABANDONMENT", "OPEN",
                "RECOVERABLE_CHECKOUT", days_ago=days,
            )

    def _build_s06_high_value_failure(self, n: int = 10) -> None:
        """
        S06: High-value order (≥ ₹10 000) with failed payment.
        Ground truth: RECOVERABLE_HIGH_VALUE
        """
        for _ in range(n):
            c = self._add_customer("S06_HIGH_VALUE_FAILURE", "RECOVERABLE_HIGH_VALUE", days_ago=20)
            days = self.rng.randint(1, 7)
            amount = self._random_high_amount()
            order = self._add_order(c, "FAILED", amount=amount, days_ago=days)
            pay = self._add_payment(
                order, c, "FAILED",
                failure_reason=self.rng.choice(["transaction_limit_exceeded", "do_not_honour", "bank_timeout"]),
                days_ago=days, hours_offset=1,
            )
            self._add_checkout_events(c, order, "fail", days_ago=days)
            self._add_recovery_case(
                c, order, pay, "PAYMENT_FAILURE", "OPEN",
                "RECOVERABLE_HIGH_VALUE", days_ago=days,
            )

    def _build_s07_subscription_failure(self, n: int = 8) -> None:
        """
        S07: Recurring subscription payment fails.
        Ground truth: RECOVERABLE
        """
        for i in range(n):
            c = self._add_customer("S07_SUBSCRIPTION_FAILURE", "RECOVERABLE", days_ago=60)
            # 2–4 previous successful subscription renewals
            for m in range(self.rng.randint(2, 4)):
                old = self._add_order(c, "PAID", days_ago=60 - m * 30)
                self._add_payment(old, c, "SUCCESS", days_ago=60 - m * 30, hours_offset=1)
            days = self.rng.randint(1, 5)
            order = self._add_order(c, "FAILED", days_ago=days)
            pay = self._add_payment(
                order, c, "FAILED",
                failure_reason="insufficient_funds",
                days_ago=days, hours_offset=1,
            )
            self._add_recovery_case(
                c, order, pay, "SUBSCRIPTION_FAILURE", "OPEN",
                "RECOVERABLE", days_ago=days,
            )

    def _build_s08_already_recovered(self, n: int = 8) -> None:
        """
        S08: Payment failed then customer retried and succeeded.
        Case is RECOVERED — not an active risk.
        Ground truth: NOT_AT_RISK
        """
        for _ in range(n):
            c = self._add_customer("S08_ALREADY_RECOVERED", "NOT_AT_RISK", days_ago=30)
            days = self.rng.randint(5, 20)
            order = self._add_order(c, "PAID", days_ago=days)
            fail_pay = self._add_payment(
                order, c, "FAILED",
                failure_reason="temporary_bank_error",
                days_ago=days, hours_offset=1,
            )
            self._add_payment(order, c, "SUCCESS", days_ago=days, hours_offset=3)
            self._add_checkout_events(c, order, "fail_then_success", days_ago=days)
            self._add_recovery_case(
                c, order, fail_pay, "PAYMENT_FAILURE", "RECOVERED",
                "NOT_AT_RISK", days_ago=days,
            )

    def _build_s09_cancelled_order(self, n: int = 5) -> None:
        """
        S09: Customer cancelled the order themselves.
        Ground truth: NOT_RECOVERABLE
        """
        for _ in range(n):
            c = self._add_customer("S09_CANCELLED_ORDER", "NOT_RECOVERABLE", days_ago=15)
            days = self.rng.randint(2, 12)
            order = self._add_order(c, "CANCELLED", days_ago=days)
            # No payment attempt — or a failed one before cancellation
            if self.rng.random() > 0.5:
                pay = self._add_payment(
                    order, c, "FAILED",
                    failure_reason="payment_declined",
                    days_ago=days, hours_offset=1,
                )
            else:
                pay = None
            self._add_checkout_events(c, order, "abandon", days_ago=days)
            self._add_recovery_case(
                c, order, pay, "PAYMENT_FAILURE" if pay else "CHECKOUT_ABANDONMENT",
                "STOPPED", "NOT_RECOVERABLE", days_ago=days,
            )

    def _build_s10_stale_abandonment(self, n: int = 5) -> None:
        """
        S10: Checkout abandoned 60–90 days ago — too old to recover.
        Ground truth: LOW_RECOVERY_PROBABILITY
        """
        for _ in range(n):
            c = self._add_customer("S10_STALE_ABANDONMENT", "LOW_RECOVERY_PROBABILITY", days_ago=90)
            days = self.rng.randint(60, 90)
            order = self._add_order(c, "ABANDONED", days_ago=days)
            self._add_checkout_events(c, order, "abandon", days_ago=days)
            self._add_recovery_case(
                c, order, None, "CHECKOUT_ABANDONMENT", "NOT_RECOVERED",
                "LOW_RECOVERY_PROBABILITY", days_ago=days,
            )

    def _build_s11_mixed_history(self, n: int = 10) -> None:
        """
        S11: Customer with a mix of successes, failures, and recoveries.
        Ground truth: MIXED_BASELINE
        """
        for _ in range(n):
            c = self._add_customer("S11_MIXED_HISTORY", "MIXED_BASELINE", days_ago=120)
            # 2–3 successes
            for s in range(self.rng.randint(2, 3)):
                o = self._add_order(c, "PAID", days_ago=120 - s * 20)
                self._add_payment(o, c, "SUCCESS", days_ago=120 - s * 20, hours_offset=1)
                self._add_checkout_events(c, o, "success", days_ago=120 - s * 20)
            # 1 failure that was recovered
            o2 = self._add_order(c, "PAID", days_ago=30)
            fp = self._add_payment(o2, c, "FAILED", failure_reason="network_error", days_ago=30, hours_offset=1)
            self._add_payment(o2, c, "SUCCESS", days_ago=30, hours_offset=4)
            self._add_checkout_events(c, o2, "fail_then_success", days_ago=30)
            self._add_recovery_case(c, o2, fp, "PAYMENT_FAILURE", "RECOVERED", "NOT_AT_RISK", days_ago=30)
            # 1 current failure
            o3 = self._add_order(c, "FAILED", days_ago=2)
            fp2 = self._add_payment(o3, c, "FAILED", failure_reason="temporary_bank_error", days_ago=2, hours_offset=1)
            self._add_checkout_events(c, o3, "fail", days_ago=2)
            self._add_recovery_case(c, o3, fp2, "PAYMENT_FAILURE", "OPEN", "RECOVERABLE", days_ago=2)

    def _build_s12_purely_successful(self, n: int = 10) -> None:
        """
        S12: All orders paid successfully — no active recovery cases.
        Provides a baseline for the AI agent to learn from.
        """
        for _ in range(n):
            c = self._add_customer("S12_PURELY_SUCCESSFUL", "NO_RISK", days_ago=90)
            for s in range(self.rng.randint(1, 4)):
                o = self._add_order(c, "PAID", days_ago=90 - s * 15)
                self._add_payment(o, c, "SUCCESS", days_ago=90 - s * 15, hours_offset=1)
                self._add_checkout_events(c, o, "success", days_ago=90 - s * 15)

    # ── Public entry point ────────────────────────────────────────────────────

    def _build_test_cases(self) -> None:
        """
        Creates 3 open recovery cases for manual testing of the recovery agent.
        """
        # Customer 1: 7 previous attempts (all SUCCESS).
        # Total attempts = 8. Successful = 7. Success rate = 87.5%.
        # Current failure: bank_timeout, amount ₹1,999.
        c1_id = self._cust_id()
        c1 = SyntheticCustomer(
            external_customer_id=c1_id,
            name="Test Customer Recovery One",
            email="test_recovery_one@example.com",
            phone="+919876543210",
            created_at=self._ago(60),
            scenario_tag="TEST_RECOVERY_CASE",
            ground_truth="RECOVERABLE",
        )
        self.dataset.customers.append(c1)
        self._customer_index[c1_id] = c1

        # 7 historical successful orders & payments
        for h in range(7):
            old_order = self._add_order(c1, "PAID", amount=Decimal("1999.00"), days_ago=45 - h * 5)
            self._add_payment(old_order, c1, "SUCCESS", days_ago=45 - h * 5, hours_offset=1)
            self._add_checkout_events(c1, old_order, "success", days_ago=45 - h * 5)

        # Current failing order & payment
        fail_order1 = self._add_order(c1, "FAILED", amount=Decimal("1999.00"), days_ago=1)
        fail_pay1 = self._add_payment(
            fail_order1, c1, "FAILED",
            failure_reason="bank_timeout",
            days_ago=1, hours_offset=1,
        )
        self._add_checkout_events(c1, fail_order1, "fail", days_ago=1)
        self._add_recovery_case(
            c1, fail_order1, fail_pay1,
            "PAYMENT_FAILURE", "OPEN", "RECOVERABLE", days_ago=1
        )

        # Customer 2: 8 previous attempts (7 SUCCESS, 1 FAILED).
        # Total attempts = 9. Successful = 7. Success rate = 77.8%.
        # Current failure: temporary_bank_error, amount ₹2,499.
        c2_id = self._cust_id()
        c2 = SyntheticCustomer(
            external_customer_id=c2_id,
            name="Test Customer Recovery Two",
            email="test_recovery_two@example.com",
            phone="+919876543211",
            created_at=self._ago(70),
            scenario_tag="TEST_RECOVERY_CASE",
            ground_truth="RECOVERABLE",
        )
        self.dataset.customers.append(c2)
        self._customer_index[c2_id] = c2

        # 7 SUCCESS in history
        for h in range(7):
            old_order = self._add_order(c2, "PAID", amount=Decimal("2499.00"), days_ago=55 - h * 6)
            self._add_payment(old_order, c2, "SUCCESS", days_ago=55 - h * 6, hours_offset=1)
            self._add_checkout_events(c2, old_order, "success", days_ago=55 - h * 6)

        # 1 FAILED in history
        old_failed_order = self._add_order(c2, "FAILED", amount=Decimal("2499.00"), days_ago=10)
        self._add_payment(old_failed_order, c2, "FAILED", failure_reason="network_error", days_ago=10, hours_offset=1)
        self._add_checkout_events(c2, old_failed_order, "fail", days_ago=10)

        # Current failing order & payment
        fail_order2 = self._add_order(c2, "FAILED", amount=Decimal("2499.00"), days_ago=1)
        fail_pay2 = self._add_payment(
            fail_order2, c2, "FAILED",
            failure_reason="temporary_bank_error",
            days_ago=1, hours_offset=1,
        )
        self._add_checkout_events(c2, fail_order2, "fail", days_ago=1)
        self._add_recovery_case(
            c2, fail_order2, fail_pay2,
            "PAYMENT_FAILURE", "OPEN", "RECOVERABLE", days_ago=1
        )

        # Customer 3: 5 previous attempts (5 SUCCESS).
        # Total attempts = 6. Successful = 5. Success rate = 83.3%.
        # Current failure: gateway_timeout, amount ₹1,999.
        c3_id = self._cust_id()
        c3 = SyntheticCustomer(
            external_customer_id=c3_id,
            name="Test Customer Recovery Three",
            email="test_recovery_three@example.com",
            phone="+919876543212",
            created_at=self._ago(50),
            scenario_tag="TEST_RECOVERY_CASE",
            ground_truth="RECOVERABLE",
        )
        self.dataset.customers.append(c3)
        self._customer_index[c3_id] = c3

        # 5 SUCCESS in history
        for h in range(5):
            old_order = self._add_order(c3, "PAID", amount=Decimal("1999.00"), days_ago=35 - h * 6)
            self._add_payment(old_order, c3, "SUCCESS", days_ago=35 - h * 6, hours_offset=1)
            self._add_checkout_events(c3, old_order, "success", days_ago=35 - h * 6)

        # Current failing order & payment
        fail_order3 = self._add_order(c3, "FAILED", amount=Decimal("1999.00"), days_ago=1)
        fail_pay3 = self._add_payment(
            fail_order3, c3, "FAILED",
            failure_reason="gateway_timeout",
            days_ago=1, hours_offset=1,
        )
        self._add_checkout_events(c3, fail_order3, "fail", days_ago=1)
        self._add_recovery_case(
            c3, fail_order3, fail_pay3,
            "PAYMENT_FAILURE", "OPEN", "RECOVERABLE", days_ago=1
        )

    def generate(self) -> SyntheticDataset:
        """
        Run all scenario builders and return the complete dataset.

        Call with the same RANDOM_SEED to always get identical data.
        """
        self._build_s01_loyal_one_off_failure(n=20)
        self._build_s02_new_customer_single_failure(n=15)
        self._build_s03_repeated_failures(n=12)
        self._build_s04_clean_abandonment(n=15)
        self._build_s05_fail_then_abandon(n=10)
        self._build_s06_high_value_failure(n=10)
        self._build_s07_subscription_failure(n=8)
        self._build_s08_already_recovered(n=8)
        self._build_s09_cancelled_order(n=5)
        self._build_s10_stale_abandonment(n=5)
        self._build_s11_mixed_history(n=10)
        self._build_s12_purely_successful(n=10)
        self._build_test_cases()
        return self.dataset


def generate(seed: int = RANDOM_SEED) -> SyntheticDataset:
    """
    Module-level convenience function.
    Always deterministic for the same seed.
    """
    return SyntheticDataGenerator(seed=seed).generate()
