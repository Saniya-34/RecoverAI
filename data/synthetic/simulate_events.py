"""
data/synthetic/simulate_events.py

Merchant Event Simulator for RecoverAI Stage 4.

Sends realistic event sequences to POST /api/events, exactly as a real
merchant platform would.  Uses only the HTTP API — no direct DB access.

Purpose
───────
- Demonstrate the full event → detection pipeline end-to-end.
- Verify idempotency (re-sending the same event).
- Generate new live recovery cases beyond the Stage 3 seed data.

Usage (server must be running on localhost:8000)
────────────────────────────────────────────────
  # Run all scenarios (default)
  python -m data.synthetic.simulate_events

  # Run a specific scenario only
  python -m data.synthetic.simulate_events --scenario 1

  # Dry run — print payloads without sending
  python -m data.synthetic.simulate_events --dry-run

Scenarios
─────────
  1  Payment failure                 → RecoveryCase PAYMENT_FAILURE created
  2  Successful payment              → No recovery case
  3  Checkout abandonment            → RecoveryCase CHECKOUT_ABANDONMENT created
  4  Duplicate event (idempotency)   → Second call returns duplicate=true
  5  Failure then success (recovery) → Case created then marked RECOVERED
  6  Multiple failures same order    → One case, not two
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Optional requests import ─────────────────────────────────────────────────
try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

BASE_URL = "http://localhost:8000"
EVENTS_ENDPOINT = f"{BASE_URL}/api/events"
CASES_ENDPOINT = f"{BASE_URL}/api/recovery-cases"


# ──────────────────────────────────────────────────────────────────────────────
# HTTP helper
# ──────────────────────────────────────────────────────────────────────────────

def post_event(payload: dict[str, Any], dry_run: bool = False) -> dict[str, Any] | None:
    print(f"\n  → POST /api/events")
    print(f"    payload: {json.dumps(payload, indent=6, default=str)}")

    if dry_run:
        print("    [DRY RUN — not sent]")
        return None

    if not HAS_REQUESTS:
        print("    [ERROR] 'requests' library not installed. Run: pip install requests")
        return None

    resp = _requests.post(EVENTS_ENDPOINT, json=payload, timeout=10)
    print(f"    ← {resp.status_code}: {json.dumps(resp.json(), indent=6, default=str)}")
    return resp.json()


def get_case(case_id: int, dry_run: bool = False) -> None:
    if dry_run:
        return
    if not HAS_REQUESTS:
        return
    resp = _requests.get(f"{CASES_ENDPOINT}/{case_id}", timeout=10)
    print(f"\n  → GET /api/recovery-cases/{case_id}")
    print(f"    ← {resp.status_code}: {json.dumps(resp.json(), indent=6, default=str)}")


def uid() -> str:
    """Generate a short unique event ID."""
    return str(uuid.uuid4())[:8]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 1 — Payment failure → RecoveryCase created
# ──────────────────────────────────────────────────────────────────────────────

def scenario_1(dry_run: bool) -> None:
    print("\n" + "═" * 60)
    print("SCENARIO 1 — Payment failure → RecoveryCase PAYMENT_FAILURE")
    print("═" * 60)

    cust = f"SIM-CUST-{uid()}"
    order = f"SIM-ORD-{uid()}"
    pay = f"SIM-PAY-{uid()}"

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "CHECKOUT_STARTED",
        "external_customer_id": cust,
        "external_order_id": order,
        "amount": "2499.00",
        "currency": "INR",
        "occurred_at": now_iso(),
        "event_metadata": {"source": "simulator_s1"},
    }, dry_run)

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "PAYMENT_INITIATED",
        "external_customer_id": cust,
        "external_order_id": order,
        "external_payment_id": pay,
        "amount": "2499.00",
        "currency": "INR",
        "payment_method": "CARD",
        "occurred_at": now_iso(),
    }, dry_run)

    result = post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "PAYMENT_FAILED",
        "external_customer_id": cust,
        "external_order_id": order,
        "external_payment_id": pay,
        "amount": "2499.00",
        "currency": "INR",
        "payment_method": "CARD",
        "failure_reason": "temporary_bank_error",
        "occurred_at": now_iso(),
    }, dry_run)

    if result and result.get("case_id"):
        get_case(result["case_id"], dry_run)

    print("\n  ✓ Expected: revenue_at_risk=true, case_type=PAYMENT_FAILURE")


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 2 — Successful payment → No recovery case
# ──────────────────────────────────────────────────────────────────────────────

def scenario_2(dry_run: bool) -> None:
    print("\n" + "═" * 60)
    print("SCENARIO 2 — Successful payment → no recovery case")
    print("═" * 60)

    cust = f"SIM-CUST-{uid()}"
    order = f"SIM-ORD-{uid()}"
    pay = f"SIM-PAY-{uid()}"

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "CHECKOUT_STARTED",
        "external_customer_id": cust,
        "external_order_id": order,
        "amount": "999.00",
        "currency": "INR",
        "occurred_at": now_iso(),
    }, dry_run)

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "PAYMENT_INITIATED",
        "external_customer_id": cust,
        "external_order_id": order,
        "external_payment_id": pay,
        "amount": "999.00",
        "payment_method": "UPI",
        "occurred_at": now_iso(),
    }, dry_run)

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "PAYMENT_SUCCESS",
        "external_customer_id": cust,
        "external_order_id": order,
        "external_payment_id": pay,
        "amount": "999.00",
        "payment_method": "UPI",
        "occurred_at": now_iso(),
    }, dry_run)

    print("\n  ✓ Expected: revenue_at_risk=false")


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 3 — Checkout abandonment → RecoveryCase created
# ──────────────────────────────────────────────────────────────────────────────

def scenario_3(dry_run: bool) -> None:
    print("\n" + "═" * 60)
    print("SCENARIO 3 — Checkout abandonment → RecoveryCase CHECKOUT_ABANDONMENT")
    print("═" * 60)

    cust = f"SIM-CUST-{uid()}"
    order = f"SIM-ORD-{uid()}"

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "CHECKOUT_STARTED",
        "external_customer_id": cust,
        "external_order_id": order,
        "amount": "4999.00",
        "currency": "INR",
        "occurred_at": now_iso(),
        "event_metadata": {"source": "mobile_app"},
    }, dry_run)

    result = post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "CHECKOUT_ABANDONED",
        "external_customer_id": cust,
        "external_order_id": order,
        "occurred_at": now_iso(),
    }, dry_run)

    if result and result.get("case_id"):
        get_case(result["case_id"], dry_run)

    print("\n  ✓ Expected: revenue_at_risk=true, case_type=CHECKOUT_ABANDONMENT")


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 4 — Duplicate event (idempotency)
# ──────────────────────────────────────────────────────────────────────────────

def scenario_4(dry_run: bool) -> None:
    print("\n" + "═" * 60)
    print("SCENARIO 4 — Duplicate event → idempotency (no duplicate records)")
    print("═" * 60)

    cust = f"SIM-CUST-{uid()}"
    order = f"SIM-ORD-{uid()}"
    pay = f"SIM-PAY-{uid()}"
    fixed_event_id = f"IDEM-EVT-{uid()}"   # same ID used twice

    payload = {
        "external_event_id": fixed_event_id,
        "event_type": "PAYMENT_FAILED",
        "external_customer_id": cust,
        "external_order_id": order,
        "external_payment_id": pay,
        "amount": "1499.00",
        "payment_method": "NETBANKING",
        "failure_reason": "bank_timeout",
        "occurred_at": now_iso(),
    }

    print("\n  First submission:")
    post_event(payload, dry_run)

    print("\n  Second submission (same external_event_id):")
    post_event(payload, dry_run)

    print("\n  ✓ Expected: second call returns duplicate=true, no new DB rows")


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 5 — Failure then success (case auto-recovered)
# ──────────────────────────────────────────────────────────────────────────────

def scenario_5(dry_run: bool) -> None:
    print("\n" + "═" * 60)
    print("SCENARIO 5 — Failure then success → case marked RECOVERED")
    print("═" * 60)

    cust = f"SIM-CUST-{uid()}"
    order = f"SIM-ORD-{uid()}"
    pay1 = f"SIM-PAY-{uid()}"
    pay2 = f"SIM-PAY-{uid()}"

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "CHECKOUT_STARTED",
        "external_customer_id": cust,
        "external_order_id": order,
        "amount": "9999.00",
        "occurred_at": now_iso(),
    }, dry_run)

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "PAYMENT_INITIATED",
        "external_customer_id": cust,
        "external_order_id": order,
        "external_payment_id": pay1,
        "amount": "9999.00",
        "payment_method": "CARD",
        "occurred_at": now_iso(),
    }, dry_run)

    fail_result = post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "PAYMENT_FAILED",
        "external_customer_id": cust,
        "external_order_id": order,
        "external_payment_id": pay1,
        "amount": "9999.00",
        "payment_method": "CARD",
        "failure_reason": "card_expired",
        "occurred_at": now_iso(),
    }, dry_run)

    print("\n  → Customer retries with UPI …")

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "PAYMENT_INITIATED",
        "external_customer_id": cust,
        "external_order_id": order,
        "external_payment_id": pay2,
        "amount": "9999.00",
        "payment_method": "UPI",
        "occurred_at": now_iso(),
    }, dry_run)

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "PAYMENT_SUCCESS",
        "external_customer_id": cust,
        "external_order_id": order,
        "external_payment_id": pay2,
        "amount": "9999.00",
        "payment_method": "UPI",
        "occurred_at": now_iso(),
    }, dry_run)

    if fail_result and fail_result.get("case_id"):
        get_case(fail_result["case_id"], dry_run)

    print("\n  ✓ Expected: case created on FAILED, status=RECOVERED after SUCCESS")


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 6 — Multiple failures same order → only ONE case
# ──────────────────────────────────────────────────────────────────────────────

def scenario_6(dry_run: bool) -> None:
    print("\n" + "═" * 60)
    print("SCENARIO 6 — Multiple failures, same order → one recovery case")
    print("═" * 60)

    cust = f"SIM-CUST-{uid()}"
    order = f"SIM-ORD-{uid()}"

    post_event({
        "external_event_id": f"EVT-{uid()}",
        "event_type": "CHECKOUT_STARTED",
        "external_customer_id": cust,
        "external_order_id": order,
        "amount": "2999.00",
        "occurred_at": now_iso(),
    }, dry_run)

    for attempt in range(1, 4):
        pay = f"SIM-PAY-{uid()}"
        post_event({
            "external_event_id": f"EVT-{uid()}",
            "event_type": "PAYMENT_INITIATED",
            "external_customer_id": cust,
            "external_order_id": order,
            "external_payment_id": pay,
            "amount": "2999.00",
            "payment_method": "CARD",
            "occurred_at": now_iso(),
        }, dry_run)
        result = post_event({
            "external_event_id": f"EVT-{uid()}",
            "event_type": "PAYMENT_FAILED",
            "external_customer_id": cust,
            "external_order_id": order,
            "external_payment_id": pay,
            "amount": "2999.00",
            "payment_method": "CARD",
            "failure_reason": "insufficient_funds",
            "occurred_at": now_iso(),
        }, dry_run)
        if result:
            print(f"\n    Attempt {attempt}: case_id={result.get('case_id')} "
                  f"revenue_at_risk={result.get('revenue_at_risk')}")

    print("\n  ✓ Expected: all three responses reference the SAME case_id")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

SCENARIOS = {
    1: scenario_1,
    2: scenario_2,
    3: scenario_3,
    4: scenario_4,
    5: scenario_5,
    6: scenario_6,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RecoverAI merchant event simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scenario", type=int, choices=list(SCENARIOS),
        help="Run a single scenario (1–6). Omit to run all.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print payloads without sending HTTP requests.",
    )
    args = parser.parse_args()

    if not HAS_REQUESTS and not args.dry_run:
        print(
            "The 'requests' library is not installed.\n"
            "Install it with:  pip install requests\n"
            "Or use --dry-run to print payloads only."
        )
        sys.exit(1)

    targets = {args.scenario: SCENARIOS[args.scenario]} if args.scenario else SCENARIOS

    for num, fn in targets.items():
        fn(args.dry_run)
        time.sleep(0.1)   # brief pause between scenarios

    print("\n\nSimulation complete.\n")


if __name__ == "__main__":
    main()
