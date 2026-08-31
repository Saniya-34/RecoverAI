"""
backend/app/agents/graph.py

LangGraph workflow for the RecoverAI recovery agent.

Workflow
────────
1. load_case
2. investigate_case
3. analyze
4. policy_gate
5. execute_action
6. record_result
7. END

Payment execution behavior
──────────────────────────
When USE_RAZORPAY_TEST_MODE=true:

    RETRY_PAYMENT
        ↓
    Razorpay Test Mode Payment Link
        ↓
    WAIT
        ↓
    Customer completes payment
        ↓
    Razorpay Webhook
        ↓
    RecoveryCase → RECOVERED

    SEND_PAYMENT_LINK
        ↓
    Razorpay Test Mode Payment Link
        ↓
    WAIT
        ↓
    Razorpay Webhook
        ↓
    RecoveryCase → RECOVERED

When Razorpay Test Mode is disabled, the existing simulated
executor is used.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from backend.app.agents.state import AgentState
from backend.app.models.agent_action import (
    ActionStatus,
    ActionType,
    AgentAction,
)
from backend.app.models.audit_log import AuditLog
from backend.app.models.order import Order
from backend.app.models.payment import Payment
from backend.app.models.recovery_case import (
    CaseStatus,
    RecoveryCase,
)
from backend.app.services import executor
from backend.app.services import recovery_policy as policy
from backend.app.services.gemini_service import (
    GeminiCallError,
    GeminiConfigError,
    GeminiParseError,
    GeminiService,
    create_gemini_service,
)
from backend.app.tools.recovery_tools import RecoveryTools


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Audit helper
# ──────────────────────────────────────────────────────────────────────────────

def _audit(
    event_type: str,
    details: dict | None = None,
) -> dict:
    """Create a standard agent audit event."""

    return {
        "event_type": event_type,
        "actor": "AGENT",
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Node 1: load_case
# ──────────────────────────────────────────────────────────────────────────────

def make_load_case_node(db: Session):

    def load_case(state: AgentState) -> dict:

        import os
        import time

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            time.sleep(0.3)

        tools = RecoveryTools(db)

        case_id = state["recovery_case_id"]

        audit_events = list(
            state.get("audit_events", [])
        )

        errors = list(
            state.get("errors", [])
        )

        audit_events.append(
            _audit(
                "AGENT_STARTED",
                {
                    "case_id": case_id,
                },
            )
        )

        try:

            case = tools.get_recovery_case(case_id)

        except ValueError as exc:

            errors.append(str(exc))

            logger.error(
                "load_case: %s",
                exc,
            )

            return {
                "errors": errors,
                "audit_events": audit_events,
                "completed": True,
                "final_decision": "STOP",
                "final_action": "STOP",
                "policy_allowed": False,
                "policy_reason": str(exc),
                "policy_overridden": False,
            }

        audit_events.append(
            _audit(
                "CASE_LOADED",
                {
                    "case_type": case.case_type,
                    "risk_amount": str(case.risk_amount),
                    "case_status": case.status,
                },
            )
        )

        logger.info(
            "load_case: case %d type=%s status=%s risk=₹%s",
            case_id,
            case.case_type,
            case.status,
            case.risk_amount,
        )

        return {
            "case_type": case.case_type,
            "case_status": case.status,
            "risk_amount": str(case.risk_amount),
            "recovered_amount": str(case.recovered_amount),
            "currency": case.currency,
            "customer_id": case.customer_id,
            "order_id": case.order_id,
            "payment_id": case.payment_id,
            "failure_reason": case.failure_reason,
            "errors": errors,
            "audit_events": audit_events,
            "completed": False,
        }

    return load_case


# ──────────────────────────────────────────────────────────────────────────────
# Node 2: investigate_case
# ──────────────────────────────────────────────────────────────────────────────

def make_investigate_node(db: Session):

    def investigate_case(state: AgentState) -> dict:

        if state.get("completed"):
            return {}

        import os
        import time

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            time.sleep(0.5)

        tools = RecoveryTools(db)

        audit_events = list(
            state.get("audit_events", [])
        )

        errors = list(
            state.get("errors", [])
        )

        # ── Customer history ────────────────────────────────────────────────

        try:

            ch = tools.get_customer_history(
                state["customer_id"]
            )

            audit_events.append(
                _audit(
                    "CUSTOMER_HISTORY_RETRIEVED",
                    {
                        "successful_payments": ch.successful_payments,
                        "failed_payments": ch.failed_payments,
                        "success_rate": ch.payment_success_rate,
                    },
                )
            )

        except ValueError as exc:

            errors.append(
                f"customer_history: {exc}"
            )

            ch = None

        # ── Payment history ─────────────────────────────────────────────────

        try:

            ph = tools.get_payment_history(
                state["order_id"]
            )

            audit_events.append(
                _audit(
                    "PAYMENT_HISTORY_RETRIEVED",
                    {
                        "total_attempts": ph.total_attempts,
                        "failed": ph.failed_attempts,
                    },
                )
            )

        except ValueError as exc:

            errors.append(
                f"payment_history: {exc}"
            )

            ph = None

        # ── Order history ───────────────────────────────────────────────────

        try:

            oh = tools.get_order_history(
                state["customer_id"],
                limit=5,
            )

        except ValueError as exc:

            errors.append(
                f"order_history: {exc}"
            )

            oh = None

        # ── Previous recovery attempts ──────────────────────────────────────

        try:

            ra = tools.get_previous_recovery_attempts(
                state["recovery_case_id"]
            )

            audit_events.append(
                _audit(
                    "RECOVERY_ATTEMPTS_RETRIEVED",
                    {
                        "total": ra.total_attempts,
                    },
                )
            )

        except ValueError as exc:

            errors.append(
                f"recovery_attempts: {exc}"
            )

            ra = None

        # ── Current order status ────────────────────────────────────────────

        order = db.get(
            Order,
            state["order_id"],
        )

        order_status = (
            order.status
            if order
            else "UNKNOWN"
        )

        has_successful = (
            order_status == "PAID"
        ) or (
            ph.successful_attempts > 0
            if ph
            else False
        )

        return {
            "customer_history": {
                "total_orders": ch.total_orders if ch else 0,
                "successful_payments": (
                    ch.successful_payments
                    if ch
                    else 0
                ),
                "failed_payments": (
                    ch.failed_payments
                    if ch
                    else 0
                ),
                "payment_success_rate": (
                    ch.payment_success_rate
                    if ch
                    else 0.0
                ),
                "recent_failure_reasons": (
                    ch.recent_failure_reasons
                    if ch
                    else []
                ),
            },
            "payment_history": {
                "total_attempts": (
                    ph.total_attempts
                    if ph
                    else 0
                ),
                "successful_attempts": (
                    ph.successful_attempts
                    if ph
                    else 0
                ),
                "failed_attempts": (
                    ph.failed_attempts
                    if ph
                    else 0
                ),
                "attempts": [
                    {
                        "status": a.status,
                        "failure_reason": a.failure_reason,
                        "payment_method": a.payment_method,
                        "attempted_at": (
                            a.attempted_at.isoformat()
                            if a.attempted_at
                            else None
                        ),
                    }
                    for a in (
                        ph.attempts
                        if ph
                        else []
                    )
                ],
            },
            "order_history": {
                "total_orders": (
                    oh.total_orders
                    if oh
                    else 0
                ),
                "recent_statuses": [
                    o.status
                    for o in (
                        oh.recent_orders
                        if oh
                        else []
                    )
                ],
            },
            "previous_recovery_attempts": {
                "total": (
                    ra.total_attempts
                    if ra
                    else 0
                ),
                "actions": [
                    {
                        "action_type": a.action_type,
                        "status": a.status,
                    }
                    for a in (
                        ra.attempts
                        if ra
                        else []
                    )
                ],
            },
            "order_status": order_status,
            "has_successful_payment": has_successful,
            "previous_attempt_count": (
                ra.total_attempts
                if ra
                else 0
            ),
            "errors": errors,
            "audit_events": audit_events,
        }

    return investigate_case


# ──────────────────────────────────────────────────────────────────────────────
# Node 3: analyze
# ──────────────────────────────────────────────────────────────────────────────

def make_analyze_node(
    gemini_service: GeminiService | None = None,
):

    def analyze(state: AgentState) -> dict:

        if state.get("completed"):
            return {}

        import os
        import time

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            time.sleep(1.0)

        audit_events = list(
            state.get("audit_events", [])
        )

        errors = list(
            state.get("errors", [])
        )

        case_context = {
            "case": {
                "type": state.get("case_type"),
                "risk_amount": state.get("risk_amount"),
                "currency": state.get("currency"),
                "failure_reason": state.get("failure_reason"),
            },
            "customer": state.get(
                "customer_history",
                {},
            ),
            "payment_history": state.get(
                "payment_history",
                {},
            ),
            "order": {
                "status": state.get(
                    "order_status"
                ),
                "history": state.get(
                    "order_history",
                    {},
                ),
            },
            "previous_recovery_attempts": state.get(
                "previous_recovery_attempts",
                {},
            ),
        }

        try:

            service = (
                gemini_service
                or create_gemini_service()
            )

            decision_obj = (
                service.request_recovery_decision(
                    case_context
                )
            )

            audit_events.append(
                _audit(
                    "DECISION_MADE",
                    {
                        "decision": decision_obj.decision,
                        "action": decision_obj.action,
                        "confidence": decision_obj.confidence,
                    },
                )
            )

            logger.info(
                "analyze: decision=%s action=%s confidence=%.2f",
                decision_obj.decision,
                decision_obj.action,
                decision_obj.confidence,
            )

            return {
                "proposed_decision": decision_obj.decision,
                "proposed_action": decision_obj.action,
                "confidence": decision_obj.confidence,
                "decision_reason": decision_obj.reason,
                "evidence": list(
                    decision_obj.evidence
                ),
                "errors": errors,
                "audit_events": audit_events,
            }

        except GeminiConfigError as exc:

            logger.error(
                "analyze: Gemini config error — %s",
                exc,
            )

            errors.append(
                f"gemini_config_error: {exc}"
            )

            audit_events.append(
                _audit(
                    "AGENT_ERROR",
                    {
                        "error": "Gemini not configured",
                    },
                )
            )

        except GeminiCallError as exc:

            logger.error(
                "analyze: Gemini API call failed — %s",
                exc,
            )

            errors.append(
                f"gemini_call_error: {exc}"
            )

            audit_events.append(
                _audit(
                    "AGENT_ERROR",
                    {
                        "error": "Gemini API call failed",
                    },
                )
            )

        except GeminiParseError as exc:

            logger.error(
                "analyze: Gemini response parse error — %s",
                exc,
            )

            errors.append(
                f"gemini_parse_error: {exc}"
            )

            audit_events.append(
                _audit(
                    "AGENT_ERROR",
                    {
                        "error": "Gemini response invalid",
                    },
                )
            )

        except Exception as exc:

            logger.error(
                "analyze: unexpected error — %s",
                exc,
            )

            errors.append(
                f"analyze_error: {exc}"
            )

            audit_events.append(
                _audit(
                    "AGENT_ERROR",
                    {
                        "error": "Unexpected analysis error",
                    },
                )
            )

        # Never guess a recovery action when Gemini fails.

        return {
            "proposed_decision": "WAIT",
            "proposed_action": "WAIT",
            "confidence": 0.0,
            "decision_reason": (
                "Model unavailable or response invalid "
                "— defaulting to WAIT."
            ),
            "evidence": [],
            "errors": errors,
            "audit_events": audit_events,
        }

    return analyze


# ──────────────────────────────────────────────────────────────────────────────
# Node 4: policy_gate
# ──────────────────────────────────────────────────────────────────────────────

def make_policy_gate_node():

    def policy_gate(state: AgentState) -> dict:

        if state.get("completed"):
            return {}

        import os
        import time

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            time.sleep(0.3)

        audit_events = list(
            state.get("audit_events", [])
        )

        result = policy.evaluate(
            proposed_decision=state.get(
                "proposed_decision",
                "STOP",
            ),
            proposed_action=state.get(
                "proposed_action",
                "STOP",
            ),
            order_status=state.get(
                "order_status",
                "UNKNOWN",
            ),
            case_status=state.get(
                "case_status",
                "OPEN",
            ),
            previous_attempt_count=state.get(
                "previous_attempt_count",
                0,
            ),
            has_successful_payment=state.get(
                "has_successful_payment",
                False,
            ),
        )

        audit_events.append(
            _audit(
                "POLICY_CHECKED",
                {
                    "allowed": result.allowed,
                    "final_decision": result.decision,
                    "final_action": result.action,
                    "overridden": result.overridden,
                    "reason": result.reason,
                },
            )
        )

        logger.info(
            "policy_gate: allowed=%s decision=%s action=%s overridden=%s",
            result.allowed,
            result.decision,
            result.action,
            result.overridden,
        )

        return {
            "policy_allowed": result.allowed,
            "final_decision": result.decision,
            "final_action": result.action,
            "policy_reason": result.reason,
            "policy_overridden": result.overridden,
            "audit_events": audit_events,
        }

    return policy_gate


# ──────────────────────────────────────────────────────────────────────────────
# Node 5: execute_action
# ──────────────────────────────────────────────────────────────────────────────

def make_execute_action_node(executor_override=None):

    def execute_action(state: AgentState) -> dict:

        if state.get("completed"):
            return {}

        import os
        import time

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            time.sleep(0.6)

        audit_events = list(
            state.get("audit_events", [])
        )

        errors = list(
            state.get("errors", [])
        )

        action = state.get(
            "final_action",
            "STOP",
        )

        context = {
            "case_id": state.get(
                "recovery_case_id"
            ),
            "customer_id": state.get(
                "customer_id"
            ),
            "risk_amount": state.get(
                "risk_amount"
            ),
        }

        try:

            # The executor is selected centrally by:
            #
            # backend/app/services/__init__.py
            #
            # If USE_RAZORPAY_TEST_MODE=true:
            #     RazorpayTestModeExecutor
            #
            # Otherwise:
            #     SimulatedActionExecutor

            action_executor = executor_override or executor

            exec_result = action_executor.execute(
                action,
                context,
            )

            is_simulated = getattr(
                exec_result,
                "simulated",
                True,
            )

            # ── RETRY_PAYMENT ───────────────────────────────────────────────

            if action == "RETRY_PAYMENT":

                if is_simulated:

                    audit_events.append(
                        _audit(
                            "PAYMENT_RETRY_SIMULATED",
                            {
                                "amount": context.get(
                                    "risk_amount"
                                ),
                            },
                        )
                    )

                    if exec_result.success:

                        audit_events.append(
                            _audit(
                                "PAYMENT_SUCCESS_SIMULATED",
                                {
                                    "amount": context.get(
                                        "risk_amount"
                                    ),
                                },
                            )
                        )

                    else:

                        audit_events.append(
                            _audit(
                                "PAYMENT_FAILURE_SIMULATED",
                                {
                                    "reason": exec_result.message,
                                },
                            )
                        )

                else:

                    # Razorpay Test Mode:
                    # payment-link creation does NOT mean payment success.

                    audit_events.append(
                        _audit(
                            "RAZORPAY_PAYMENT_LINK_CREATED",
                            {
                                "payment_link_id": getattr(
                                    exec_result,
                                    "payment_link_id",
                                    None,
                                ),
                                "payment_link_url": getattr(
                                    exec_result,
                                    "payment_link_url",
                                    None,
                                ),
                                "amount": context.get(
                                    "risk_amount"
                                ),
                            },
                        )
                    )

            # ── SEND_PAYMENT_LINK ──────────────────────────────────────────

            elif action == "SEND_PAYMENT_LINK":

                if is_simulated:

                    audit_events.append(
                        _audit(
                            "PAYMENT_LINK_SIMULATED",
                            {
                                "amount": context.get(
                                    "risk_amount"
                                ),
                            },
                        )
                    )

                else:

                    audit_events.append(
                        _audit(
                            "RAZORPAY_PAYMENT_LINK_CREATED",
                            {
                                "payment_link_id": getattr(
                                    exec_result,
                                    "payment_link_id",
                                    None,
                                ),
                                "payment_link_url": getattr(
                                    exec_result,
                                    "payment_link_url",
                                    None,
                                ),
                                "amount": context.get(
                                    "risk_amount"
                                ),
                            },
                        )
                    )

            # ── SEND_REMINDER ───────────────────────────────────────────────

            elif action == "SEND_REMINDER":

                audit_events.append(
                    _audit(
                        "NOTIFICATION_SIMULATED",
                        {
                            "action": action,
                        },
                    )
                )

            # ── WAIT ───────────────────────────────────────────────────────

            elif action == "WAIT":

                audit_events.append(
                    _audit(
                        "AGENT_WAITING",
                        {
                            "reason": (
                                "Waiting for external signal."
                            ),
                        },
                    )
                )

            # ── STOP ───────────────────────────────────────────────────────

            elif action == "STOP":

                audit_events.append(
                    _audit(
                        "RECOVERY_STOPPED",
                        {},
                    )
                )

            # ── Recovered amount ───────────────────────────────────────────
            #
            # IMPORTANT:
            #
            # Razorpay payment-link creation is NOT successful payment.
            #
            # Therefore:
            #
            # Razorpay -> recovered_amount = 0
            #
            # The webhook will update the case after payment succeeds.
            #
            # Simulation -> a successful simulated retry can immediately
            # update recovered_amount.

            recovered_amount = 0

            if (
                is_simulated
                and action == "RETRY_PAYMENT"
                and exec_result.success
                and getattr(
                    exec_result,
                    "payment_outcome",
                    "",
                ) == "SUCCESS"
            ):

                recovered_amount = context.get(
                    "risk_amount",
                    0,
                )

            # ── Convert result to dictionary ───────────────────────────────

            action_result = exec_result.to_dict()

            # Razorpay payment link ID

            payment_link_id = getattr(
                exec_result,
                "payment_link_id",
                None,
            )

            # Razorpay payment link URL

            payment_link_url = getattr(
                exec_result,
                "payment_link_url",
                None,
            )

            if payment_link_id:

                action_result[
                    "payment_link_id"
                ] = payment_link_id

            if payment_link_url:

                action_result[
                    "payment_link_url"
                ] = payment_link_url

            return {
                "action_result": action_result,
                "recovered_amount": recovered_amount,
                "errors": errors,
                "audit_events": audit_events,
            }

        except ValueError as exc:

            errors.append(
                f"execute_error: {exc}"
            )

            audit_events.append(
                _audit(
                    "AGENT_ERROR",
                    {
                        "error": str(exc),
                    },
                )
            )

            return {
                "action_result": {
                    "success": False,
                    "action": action,
                    "simulated": True,
                    "message": str(exc),
                    "payment_outcome": "FAILURE",
                },
                "recovered_amount": 0,
                "errors": errors,
                "audit_events": audit_events,
            }

        except Exception as exc:

            logger.exception(
                "execute_action: unexpected execution error"
            )

            errors.append(
                f"execute_error: {exc}"
            )

            audit_events.append(
                _audit(
                    "AGENT_ERROR",
                    {
                        "error": (
                            "Unexpected action execution error"
                        ),
                    },
                )
            )

            return {
                "action_result": {
                    "success": False,
                    "action": action,
                    "simulated": False,
                    "message": (
                        "Action execution failed."
                    ),
                    "payment_outcome": "FAILURE",
                },
                "recovered_amount": 0,
                "errors": errors,
                "audit_events": audit_events,
            }

    return execute_action


# ──────────────────────────────────────────────────────────────────────────────
# Node 6: record_result
# ──────────────────────────────────────────────────────────────────────────────

def make_record_result_node(db: Session):

    def record_result(state: AgentState) -> dict:

        audit_events = list(
            state.get("audit_events", [])
        )

        errors = list(
            state.get("errors", [])
        )

        now = datetime.now(timezone.utc)

        final_decision = state.get(
            "final_decision",
            "STOP",
        )

        final_action = state.get(
            "final_action",
            "STOP",
        )

        action_result = (
            state.get("action_result")
            or {
                "success": False,
                "action": final_action,
                "simulated": True,
                "message": "No execution result.",
                "payment_outcome": "WAIT",
            }
        )

        # ── AgentAction ─────────────────────────────────────────────────────

        agent_action_id: int | None = None

        try:

            action_type = ActionType(
                final_action
            )

            action_status = (
                ActionStatus.EXECUTED
                if action_result.get("success")
                else ActionStatus.FAILED
            )

            agent_action = AgentAction(
                recovery_case_id=state[
                    "recovery_case_id"
                ],
                action_type=action_type,
                reason=(
                    state.get(
                        "decision_reason"
                    )
                    or state.get(
                        "policy_reason"
                    )
                ),
                status=action_status,
                executed_at=(
                    now
                    if action_result.get(
                        "success"
                    )
                    else None
                ),
                result=action_result,
                created_at=now,
            )

            db.add(agent_action)

            db.flush()

            agent_action_id = agent_action.id

            audit_events.append(
                _audit(
                    "ACTION_SELECTED",
                    {
                        "agent_action_id": agent_action_id,
                        "action_type": final_action,
                        "status": action_status.value,
                    },
                )
            )

        except Exception as exc:

            errors.append(
                f"record_agent_action: {exc}"
            )

            logger.error(
                "record_result: AgentAction error — %s",
                exc,
            )


        # ── Razorpay Payment Link persistence ─────────────────────────────
        #
        # In Razorpay Test Mode, RETRY_PAYMENT and SEND_PAYMENT_LINK
        # create a payment link. Creating the link does NOT mean that
        # the customer has paid.
        #
        # Store the Razorpay payment-link ID against the existing
        # Payment row so the webhook can later identify the payment
        # associated with this recovery case.

        if (
            not action_result.get("simulated", True)
            and final_action in {"RETRY_PAYMENT", "SEND_PAYMENT_LINK"}
        ):
            payment_link_id = action_result.get("payment_link_id")

            if payment_link_id:
                try:
                    payment_id = state.get("payment_id")

                    if payment_id:
                        payment = db.get(Payment, payment_id)

                        if payment:
                            payment.razorpay_payment_link_id = payment_link_id

                            audit_events.append(
                                _audit(
                                    "RAZORPAY_PAYMENT_LINK_ATTACHED",
                                    {
                                        "payment_id": payment.id,
                                        "payment_link_id": payment_link_id,
                                    },
                                )
                            )

                            logger.info(
                                "Stored Razorpay payment link ID=%s "
                                "on payment_id=%s",
                                payment_link_id,
                                payment.id,
                            )

                        else:
                            errors.append(
                                f"Payment {payment_id} not found while "
                                "storing Razorpay payment link."
                            )

                    else:
                        errors.append(
                            "No payment_id available while storing "
                            "Razorpay payment link."
                        )

                except Exception as exc:
                    errors.append(
                        f"razorpay_payment_link_persistence: {exc}"
                    )

                    logger.exception(
                        "Failed to store Razorpay payment link "
                        "for case_id=%s",
                        state["recovery_case_id"],
                    )


        # ── RecoveryCase status update ──────────────────────────────────────

        try:

            case = db.get(
                RecoveryCase,
                state["recovery_case_id"],
            )

            if case and case.status in (
                CaseStatus.OPEN,
                CaseStatus.IN_PROGRESS,
            ):

                # ── STOP ───────────────────────────────────────────────────

                if (
                    final_decision == "STOP"
                    or not state.get(
                        "policy_allowed"
                    )
                    or final_action == "STOP"
                ):

                    case.status = CaseStatus.STOPPED
                    case.resolved_at = now

                # ── RETRY_PAYMENT ─────────────────────────────────────────

                elif final_action == "RETRY_PAYMENT":

                    # Simulation mode:
                    #
                    # The simulator already knows whether the payment
                    # succeeded, so a successful simulated retry can
                    # immediately recover the case.

                    if (
                        action_result.get(
                            "simulated"
                        )
                        and action_result.get(
                            "payment_outcome"
                        ) == "SUCCESS"
                        and action_result.get(
                            "success"
                        )
                    ):

                        case.status = (
                            CaseStatus.RECOVERED
                        )

                        case.recovered_amount = (
                            state.get(
                                "recovered_amount",
                                0,
                            )
                        )

                        case.resolved_at = now

                    # Razorpay Test Mode:
                    #
                    # A payment link has only been created.
                    # The customer has NOT necessarily paid.
                    #
                    # Therefore remain IN_PROGRESS.
                    #
                    # The webhook will later change the case to
                    # RECOVERED after payment_link.paid/payment.captured.

                    elif (
                        not action_result.get(
                            "simulated"
                        )
                        and action_result.get(
                            "payment_outcome"
                        ) == "WAIT"
                    ):

                        case.status = (
                            CaseStatus.IN_PROGRESS
                        )

                    elif action_result.get(
                        "payment_outcome"
                    ) == "WAIT":

                        case.status = (
                            CaseStatus.IN_PROGRESS
                        )

                    else:

                        case.status = (
                            CaseStatus.NOT_RECOVERED
                        )

                        case.resolved_at = now

                # ── SEND_PAYMENT_LINK / SEND_REMINDER / WAIT ──────────────

                else:

                    # These actions do not themselves confirm payment.

                    case.status = (
                        CaseStatus.IN_PROGRESS
                    )

                case.updated_at = now

                db.flush()

            audit_events.append(
                _audit(
                    "CASE_UPDATED",
                    {
                        "new_status": (
                            case.status.value
                            if case
                            else "UNKNOWN"
                        ),
                    },
                )
            )

        except Exception as exc:

            errors.append(
                f"record_case_update: {exc}"
            )

            logger.error(
                "record_result: case update error — %s",
                exc,
            )

        # ── AuditLog rows ───────────────────────────────────────────────────

        action_related_events = {
            "ACTION_EXECUTED",
            "ACTION_SELECTED",
            "CASE_UPDATED",
            "AGENT_COMPLETED",
        }

        try:

            for evt in audit_events:

                db.add(
                    AuditLog(
                        recovery_case_id=state[
                            "recovery_case_id"
                        ],
                        agent_action_id=(
                            agent_action_id
                            if evt.get(
                                "event_type"
                            )
                            in action_related_events
                            else None
                        ),
                        event_type=evt[
                            "event_type"
                        ],
                        actor=evt.get(
                            "actor",
                            "AGENT",
                        ),
                        details=evt.get(
                            "details"
                        ),
                        created_at=datetime.fromisoformat(
                            evt["timestamp"]
                        ),
                    )
                )

            db.flush()

        except Exception as exc:

            errors.append(
                f"record_audit_log: {exc}"
            )

            logger.error(
                "record_result: AuditLog error — %s",
                exc,
            )

        # ── Completion marker ──────────────────────────────────────────────

        try:

            db.add(
                AuditLog(
                    recovery_case_id=state[
                        "recovery_case_id"
                    ],
                    agent_action_id=agent_action_id,
                    event_type="AGENT_COMPLETED",
                    actor="AGENT",
                    details={
                        "final_decision": final_decision,
                        "final_action": final_action,
                        "policy_overridden": state.get(
                            "policy_overridden",
                            False,
                        ),
                        "error_count": len(
                            errors
                        ),
                    },
                    created_at=now,
                )
            )

            db.flush()

        except Exception as exc:

            errors.append(
                f"record_completion: {exc}"
            )

        logger.info(
            "record_result: case %d — decision=%s action=%s agent_action=%s",
            state["recovery_case_id"],
            final_decision,
            final_action,
            agent_action_id,
        )

        return {
            "agent_action_id": agent_action_id,
            "errors": errors,
            "audit_events": audit_events,
            "completed": True,
        }

    return record_result


# ──────────────────────────────────────────────────────────────────────────────
# Edge routers
# ──────────────────────────────────────────────────────────────────────────────

def route_after_load(state: AgentState) -> str:

    return (
        END
        if state.get("completed")
        else "investigate_case"
    )


def route_after_policy(state: AgentState) -> str:

    if state.get("completed"):
        return "record_result"

    return (
        "execute_action"
        if state.get("policy_allowed")
        else "record_result"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Graph factory
# ──────────────────────────────────────────────────────────────────────────────

def build_recovery_graph(
    db: Session,
    gemini_service: GeminiService | None = None,
    executor=None,
) -> Any:
    """
    Build and compile the LangGraph recovery workflow.

    Parameters
    ----------
    db:
        Open SQLAlchemy session owned by the caller.

    gemini_service:
        Optional injectable GeminiService for testing.

    Returns
    -------
    Compiled LangGraph application ready to call .invoke().
    """

    graph = StateGraph(
        AgentState
    )

    graph.add_node(
        "load_case",
        make_load_case_node(db),
    )

    graph.add_node(
        "investigate_case",
        make_investigate_node(db),
    )

    graph.add_node(
        "analyze",
        make_analyze_node(
            gemini_service
        ),
    )

    graph.add_node(
        "policy_gate",
        make_policy_gate_node(),
    )

    graph.add_node(
        "execute_action",
        make_execute_action_node(executor),
    )

    graph.add_node(
        "record_result",
        make_record_result_node(db),
    )

    # ── Edges ───────────────────────────────────────────────────────────────

    graph.add_edge(
        START,
        "load_case",
    )

    graph.add_conditional_edges(
        "load_case",
        route_after_load,
        {
            "investigate_case": "investigate_case",
            END: END,
        },
    )

    graph.add_edge(
        "investigate_case",
        "analyze",
    )

    graph.add_edge(
        "analyze",
        "policy_gate",
    )

    graph.add_conditional_edges(
        "policy_gate",
        route_after_policy,
        {
            "execute_action": "execute_action",
            "record_result": "record_result",
        },
    )

    graph.add_edge(
        "execute_action",
        "record_result",
    )

    graph.add_edge(
        "record_result",
        END,
    )

    return graph.compile()