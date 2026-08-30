"""
Tests for Stage 7 — Bounded Recovery Simulation.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.agents.recovery_agent import RecoveryAgent
from backend.app.database import engine, SessionLocal
from backend.app.main import app
from backend.app.models.agent_action import AgentAction
from backend.app.models.recovery_case import CaseStatus, RecoveryCase
from backend.tests.test_stage5 import _make_db_fixtures, _mock_gemini, client

def test_stage7_simulation_success():
    """Verify that a successful RETRY_PAYMENT action simulation marks the case RECOVERED and sets recovered_amount."""
    mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")
    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(db, num_success_payments=0)
        db.flush()
        case_id = case.id
        
        # Patch the execution context to force SUCCESS outcome
        agent = RecoveryAgent(gemini_service=mock_svc)
        with patch("backend.app.services.action_executor.SimulatedActionExecutor._retry_payment") as mock_retry:
            from backend.app.services.action_executor import ExecutionResult
            mock_retry.return_value = ExecutionResult(
                success=True,
                action="RETRY_PAYMENT",
                simulated=True,
                message="Forced Success",
                payment_outcome="SUCCESS"
            )
            result = agent.run(case_id=case_id, db=db)
            db.commit()
            
    with Session(engine) as db:
        db_case = db.get(RecoveryCase, case_id)
        assert db_case.status == CaseStatus.RECOVERED
        assert db_case.recovered_amount == db_case.risk_amount
        assert db_case.resolved_at is not None

def test_stage7_simulation_failure():
    """Verify that a failed RETRY_PAYMENT action simulation does not mark the case RECOVERED and sets status NOT_RECOVERED."""
    mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")
    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(db, num_success_payments=0)
        db.flush()
        case_id = case.id
        
        agent = RecoveryAgent(gemini_service=mock_svc)
        with patch("backend.app.services.action_executor.SimulatedActionExecutor._retry_payment") as mock_retry:
            from backend.app.services.action_executor import ExecutionResult
            mock_retry.return_value = ExecutionResult(
                success=False,
                action="RETRY_PAYMENT",
                simulated=True,
                message="Forced Failure",
                payment_outcome="FAILURE"
            )
            result = agent.run(case_id=case_id, db=db)
            db.commit()
            
    with Session(engine) as db:
        db_case = db.get(RecoveryCase, case_id)
        assert db_case.status == CaseStatus.NOT_RECOVERED
        assert db_case.recovered_amount == Decimal("0.00")
        assert db_case.resolved_at is not None

def test_stage7_simulation_wait():
    """Verify that a RETRY_PAYMENT action simulation resulting in WAIT does not mark the case RECOVERED and keeps it IN_PROGRESS."""
    mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")
    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(db, num_success_payments=0)
        db.flush()
        case_id = case.id
        
        agent = RecoveryAgent(gemini_service=mock_svc)
        with patch("backend.app.services.action_executor.SimulatedActionExecutor._retry_payment") as mock_retry:
            from backend.app.services.action_executor import ExecutionResult
            mock_retry.return_value = ExecutionResult(
                success=False,
                action="RETRY_PAYMENT",
                simulated=True,
                message="Forced Wait",
                payment_outcome="WAIT"
            )
            result = agent.run(case_id=case_id, db=db)
            db.commit()
            
    with Session(engine) as db:
        db_case = db.get(RecoveryCase, case_id)
        assert db_case.status == CaseStatus.IN_PROGRESS
        assert db_case.recovered_amount == Decimal("0.00")
        assert db_case.resolved_at is None

def test_stage7_send_payment_link_does_not_recover():
    """Verify that SEND_PAYMENT_LINK (even when successful) does NOT mark the case RECOVERED or increase recovered_amount."""
    mock_svc = _mock_gemini("RECOVER", "SEND_PAYMENT_LINK")
    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(db, num_success_payments=0)
        db.flush()
        case_id = case.id
        
        agent = RecoveryAgent(gemini_service=mock_svc)
        with patch("backend.app.services.action_executor.SimulatedActionExecutor._send_payment_link") as mock_send:
            from backend.app.services.action_executor import ExecutionResult
            mock_send.return_value = ExecutionResult(
                success=True,
                action="SEND_PAYMENT_LINK",
                simulated=True,
                message="Link sent successfully",
                payment_outcome="WAIT"
            )
            result = agent.run(case_id=case_id, db=db)
            db.commit()
            
    with Session(engine) as db:
        db_case = db.get(RecoveryCase, case_id)
        assert db_case.status == CaseStatus.IN_PROGRESS
        assert db_case.recovered_amount == Decimal("0.00")

def test_stage7_send_reminder_does_not_recover():
    """Verify that SEND_REMINDER (even when successful) does NOT mark the case RECOVERED or increase recovered_amount."""
    mock_svc = _mock_gemini("RECOVER", "SEND_REMINDER")
    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(db, num_success_payments=0)
        db.flush()
        case_id = case.id
        
        agent = RecoveryAgent(gemini_service=mock_svc)
        with patch("backend.app.services.action_executor.SimulatedActionExecutor._send_reminder") as mock_send:
            from backend.app.services.action_executor import ExecutionResult
            mock_send.return_value = ExecutionResult(
                success=True,
                action="SEND_REMINDER",
                simulated=True,
                message="Reminder sent successfully",
                payment_outcome="WAIT"
            )
            result = agent.run(case_id=case_id, db=db)
            db.commit()
            
    with Session(engine) as db:
        db_case = db.get(RecoveryCase, case_id)
        assert db_case.status == CaseStatus.IN_PROGRESS
        assert db_case.recovered_amount == Decimal("0.00")

def test_stage7_dashboard_recovered_revenue():
    """Verify that the dashboard summary includes the correct recovered revenue from PostgreSQL."""
    # Ensure there's a recovered case with recovered_amount > 0
    with Session(engine) as db:
        _, _, _, case1 = _make_db_fixtures(db, num_success_payments=0, risk_amount=Decimal("1500.00"))
        case1.status = CaseStatus.RECOVERED
        case1.recovered_amount = Decimal("1500.00")
        
        _, _, _, case2 = _make_db_fixtures(db, num_success_payments=0, risk_amount=Decimal("2500.00"))
        case2.status = CaseStatus.RECOVERED
        case2.recovered_amount = Decimal("2500.00")
        
        db.commit()
        
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert float(body["recovered_revenue"]) >= 4000.0

def test_stage7_idempotency_resolved_case():
    """Verify duplicate agent execution on already RECOVERED case returns existing result successfully without double-counting."""
    with Session(engine) as db:
        _, _, _, case = _make_db_fixtures(db, num_success_payments=0, risk_amount=Decimal("2000.00"))
        case.status = CaseStatus.RECOVERED
        case.recovered_amount = Decimal("2000.00")
        db.commit()
        case_id = case.id
        
    # Run the agent again on the resolved case
    mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")
    with Session(engine) as db:
        agent = RecoveryAgent(gemini_service=mock_svc)
        result = agent.run(case_id=case_id, db=db)
        db.commit()
        
    assert result.success is True
    assert result.response.recovered_amount == Decimal("2000.00")
    
    # Check that it did not double-count in DB
    with Session(engine) as db:
        db_case = db.get(RecoveryCase, case_id)
        assert db_case.recovered_amount == Decimal("2000.00")
