# RecoverAI — Synthetic Data (Stage 3)

This module generates and seeds a realistic synthetic merchant dataset
for testing and demonstrating the RecoverAI revenue-recovery system.

All data is **fictional**. No real customer names, emails, or payment
information are used.

---

## Prerequisites

1. Docker PostgreSQL container must be running:
   ```cmd
   docker compose up -d db
   ```

2. Alembic migrations must have been applied:
   ```cmd
   backend\venv\Scripts\alembic.exe upgrade head
   ```

3. All commands below must be run from the **project root**
   (`RecoverAI/`), not from inside `data/`.

---

## Commands

### Seed the database (idempotent)

```cmd
backend\venv\Scripts\python.exe -m data.synthetic.seed_data
```

Safe to run multiple times — skips insertion if data already exists.

---

### Reset and reseed (clears all rows first)

```cmd
backend\venv\Scripts\python.exe -m data.synthetic.seed_data --reset
```

Deletes all rows from the 7 domain tables in FK-safe order, then reseeds.

---

### Verify record counts (no insert)

```cmd
backend\venv\Scripts\python.exe -m data.synthetic.seed_data --verify
```

Prints a summary table of all record counts and scenario breakdowns.

---

## File Structure

```
data/
└── synthetic/
    ├── README.md          ← this file
    ├── __init__.py
    ├── scenarios.py       ← pure data generation (no DB access)
    └── seed_data.py       ← DB seeder + CLI
```

---

## Scenario Catalogue

| Tag | Description | Ground Truth |
|-----|-------------|--------------|
| S01 | Loyal customer, one-off failure (5–8 prior successes) | RECOVERABLE |
| S02 | New customer, first payment fails | RECOVERABLE |
| S03 | Repeated failures (3–4 consecutive) | LOW_RECOVERY_PROBABILITY |
| S04 | Clean checkout abandonment | RECOVERABLE_CHECKOUT |
| S05 | Payment fails then customer abandons | RECOVERABLE_CHECKOUT |
| S06 | High-value order (≥ ₹10 000) fails | RECOVERABLE_HIGH_VALUE |
| S07 | Subscription/recurring payment fails | RECOVERABLE |
| S08 | Failure then self-recovered (retry succeeded) | NOT_AT_RISK |
| S09 | Order cancelled by customer | NOT_RECOVERABLE |
| S10 | Stale abandonment (60–90 days ago) | LOW_RECOVERY_PROBABILITY |
| S11 | Mixed history (successes + failures + recovery) | MIXED_BASELINE |
| S12 | Purely successful — no risk | NO_RISK |

---

## Ground Truth

Each `RecoveryCase` in the dataset carries a `ground_truth` label stored
in `scenarios.py` (as a Python attribute on `SyntheticRecoveryCase`).

This label is **not stored in the database** — it exists only in the
in-memory generator output for offline evaluation of the future AI agent.

| Label | Meaning |
|-------|---------|
| RECOVERABLE | High likelihood of recovery via outreach |
| RECOVERABLE_CHECKOUT | Abandonment — reminder likely to convert |
| RECOVERABLE_HIGH_VALUE | High value — prioritise recovery |
| LOW_RECOVERY_PROBABILITY | Multiple failures or stale — low confidence |
| NOT_AT_RISK | Already resolved, no action needed |
| NOT_RECOVERABLE | Cancelled — do not attempt |
| MIXED_BASELINE | Mix of outcomes — used as baseline |
| NO_RISK | All successful — control group |

---

## Random Seed

Data is generated with `random.Random(seed=42)` — always deterministic.

To generate a different dataset layout, change `RANDOM_SEED` in
`scenarios.py` and reseed with `--reset`.
