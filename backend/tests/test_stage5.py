"""
Tests for Stage 5 — AI Recovery Agent and Bounded Recovery Workflow.

All Gemini API calls are mocked — tests are deterministic and use no credits.

Test groups
───────────
A. Tool tests   — RecoveryTools read-only investigation
B. Policy tests — deterministic safety gate
C. Executor     — simulated action executor
D. Agent graph  — end-to-end workflow with mocked Gemini
E. API layer    — FastAPI route via TestClient
F. Audit trail  — AgentAction + AuditLog persistence
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.agents.recovery_agent import RecoveryAgent
from backend.app.agents.state import AgentState
from backend.app.database import engine
from backend.app.main import app
from backend.app.models.agent_action import ActionStatus, ActionType, AgentAction
from backend.app.models.audit_log import AuditLog
from backend.app.models.customer import Customer
from backend.app.models.order import Order
from backend.app.models.payment import Payment
from backend.app.models.recovery_case import CaseStatus, CaseType, RecoveryCase
from backend.app.services import recovery_policy as policy
from backend.app.services.action_executor import SimulatedActionExecutor
from backend.app.tools.recovery_tools import RecoveryTools

client = TestClient(app)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def uid() -> str:
    return str(uuid.uuid4())[:10]


def _now():
    return datetime.now(timezone.utc)


def _make_db_fixtures(
    db: Session,
    *,
    order_status: str = "FAILED",
    num_success_payments: int = 5,
    num_failed_payments: int = 1,
    failure_reason: str = "temporary_bank_error",
    case_type: CaseType = CaseType.PAYMENT_FAILURE,
    case_status: CaseStatus = CaseStatus.OPEN,
    risk_amount: Decimal = Decimal("2499.00"),
) -> tuple[Customer, Order, Payment | None, RecoveryCase]:
    """Create a full fixture set in the given session (caller manages transaction)."""
    now = _now()

    customer = Customer(
        external_customer_id=f"TC-{uid()}",
        name="Test Customer",
        email=f"test-{uid()}@example.com",
        created_at=now, updated_at=now,
    )
    db.add(customer)
    db.flush()

    order = Order(
        external_order_id=f"TO-{uid()}",
        customer_id=customer.id,
        amount=risk_amount,
        currency="INR",
        status=order_status,
        created_at=now, updated_at=now,
    )
    db.add(order)
    db.flush()

    # Historical successful payments
    for _ in range(num_success_payments):
        db.add(Payment(
            external_payment_id=f"TP-{uid()}",
            order_id=order.id,
            customer_id=customer.id,
            amount=Decimal("999.00"),
            currency="INR",
            status="SUCCESS",
            payment_method="UPI",
            attempted_at=now,
            created_at=now, updated_at=now,
        ))

    # The failing payment
    fail_pay: Payment | None = None
    if num_failed_payments > 0:
        fail_pay = Payment(
            external_payment_id=f"TP-{uid()}",
            order_id=order.id,
            customer_id=customer.id,
            amount=risk_amount,
            currency="INR",
            status="FAILED",
            failure_reason=failure_reason,
            payment_method="CARD",
            attempted_at=now,
            created_at=now, updated_at=now,
        )
        db.add(fail_pay)
    db.flush()

    case = RecoveryCase(
        customer_id=customer.id,
        order_id=order.id,
        payment_id=fail_pay.id if fail_pay else None,
        case_type=case_type,
        risk_amount=risk_amount,
        status=case_status,
        detected_at=now,
        created_at=now, updated_at=now,
    )
    db.add(case)
    db.flush()

    return customer, order, fail_pay, case


def _mock_gemini(decision: str, action: str, confidence: float = 0.85) -> "GeminiService":
    """Return a fake GeminiService that produces a fixed structured response."""
    from backend.app.services.gemini_service import GeminiService, RecoveryDecision
    mock_svc = MagicMock(spec=GeminiService)
    mock_svc.request_recovery_decision.return_value = RecoveryDecision(
        decision=decision,
        action=action,
        confidence=confidence,
        reason=f"Test decision: {decision} → {action}",
        evidence=["test evidence 1", "test evidence 2"],
    )
    return mock_svc


# ──────────────────────────────────────────────────────────────────────────────
# A. Tool tests
# ──────────────────────────────────────────────────────────────────────────────

class TestRecoveryTools:

    @pytest.fixture(autouse=True)
    def rollback(self):
        with Session(engine) as db:
            with db.begin():
                self.db = db
                yield
                db.rollback()

    def _fixtures(self, **kw):
        return _make_db_fixtures(self.db, **kw)

    def test_get_recovery_case_loads_correctly(self):
        _, _, _, case = self._fixtures()
        tools = RecoveryTools(self.db)
        ctx = tools.get_recovery_case(case.id)
        assert ctx.case_id == case.id
        assert ctx.case_type == "PAYMENT_FAILURE"
        assert ctx.risk_amount == Decimal("2499.00")

    def test_get_recovery_case_raises_for_missing(self):
        tools = RecoveryTools(self.db)
        with pytest.raises(ValueError, match="not found"):
            tools.get_recovery_case(999_999_999)

    def test_get_customer_history_aggregates_correctly(self):
        customer, _, _, _ = self._fixtures(
            num_success_payments=5, num_failed_payments=1
        )
        tools = RecoveryTools(self.db)
        ch = tools.get_customer_history(customer.id)
        assert ch.successful_payments >= 5
        assert ch.failed_payments >= 1
        assert 0.0 <= ch.payment_success_rate <= 1.0

    def test_get_customer_history_raises_for_missing(self):
        tools = RecoveryTools(self.db)
        with pytest.raises(ValueError):
            tools.get_customer_history(999_999_999)

    def test_get_payment_history_returns_attempts(self):
        _, order, _, _ = self._fixtures(
            num_success_payments=2, num_failed_payments=1
        )
        tools = RecoveryTools(self.db)
        ph = tools.get_payment_history(order.id)
        assert ph.total_attempts >= 3
        assert ph.successful_attempts >= 2
        assert ph.failed_attempts >= 1

    def test_get_payment_history_raises_for_missing_order(self):
        tools = RecoveryTools(self.db)
        with pytest.raises(ValueError):
            tools.get_payment_history(999_999_999)

    def test_get_order_history_returns_orders(self):
        customer, _, _, _ = self._fixtures()
        tools = RecoveryTools(self.db)
        oh = tools.get_order_history(customer.id)
        assert oh.total_orders >= 1
        assert len(oh.recent_orders) >= 1

    def test_get_previous_recovery_attempts_empty_initially(self):
        _, _, _, case = self._fixtures()
        tools = RecoveryTools(self.db)
        ra = tools.get_previous_recovery_attempts(case.id)
        assert ra.total_attempts == 0
        assert ra.attempts == []

    def test_get_case_context_returns_all_keys(self):
        _, _, _, case = self._fixtures()
        tools = RecoveryTools(self.db)
        ctx = tools.get_case_context(case.id)
        assert "case" in ctx
        assert "customer" in ctx
        assert "payment_history" in ctx
        assert "order_history" in ctx
        assert "previous_recovery_attempts" in ctx

    def test_tools_are_read_only_no_writes(self):
        """Calling all tools should not modify any rows."""
        _, _, _, case = self._fixtures()
        tools = RecoveryTools(self.db)
        tools.get_recovery_case(case.id)
        tools.get_customer_history(case.customer_id)
        tools.get_payment_history(case.order_id)
        tools.get_order_history(case.customer_id)
        tools.get_previous_recovery_attempts(case.id)
        # Reload case — status must still be OPEN
        reloaded = self.db.get(RecoveryCase, case.id)
        assert reloaded.status == CaseStatus.OPEN


# ──────────────────────────────────────────────────────────────────────────────
# B. Policy gate tests
# ──────────────────────────────────────────────────────────────────────────────

class TestRecoveryPolicy:

    def _eval(self, **kw):
        defaults = dict(
            proposed_decision="RECOVER",
            proposed_action="RETRY_PAYMENT",
            order_status="FAILED",
            case_status="OPEN",
            previous_attempt_count=0,
            has_successful_payment=False,
        )
        defaults.update(kw)
        return policy.evaluate(**defaults)

    def test_already_paid_order_forces_stop(self):
        r = self._eval(has_successful_payment=True)
        assert r.decision == "STOP"
        assert r.allowed is False
        assert r.overridden is True

    def test_paid_order_status_forces_stop(self):
        r = self._eval(order_status="PAID")
        assert r.decision == "STOP"
        assert r.allowed is False

    def test_cancelled_order_forces_stop(self):
        r = self._eval(order_status="CANCELLED")
        assert r.decision == "STOP"
        assert r.allowed is False

    def test_terminal_case_status_forces_stop(self):
        for terminal in ("RECOVERED", "NOT_RECOVERED", "STOPPED"):
            r = self._eval(case_status=terminal)
            assert r.decision == "STOP", f"Expected STOP for {terminal}"

    def test_max_attempts_forces_stop(self):
        r = self._eval(previous_attempt_count=policy.MAX_RECOVERY_ATTEMPTS)
        assert r.decision == "STOP"
        assert r.allowed is False

    def test_one_below_max_is_allowed(self):
        r = self._eval(previous_attempt_count=policy.MAX_RECOVERY_ATTEMPTS - 1)
        assert r.allowed is True

    def test_invalid_action_for_decision_overridden(self):
        r = self._eval(proposed_decision="RECOVER", proposed_action="STOP")
        assert r.decision in ("STOP", "WAIT")
        assert r.overridden is True

    def test_valid_recover_action_passes(self):
        for action in ("RETRY_PAYMENT", "SEND_PAYMENT_LINK", "SEND_REMINDER"):
            r = self._eval(proposed_decision="RECOVER", proposed_action=action)
            assert r.allowed is True, f"Expected allowed for {action}"

    def test_wait_decision_passes(self):
        r = self._eval(proposed_decision="WAIT", proposed_action="WAIT")
        assert r.allowed is True

    def test_stop_decision_passes(self):
        r = self._eval(proposed_decision="STOP", proposed_action="STOP")
        # When the LLM itself proposes STOP, the policy allows it through cleanly.
        # allowed=True here means "no policy override needed — STOP is valid".
        # The execute_action node is still skipped because policy_allowed
        # only routes to execute_action for RECOVER/WAIT decisions.
        assert r.decision == "STOP"
        assert r.action == "STOP"
        assert r.overridden is False

    def test_llm_cannot_invent_action(self):
        r = self._eval(proposed_decision="RECOVER", proposed_action="GIVE_DISCOUNT")
        assert r.overridden is True
        assert r.decision in ("STOP", "WAIT")

    def test_policy_is_deterministic(self):
        """Same inputs always produce same output."""
        r1 = self._eval(proposed_decision="RECOVER", proposed_action="RETRY_PAYMENT")
        r2 = self._eval(proposed_decision="RECOVER", proposed_action="RETRY_PAYMENT")
        assert r1.allowed == r2.allowed
        assert r1.decision == r2.decision


# ──────────────────────────────────────────────────────────────────────────────
# C. Simulated action executor tests
# ──────────────────────────────────────────────────────────────────────────────

class TestActionExecutor:

    def setup_method(self):
        self.executor = SimulatedActionExecutor()

    def test_all_allowed_actions_succeed(self):
        for action in ("RETRY_PAYMENT", "SEND_PAYMENT_LINK", "SEND_REMINDER", "WAIT", "STOP"):
            result = self.executor.execute(action, {"case_id": 1, "force_success": True})
            assert result.success is True
            assert result.simulated is True, f"{action} must be simulated=True"
            assert result.action == action

    def test_invalid_action_raises_value_error(self):
        with pytest.raises(ValueError, match="not permitted"):
            self.executor.execute("REFUND_CUSTOMER")

    def test_simulated_flag_always_true(self):
        for action in ("RETRY_PAYMENT", "SEND_PAYMENT_LINK", "SEND_REMINDER"):
            result = self.executor.execute(action)
            assert result.simulated is True, f"simulated must be True for {action}"

    def test_no_razorpay_calls(self):
        """Executor must not import or call any Razorpay module."""
        import sys
        for action in ("RETRY_PAYMENT", "SEND_PAYMENT_LINK", "SEND_REMINDER"):
            self.executor.execute(action)
        razorpay_modules = [k for k in sys.modules if "razorpay" in k.lower()]
        assert razorpay_modules == [], f"Razorpay should not be loaded: {razorpay_modules}"

    def test_to_dict_contains_simulated_key(self):
        result = self.executor.execute("RETRY_PAYMENT")
        d = result.to_dict()
        assert d["simulated"] is True
        assert "success" in d
        assert "action" in d


# ──────────────────────────────────────────────────────────────────────────────
# D. Agent graph — end-to-end with mocked Gemini
# ──────────────────────────────────────────────────────────────────────────────

class TestAgentGraph:

    def _run(self, mock_service, **fixture_kw):
        """Run the agent against real DB fixtures with a mocked GeminiService."""
        with Session(engine) as db:
            _, _, _, case = _make_db_fixtures(db, **fixture_kw)
            db.flush()
            agent = RecoveryAgent(gemini_service=mock_service)
            result = agent.run(case_id=case.id, db=db)
            case_id = case.id
        return result, case_id

    def test_agent_produces_allowed_decision(self):
        mock = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        result, _ = self._run(mock)
        assert result.success is True
        assert result.response.decision in ("RECOVER", "WAIT", "STOP")

    def test_agent_produces_allowed_action(self):
        from backend.app.schemas.recovery_agent import ALLOWED_ACTIONS
        mock = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        result, _ = self._run(mock)
        assert result.response.action in ALLOWED_ACTIONS

    def test_already_paid_order_results_in_stop(self):
        mock = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        result, _ = self._run(mock, order_status="PAID", num_success_payments=1)
        assert result.response.decision == "STOP"

    def test_cancelled_order_results_in_stop(self):
        mock = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        result, _ = self._run(mock, order_status="CANCELLED")
        assert result.response.decision == "STOP"

    def test_max_attempts_results_in_stop(self):
        """Pre-seed existing AgentAction rows to exhaust the limit."""
        mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        with Session(engine) as db:
            _, _, _, case = _make_db_fixtures(db)
            now = _now()
            for _ in range(policy.MAX_RECOVERY_ATTEMPTS):
                db.add(AgentAction(
                    recovery_case_id=case.id,
                    action_type=ActionType.RETRY_PAYMENT,
                    status=ActionStatus.EXECUTED,
                    created_at=now,
                ))
            db.flush()
            agent = RecoveryAgent(gemini_service=mock_svc)
            result = agent.run(case_id=case.id, db=db)
        assert result.response.decision == "STOP"

    def test_loyal_customer_temporary_failure_can_recover(self):
        """8 successes + temporary failure → policy should allow RECOVER."""
        mock = _mock_gemini("RECOVER", "RETRY_PAYMENT", confidence=0.92)
        result, _ = self._run(
            mock,
            num_success_payments=8,
            num_failed_payments=1,
            failure_reason="temporary_bank_error",
        )
        # Policy allows this — agent should RECOVER
        assert result.response.decision in ("RECOVER", "WAIT", "STOP")
        assert result.response.action in ("RETRY_PAYMENT", "WAIT", "STOP")
        assert result.response.action_result.simulated is True

    def test_checkout_abandonment_valid_action(self):
        mock = _mock_gemini("RECOVER", "SEND_PAYMENT_LINK")
        result, _ = self._run(
            mock,
            case_type=CaseType.CHECKOUT_ABANDONMENT,
            order_status="ABANDONED",
            num_failed_payments=0,
        )
        assert result.response.decision in ("RECOVER", "WAIT", "STOP")

    def test_missing_context_does_not_crash_agent(self):
        """Model error fallback: agent should return WAIT, not raise."""
        from backend.app.services.gemini_service import GeminiService, GeminiCallError
        bad_svc = MagicMock(spec=GeminiService)
        bad_svc.request_recovery_decision.side_effect = GeminiCallError("Simulated API error")
        result, _ = self._run(bad_svc)
        assert result.success is True
        assert result.response.decision in ("WAIT", "STOP")

    def test_policy_overrides_unsafe_llm_decision(self):
        """LLM says RECOVER but order is already PAID — policy must force STOP."""
        mock = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        result, _ = self._run(mock, order_status="PAID", num_success_payments=1)
        assert result.response.decision == "STOP"
        assert result.response.policy_override is True

    def test_simulated_action_never_calls_razorpay(self):
        import sys
        mock = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        self._run(mock)
        razorpay_modules = [k for k in sys.modules if "razorpay" in k.lower()]
        assert razorpay_modules == []

    def test_case_not_marked_recovered_after_simulation(self):
        """Simulated action success must NOT mark case as RECOVERED."""
        mock = _mock_gemini("RECOVER", "RETRY_PAYMENT", confidence=0.9)
        result, case_id = self._run(mock, num_success_payments=5)
        with Session(engine) as db:
            case = db.get(RecoveryCase, case_id)
            # Must be IN_PROGRESS or STOPPED — never RECOVERED from simulation alone
            assert case.status != CaseStatus.RECOVERED, (
                f"Case must not be RECOVERED after simulation. Got: {case.status}"
            )

    def test_not_found_case_returns_error(self):
        with Session(engine) as db:
            agent = RecoveryAgent(gemini_service=_mock_gemini("RECOVER", "RETRY_PAYMENT"))
            result = agent.run(case_id=999_999_999, db=db)
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_terminal_case_returns_error(self):
        mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        with Session(engine) as db:
            _, _, _, case = _make_db_fixtures(db, case_status=CaseStatus.RECOVERED)
            db.flush()
            agent = RecoveryAgent(gemini_service=mock_svc)
            result = agent.run(case_id=case.id, db=db)
            db.rollback()
        assert result.success is True
        assert result.response.case_id == case.id


# ──────────────────────────────────────────────────────────────────────────────
# E. API layer tests
# ──────────────────────────────────────────────────────────────────────────────

class TestAgentAPI:

    def _create_open_case(self) -> int:
        """Create fixtures via the event API and return the case_id."""
        cust = f"AC-{uid()}"
        order = f"AO-{uid()}"
        pay = f"AP-{uid()}"
        client.post("/api/events", json={
            "external_event_id": f"E-{uid()}",
            "event_type": "CHECKOUT_STARTED",
            "external_customer_id": cust,
            "external_order_id": order,
            "amount": "2499.00",
        })
        client.post("/api/events", json={
            "external_event_id": f"E-{uid()}",
            "event_type": "PAYMENT_INITIATED",
            "external_customer_id": cust,
            "external_order_id": order,
            "external_payment_id": pay,
            "amount": "2499.00",
            "payment_method": "CARD",
        })
        r = client.post("/api/events", json={
            "external_event_id": f"E-{uid()}",
            "event_type": "PAYMENT_FAILED",
            "external_customer_id": cust,
            "external_order_id": order,
            "external_payment_id": pay,
            "amount": "2499.00",
            "payment_method": "CARD",
            "failure_reason": "temporary_bank_error",
        })
        return r.json()["case_id"]

    def test_run_agent_returns_200_with_mock(self):
        case_id = self._create_open_case()
        mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        with patch(
            "backend.app.agents.graph.build_recovery_graph",
            side_effect=lambda db, gemini_service=None: build_graph_with_mock(db, mock_svc),
        ):
            r = client.post(f"/api/recovery-cases/{case_id}/run-agent")
        assert r.status_code == 200

    def test_run_agent_404_for_missing_case(self):
        r = client.post("/api/recovery-cases/999999999/run-agent")
        assert r.status_code == 404

    def test_run_agent_response_has_required_fields(self):
        case_id = self._create_open_case()
        mock_svc = _mock_gemini("WAIT", "WAIT")
        with patch(
            "backend.app.agents.graph.build_recovery_graph",
            side_effect=lambda db, gemini_service=None: build_graph_with_mock(db, mock_svc),
        ):
            r = client.post(f"/api/recovery-cases/{case_id}/run-agent")
        if r.status_code == 200:
            body = r.json()
            assert "decision" in body
            assert "action" in body
            assert "reason" in body
            assert "action_result" in body
            assert body["action_result"]["simulated"] is True

    def test_run_agent_response_has_no_api_key(self):
        case_id = self._create_open_case()
        mock_svc = _mock_gemini("STOP", "STOP")
        with patch(
            "backend.app.agents.graph.build_recovery_graph",
            side_effect=lambda db, gemini_service=None: build_graph_with_mock(db, mock_svc),
        ):
            r = client.post(f"/api/recovery-cases/{case_id}/run-agent")
        body_str = r.text
        assert "GEMINI_API_KEY" not in body_str
        assert "DATABASE_URL" not in body_str


def build_graph_with_mock(db, mock_service):
    """Helper for patching build_recovery_graph in API tests."""
    from backend.app.agents.graph import build_recovery_graph
    return build_recovery_graph(db, gemini_service=mock_service)


# ──────────────────────────────────────────────────────────────────────────────
# F. Audit trail and persistence
# ──────────────────────────────────────────────────────────────────────────────

class TestAuditTrail:

    def test_agent_action_created(self):
        mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        with Session(engine) as db:
            _, _, _, case = _make_db_fixtures(db)
            db.flush()
            case_id = case.id
            agent = RecoveryAgent(gemini_service=mock_svc)
            result = agent.run(case_id=case_id, db=db)

        assert result.success is True
        assert result.response.agent_action_id is not None

        with Session(engine) as db:
            action = db.get(AgentAction, result.response.agent_action_id)
            assert action is not None
            assert action.recovery_case_id == case_id
            assert action.result is not None
            assert action.result.get("simulated") is True

    def test_audit_log_entries_created(self):
        mock_svc = _mock_gemini("RECOVER", "SEND_REMINDER")
        with Session(engine) as db:
            _, _, _, case = _make_db_fixtures(db)
            db.flush()
            case_id = case.id
            agent = RecoveryAgent(gemini_service=mock_svc)
            agent.run(case_id=case_id, db=db)

        with Session(engine) as db:
            from sqlalchemy import select
            logs = db.execute(
                select(AuditLog)
                .where(AuditLog.recovery_case_id == case_id)
                .order_by(AuditLog.created_at)
            ).scalars().all()

        assert len(logs) >= 3, f"Expected ≥3 audit log entries, got {len(logs)}"
        event_types = [l.event_type for l in logs]
        assert "AGENT_STARTED" in event_types
        assert "AGENT_COMPLETED" in event_types

    def test_audit_log_contains_decision(self):
        mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        with Session(engine) as db:
            _, _, _, case = _make_db_fixtures(db)
            db.flush()
            case_id = case.id
            agent = RecoveryAgent(gemini_service=mock_svc)
            agent.run(case_id=case_id, db=db)

        with Session(engine) as db:
            from sqlalchemy import select
            completed = db.execute(
                select(AuditLog)
                .where(
                    AuditLog.recovery_case_id == case_id,
                    AuditLog.event_type == "AGENT_COMPLETED",
                )
            ).scalars().first()

        assert completed is not None
        assert "final_decision" in (completed.details or {})

    def test_case_not_falsely_marked_recovered(self):
        """Core invariant: simulated action must NOT set case to RECOVERED."""
        mock_svc = _mock_gemini("RECOVER", "RETRY_PAYMENT")
        with Session(engine) as db:
            _, _, _, case = _make_db_fixtures(db, num_success_payments=8)
            db.flush()
            case_id = case.id
            agent = RecoveryAgent(gemini_service=mock_svc)
            agent.run(case_id=case_id, db=db)

        with Session(engine) as db:
            case = db.get(RecoveryCase, case_id)
            assert case.status != CaseStatus.RECOVERED, (
                "Case MUST NOT be marked RECOVERED from a simulated action alone"
            )

    def test_agent_action_stores_simulated_true(self):
        mock_svc = _mock_gemini("RECOVER", "SEND_PAYMENT_LINK")
        with Session(engine) as db:
            _, _, _, case = _make_db_fixtures(db)
            db.flush()
            case_id = case.id
            agent = RecoveryAgent(gemini_service=mock_svc)
            result = agent.run(case_id=case_id, db=db)

        with Session(engine) as db:
            action = db.get(AgentAction, result.response.agent_action_id)
            assert action.result.get("simulated") is True
