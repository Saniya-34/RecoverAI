"""
Tests for Stage 7 — Bounded Recovery Simulation.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from sqlalchemy.orm import Session

from backend.app.agents.recovery_agent import RecoveryAgent
from backend.app.database import engine
from backend.app.models.recovery_case import CaseStatus, RecoveryCase
from backend.app.services.action_executor import (
    ExecutionResult,
    SimulatedActionExecutor,
)
from backend.tests.test_stage5 import (
    _make_db_fixtures,
    _mock_gemini,
    client,
)


def test_stage7_simulation_success():
    """Verify that a successful RETRY_PAYMENT simulation marks the case RECOVERED."""
    mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")

    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(
            db,
            num_success_payments=0,
        )
        db.flush()
        case_id = case.id

        agent = RecoveryAgent(
            gemini_service=mock_svc,
            executor=SimulatedActionExecutor(),
        )

        with patch(
            "backend.app.services.action_executor."
            "SimulatedActionExecutor._retry_payment"
        ) as mock_retry:

            mock_retry.return_value = ExecutionResult(
                success=True,
                action="RETRY_PAYMENT",
                simulated=True,
                message="Forced Success",
                payment_outcome="SUCCESS",
            )

            result = agent.run(
                case_id=case_id,
                db=db,
            )

            db.commit()

    with Session(engine) as db:
        db_case = db.get(
            RecoveryCase,
            case_id,
        )

        assert db_case.status == CaseStatus.RECOVERED
        assert db_case.recovered_amount == db_case.risk_amount
        assert db_case.resolved_at is not None


def test_stage7_simulation_failure():
    """Verify that a failed RETRY_PAYMENT simulation marks the case NOT_RECOVERED."""
    mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")

    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(
            db,
            num_success_payments=0,
        )
        db.flush()
        case_id = case.id

        agent = RecoveryAgent(
            gemini_service=mock_svc,
            executor=SimulatedActionExecutor(),
        )

        with patch(
            "backend.app.services.action_executor."
            "SimulatedActionExecutor._retry_payment"
        ) as mock_retry:

            mock_retry.return_value = ExecutionResult(
                success=False,
                action="RETRY_PAYMENT",
                simulated=True,
                message="Forced Failure",
                payment_outcome="FAILURE",
            )

            result = agent.run(
                case_id=case_id,
                db=db,
            )

            db.commit()

    with Session(engine) as db:
        db_case = db.get(
            RecoveryCase,
            case_id,
        )

        assert db_case.status == CaseStatus.NOT_RECOVERED
        assert db_case.recovered_amount == Decimal("0.00")
        assert db_case.resolved_at is not None


def test_stage7_simulation_wait():
    """Verify that a RETRY_PAYMENT simulation resulting in WAIT keeps the case IN_PROGRESS."""
    mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")

    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(
            db,
            num_success_payments=0,
        )
        db.flush()
        case_id = case.id

        agent = RecoveryAgent(
            gemini_service=mock_svc,
            executor=SimulatedActionExecutor(),
        )

        with patch(
            "backend.app.services.action_executor."
            "SimulatedActionExecutor._retry_payment"
        ) as mock_retry:

            mock_retry.return_value = ExecutionResult(
                success=False,
                action="RETRY_PAYMENT",
                simulated=True,
                message="Forced Wait",
                payment_outcome="WAIT",
            )

            result = agent.run(
                case_id=case_id,
                db=db,
            )

            db.commit()

    with Session(engine) as db:
        db_case = db.get(
            RecoveryCase,
            case_id,
        )

        assert db_case.status == CaseStatus.IN_PROGRESS
        assert db_case.recovered_amount == Decimal("0.00")
        assert db_case.resolved_at is None


def test_stage7_send_payment_link_does_not_recover():
    """Verify that SEND_PAYMENT_LINK does not mark the case RECOVERED."""
    mock_svc = _mock_gemini(
        "RECOVER",
        "SEND_PAYMENT_LINK",
    )

    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(
            db,
            num_success_payments=0,
        )
        db.flush()
        case_id = case.id

        agent = RecoveryAgent(
            gemini_service=mock_svc,
        )

        with patch(
            "backend.app.services.action_executor."
            "SimulatedActionExecutor._send_payment_link"
        ) as mock_send:

            mock_send.return_value = ExecutionResult(
                success=True,
                action="SEND_PAYMENT_LINK",
                simulated=True,
                message="Link sent successfully",
                payment_outcome="WAIT",
            )

            result = agent.run(
                case_id=case_id,
                db=db,
            )

            db.commit()

    with Session(engine) as db:
        db_case = db.get(
            RecoveryCase,
            case_id,
        )

        assert db_case.status == CaseStatus.IN_PROGRESS
        assert db_case.recovered_amount == Decimal("0.00")


def test_stage7_send_reminder_does_not_recover():
    """Verify that SEND_REMINDER does not mark the case RECOVERED."""
    mock_svc = _mock_gemini(
        "RECOVER",
        "SEND_REMINDER",
    )

    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(
            db,
            num_success_payments=0,
        )
        db.flush()
        case_id = case.id

        agent = RecoveryAgent(
            gemini_service=mock_svc,
        )

        with patch(
            "backend.app.services.action_executor."
            "SimulatedActionExecutor._send_reminder"
        ) as mock_send:

            mock_send.return_value = ExecutionResult(
                success=True,
                action="SEND_REMINDER",
                simulated=True,
                message="Reminder sent successfully",
                payment_outcome="WAIT",
            )

            result = agent.run(
                case_id=case_id,
                db=db,
            )

            db.commit()

    with Session(engine) as db:
        db_case = db.get(
            RecoveryCase,
            case_id,
        )

        assert db_case.status == CaseStatus.IN_PROGRESS
        assert db_case.recovered_amount == Decimal("0.00")


def test_stage7_dashboard_recovered_revenue():
    """Verify that the dashboard summary includes recovered revenue."""
    with Session(engine) as db:
        _, _, _, case1 = _make_db_fixtures(
            db,
            num_success_payments=0,
            risk_amount=Decimal("1500.00"),
        )

        case1.status = CaseStatus.RECOVERED
        case1.recovered_amount = Decimal("1500.00")

        _, _, _, case2 = _make_db_fixtures(
            db,
            num_success_payments=0,
            risk_amount=Decimal("2500.00"),
        )

        case2.status = CaseStatus.RECOVERED
        case2.recovered_amount = Decimal("2500.00")

        db.commit()

    response = client.get(
        "/api/dashboard/summary"
    )

    assert response.status_code == 200

    body = response.json()

    assert float(
        body["recovered_revenue"]
    ) >= 4000.0


def test_stage7_idempotency_resolved_case():
    """Verify duplicate execution on an already RECOVERED case does not double-count."""
    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(
            db,
            num_success_payments=0,
            risk_amount=Decimal("2000.00"),
        )

        case.status = CaseStatus.RECOVERED
        case.recovered_amount = Decimal("2000.00")

        db.commit()

        case_id = case.id

    mock_svc = _mock_gemini(
        "RECOVER",
        "RETRY_PAYMENT",
    )

    with Session(engine) as db:
        agent = RecoveryAgent(
            gemini_service=mock_svc,
        )

        result = agent.run(
            case_id=case_id,
            db=db,
        )

        db.commit()

    assert result.success is True
    assert result.response.recovered_amount == Decimal("2000.00")

    with Session(engine) as db:
        db_case = db.get(
            RecoveryCase,
            case_id,
        )

        assert db_case.recovered_amount == Decimal("2000.00")