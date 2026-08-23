"""
data/synthetic/seed_data.py

Database seeder for RecoverAI Stage 3.

Reads the synthetic dataset produced by scenarios.py and inserts all
records into PostgreSQL using the existing SQLAlchemy configuration.

Usage
─────
  # From the project root (RecoverAI/):
  python -m data.synthetic.seed_data              # seed (idempotent)
  python -m data.synthetic.seed_data --reset      # drop all rows first, then seed
  python -m data.synthetic.seed_data --verify     # print record counts only (no insert)

Design choices
──────────────
- Uses a single transaction: if anything fails the whole operation rolls back.
- Idempotent by default: checks external_customer_id before inserting
  (so re-runs without --reset are safe).
- --reset truncates all 7 tables in the correct FK order before seeding.
- All monetary values are Decimal — never float.
- external_payment_id is None for PENDING payments (no gateway response yet).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── Make sure the project root is on sys.path ─────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.database import engine
import backend.app.models  # noqa: F401 — registers all models with Base.metadata

from backend.app.models.customer import Customer
from backend.app.models.order import Order
from backend.app.models.payment import Payment
from backend.app.models.checkout_event import CheckoutEvent, CheckoutEventType
from backend.app.models.recovery_case import RecoveryCase, CaseType, CaseStatus

from data.synthetic.scenarios import generate, RANDOM_SEED


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _truncate_all(session: Session) -> None:
    """
    Delete all rows from the 7 domain tables in reverse FK order.
    Uses DELETE rather than TRUNCATE CASCADE to be explicit and safe.
    """
    tables = [
        "audit_logs",
        "agent_actions",
        "recovery_cases",
        "checkout_events",
        "payments",
        "orders",
        "customers",
    ]
    for t in tables:
        session.execute(text(f"DELETE FROM {t}"))
    print("[reset] All domain tables cleared.")


def _verify(session: Session) -> None:
    """Print record counts for all domain tables."""
    tables = [
        "customers",
        "orders",
        "payments",
        "checkout_events",
        "recovery_cases",
        "agent_actions",
        "audit_logs",
    ]
    print("\n── RecoverAI Database Record Counts ──────────────────────────────")
    for t in tables:
        count = session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        print(f"  {t:<25} {count:>6}")

    # Scenario breakdowns
    print("\n── Scenario Breakdowns ───────────────────────────────────────────")

    pf = session.execute(
        text("SELECT COUNT(*) FROM payments WHERE status = 'FAILED'")
    ).scalar()
    ps = session.execute(
        text("SELECT COUNT(*) FROM payments WHERE status = 'SUCCESS'")
    ).scalar()
    ca = session.execute(
        text("SELECT COUNT(*) FROM checkout_events WHERE event_type = 'CHECKOUT_ABANDONED'")
    ).scalar()
    rc_open = session.execute(
        text("SELECT COUNT(*) FROM recovery_cases WHERE status = 'OPEN'")
    ).scalar()
    rc_recovered = session.execute(
        text("SELECT COUNT(*) FROM recovery_cases WHERE status = 'RECOVERED'")
    ).scalar()
    hv = session.execute(
        text("SELECT COUNT(*) FROM recovery_cases WHERE risk_amount >= 10000")
    ).scalar()
    rep = session.execute(
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

    print(f"  {'Payment failures':<35} {pf:>6}")
    print(f"  {'Successful payments':<35} {ps:>6}")
    print(f"  {'Checkout abandonments':<35} {ca:>6}")
    print(f"  {'Open recovery cases':<35} {rc_open:>6}")
    print(f"  {'Recovered cases':<35} {rc_recovered:>6}")
    print(f"  {'High-value cases (>=10000)':<35} {hv:>6}")
    print(f"  {'Orders with 3+ failures (repeated)':<35} {rep:>6}")
    print("──────────────────────────────────────────────────────────────────\n")


# ──────────────────────────────────────────────────────────────────────────────
# Main seeder
# ──────────────────────────────────────────────────────────────────────────────

def seed(reset: bool = False) -> None:
    dataset = generate(seed=RANDOM_SEED)

    with Session(engine) as session:
        with session.begin():

            if reset:
                _truncate_all(session)

            # ------------------------------------------------------------------
            # Check idempotency: if first customer already exists, skip
            # ------------------------------------------------------------------
            if not reset:
                existing = session.execute(
                    text("SELECT COUNT(*) FROM customers")
                ).scalar()
                if existing and existing > 0:
                    print(
                        f"[seed] {existing} customers already present. "
                        "Use --reset to reseed from scratch."
                    )
                    _verify(session)
                    return

            print(f"[seed] Generating dataset (seed={RANDOM_SEED}) …")

            # ------------------------------------------------------------------
            # 1. Customers
            # ------------------------------------------------------------------
            cust_map: dict[str, int] = {}  # external_customer_id → db id

            for sc in dataset.customers:
                c = Customer(
                    external_customer_id=sc.external_customer_id,
                    name=sc.name,
                    email=sc.email,
                    phone=sc.phone,
                    created_at=sc.created_at,
                    updated_at=sc.created_at,
                )
                session.add(c)
                session.flush()
                cust_map[sc.external_customer_id] = c.id

            print(f"[seed] Inserted {len(dataset.customers)} customers.")

            # ------------------------------------------------------------------
            # 2. Orders
            # ------------------------------------------------------------------
            order_map: dict[str, int] = {}  # external_order_id → db id

            for so in dataset.orders:
                o = Order(
                    external_order_id=so.external_order_id,
                    customer_id=cust_map[so.customer_ext_id],
                    amount=so.amount,
                    currency=so.currency,
                    status=so.status,
                    created_at=so.created_at,
                    updated_at=so.created_at,
                )
                session.add(o)
                session.flush()
                order_map[so.external_order_id] = o.id

            print(f"[seed] Inserted {len(dataset.orders)} orders.")

            # ------------------------------------------------------------------
            # 3. Payments
            # ------------------------------------------------------------------
            pay_map: dict[str, int] = {}  # external_payment_id → db id

            for sp in dataset.payments:
                p = Payment(
                    external_payment_id=sp.external_payment_id,
                    order_id=order_map[sp.order_ext_id],
                    customer_id=cust_map[sp.customer_ext_id],
                    amount=sp.amount,
                    currency=sp.currency,
                    status=sp.status,
                    failure_reason=sp.failure_reason,
                    payment_method=sp.payment_method,
                    attempted_at=sp.attempted_at,
                    created_at=sp.attempted_at,
                    updated_at=sp.attempted_at,
                )
                session.add(p)
                session.flush()
                if sp.external_payment_id:
                    pay_map[sp.external_payment_id] = p.id

            print(f"[seed] Inserted {len(dataset.payments)} payments.")

            # ------------------------------------------------------------------
            # 4. Checkout events
            # ------------------------------------------------------------------
            for se in dataset.checkout_events:
                e = CheckoutEvent(
                    customer_id=cust_map[se.customer_ext_id],
                    order_id=order_map[se.order_ext_id] if se.order_ext_id else None,
                    event_type=CheckoutEventType(se.event_type),
                    amount=se.amount,
                    event_metadata=se.event_metadata,
                    occurred_at=se.occurred_at,
                    created_at=se.occurred_at,
                )
                session.add(e)

            session.flush()
            print(f"[seed] Inserted {len(dataset.checkout_events)} checkout events.")

            # ------------------------------------------------------------------
            # 5. Recovery cases
            # ------------------------------------------------------------------
            for src in dataset.recovery_cases:
                pay_db_id: int | None = None
                if src.payment_ext_id and src.payment_ext_id in pay_map:
                    pay_db_id = pay_map[src.payment_ext_id]

                rc = RecoveryCase(
                    customer_id=cust_map[src.customer_ext_id],
                    order_id=order_map[src.order_ext_id],
                    payment_id=pay_db_id,
                    case_type=CaseType(src.case_type),
                    risk_amount=src.risk_amount,
                    status=CaseStatus(src.status),
                    detected_at=src.detected_at,
                    created_at=src.detected_at,
                    updated_at=src.detected_at,
                )
                session.add(rc)

            session.flush()
            print(f"[seed] Inserted {len(dataset.recovery_cases)} recovery cases.")

        # transaction committed ─────────────────────────────────────────────
        print("[seed] Transaction committed successfully.")

    # Post-commit verification (new session, read-only)
    with Session(engine) as vsession:
        _verify(vsession)


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RecoverAI synthetic data seeder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m data.synthetic.seed_data              seed (idempotent)
  python -m data.synthetic.seed_data --reset      truncate and reseed
  python -m data.synthetic.seed_data --verify     print counts only
        """,
    )
    parser.add_argument("--reset", action="store_true", help="Clear all rows before seeding")
    parser.add_argument("--verify", action="store_true", help="Print record counts only (no insert)")
    args = parser.parse_args()

    if args.verify:
        with Session(engine) as session:
            _verify(session)
        return

    seed(reset=args.reset)


if __name__ == "__main__":
    main()
