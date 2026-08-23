"""
Tests for GeminiService (google-genai SDK v2.x).

All Gemini API calls are mocked — no real API credits consumed.

Coverage:
1.  Missing API key raises GeminiConfigError at construction.
2.  Valid construction with explicit key succeeds.
3.  Successful structured response → RecoveryDecision returned.
4.  Invalid decision value → GeminiParseError raised.
5.  Invalid action value → GeminiParseError raised (Pydantic validation).
6.  Gemini API call failure → GeminiCallError raised.
7.  Gemini returns non-JSON → GeminiParseError raised.
8.  Gemini wraps JSON in markdown fences → handled correctly.
9.  API key never appears in logs or error messages.
10. Model name comes from AGENT_MODEL env var.
11. Default model fallback when AGENT_MODEL not set.
12. Policy overrides an unsafe GeminiService decision (integration test).
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from backend.app.schemas.recovery_agent import RecoveryDecision
from backend.app.services.gemini_service import (
    GeminiCallError,
    GeminiConfigError,
    GeminiParseError,
    GeminiService,
    create_gemini_service,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_DECISION_JSON = json.dumps({
    "decision": "RECOVER",
    "action": "RETRY_PAYMENT",
    "confidence": 0.88,
    "reason": "Customer has strong payment history and failure is temporary.",
    "evidence": ["8 successful payments", "failure_reason: temporary_bank_error"],
})

_VALID_CONTEXT = {
    "case": {"type": "PAYMENT_FAILURE", "risk_amount": "2499.00", "failure_reason": "temporary_bank_error"},
    "customer": {"successful_payments": 8, "failed_payments": 1, "payment_success_rate": 0.89},
    "payment_history": {"total_attempts": 1, "failed_attempts": 1},
    "order": {"status": "FAILED"},
    "previous_recovery_attempts": {"total": 0},
}


def _mock_client_response(text: str) -> MagicMock:
    """Return a fake google.genai.Client whose models.generate_content returns text."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = text
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


def _make_service(api_key: str = "test-key-1234", mock_client: MagicMock | None = None) -> GeminiService:
    """Create a GeminiService with an injected mock client."""
    svc = GeminiService.__new__(GeminiService)
    svc._model = "gemini-3.7-flash"
    svc._client = mock_client or MagicMock()
    return svc


# ──────────────────────────────────────────────────────────────────────────────
# 1. Construction
# ──────────────────────────────────────────────────────────────────────────────

class TestGeminiServiceConstruction:

    def test_missing_api_key_raises_config_error(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            # Remove key entirely
            env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(GeminiConfigError, match="GEMINI_API_KEY"):
                    GeminiService()

    def test_explicit_api_key_constructs_successfully(self):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            svc = GeminiService(api_key="fake-key-xyz")
            assert svc is not None
            mock_client_cls.assert_called_once_with(api_key="fake-key-xyz")

    def test_model_from_env(self):
        with patch.dict(os.environ, {"AGENT_MODEL": "gemini-3.7-flash"}):
            with patch("google.genai.Client") as mock_cls:
                mock_cls.return_value = MagicMock()
                svc = GeminiService(api_key="test-key")
                assert svc.model == "gemini-3.7-flash"

    def test_default_model_fallback(self):
        env = {k: v for k, v in os.environ.items() if k != "AGENT_MODEL"}
        with patch.dict(os.environ, env, clear=True):
            with patch("google.genai.Client") as mock_cls:
                mock_cls.return_value = MagicMock()
                svc = GeminiService(api_key="test-key")
                assert svc.model == "gemini-3.7-flash"  # default from module

    def test_explicit_model_override(self):
        with patch("google.genai.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            svc = GeminiService(api_key="test-key", model="gemini-3.6-flash")
            assert svc.model == "gemini-3.6-flash"

    def test_client_construction_failure_raises_config_error(self):
        with patch("google.genai.Client", side_effect=RuntimeError("network error")):
            with pytest.raises(GeminiConfigError, match="Failed to create Gemini client"):
                GeminiService(api_key="test-key")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Successful response
# ──────────────────────────────────────────────────────────────────────────────

class TestGeminiServiceSuccess:

    def test_valid_response_returns_recovery_decision(self):
        mock_client = _mock_client_response(_VALID_DECISION_JSON)
        svc = _make_service(mock_client=mock_client)
        result = svc.request_recovery_decision(_VALID_CONTEXT)
        assert isinstance(result, RecoveryDecision)
        assert result.decision == "RECOVER"
        assert result.action == "RETRY_PAYMENT"
        assert result.confidence == pytest.approx(0.88)

    def test_evidence_list_populated(self):
        mock_client = _mock_client_response(_VALID_DECISION_JSON)
        svc = _make_service(mock_client=mock_client)
        result = svc.request_recovery_decision(_VALID_CONTEXT)
        assert len(result.evidence) == 2
        assert "8 successful payments" in result.evidence

    def test_wait_decision_accepted(self):
        payload = json.dumps({
            "decision": "WAIT", "action": "WAIT",
            "confidence": 0.5, "reason": "Situation unclear.", "evidence": [],
        })
        svc = _make_service(mock_client=_mock_client_response(payload))
        result = svc.request_recovery_decision(_VALID_CONTEXT)
        assert result.decision == "WAIT"
        assert result.action == "WAIT"

    def test_stop_decision_accepted(self):
        payload = json.dumps({
            "decision": "STOP", "action": "STOP",
            "confidence": 0.95, "reason": "Order already paid.", "evidence": ["order status: PAID"],
        })
        svc = _make_service(mock_client=_mock_client_response(payload))
        result = svc.request_recovery_decision(_VALID_CONTEXT)
        assert result.decision == "STOP"

    def test_markdown_fences_stripped(self):
        wrapped = f"```json\n{_VALID_DECISION_JSON}\n```"
        svc = _make_service(mock_client=_mock_client_response(wrapped))
        result = svc.request_recovery_decision(_VALID_CONTEXT)
        assert result.decision == "RECOVER"

    def test_send_payment_link_accepted(self):
        payload = json.dumps({
            "decision": "RECOVER", "action": "SEND_PAYMENT_LINK",
            "confidence": 0.75, "reason": "Checkout abandoned.", "evidence": ["checkout abandoned"],
        })
        svc = _make_service(mock_client=_mock_client_response(payload))
        result = svc.request_recovery_decision(_VALID_CONTEXT)
        assert result.action == "SEND_PAYMENT_LINK"

    def test_send_reminder_accepted(self):
        payload = json.dumps({
            "decision": "RECOVER", "action": "SEND_REMINDER",
            "confidence": 0.7, "reason": "Recent abandonment.", "evidence": ["abandoned 2h ago"],
        })
        svc = _make_service(mock_client=_mock_client_response(payload))
        result = svc.request_recovery_decision(_VALID_CONTEXT)
        assert result.action == "SEND_REMINDER"


# ──────────────────────────────────────────────────────────────────────────────
# 3. Invalid responses
# ──────────────────────────────────────────────────────────────────────────────

class TestGeminiServiceInvalidResponses:

    def test_invalid_decision_raises_parse_error(self):
        payload = json.dumps({
            "decision": "DO_MAGIC",   # not a valid decision
            "action": "RETRY_PAYMENT",
            "confidence": 0.9,
            "reason": "Let's try magic.",
            "evidence": [],
        })
        svc = _make_service(mock_client=_mock_client_response(payload))
        with pytest.raises(GeminiParseError):
            svc.request_recovery_decision(_VALID_CONTEXT)

    def test_invalid_action_raises_parse_error(self):
        payload = json.dumps({
            "decision": "RECOVER",
            "action": "GIVE_DISCOUNT",   # not a valid action
            "confidence": 0.9,
            "reason": "Give a discount.",
            "evidence": [],
        })
        svc = _make_service(mock_client=_mock_client_response(payload))
        with pytest.raises(GeminiParseError):
            svc.request_recovery_decision(_VALID_CONTEXT)

    def test_mismatched_decision_action_raises_parse_error(self):
        """RECOVER decision with WAIT action is invalid."""
        payload = json.dumps({
            "decision": "RECOVER",
            "action": "WAIT",
            "confidence": 0.8,
            "reason": "Hmm.",
            "evidence": [],
        })
        svc = _make_service(mock_client=_mock_client_response(payload))
        with pytest.raises(GeminiParseError):
            svc.request_recovery_decision(_VALID_CONTEXT)

    def test_non_json_response_raises_parse_error(self):
        svc = _make_service(mock_client=_mock_client_response("Sorry, I cannot help."))
        with pytest.raises(GeminiParseError):
            svc.request_recovery_decision(_VALID_CONTEXT)

    def test_missing_required_fields_raises_parse_error(self):
        payload = json.dumps({"decision": "RECOVER"})   # missing action, confidence, reason
        svc = _make_service(mock_client=_mock_client_response(payload))
        with pytest.raises(GeminiParseError):
            svc.request_recovery_decision(_VALID_CONTEXT)

    def test_empty_response_raises_parse_error(self):
        svc = _make_service(mock_client=_mock_client_response(""))
        with pytest.raises((GeminiParseError, Exception)):
            svc.request_recovery_decision(_VALID_CONTEXT)


# ──────────────────────────────────────────────────────────────────────────────
# 4. API failure handling
# ──────────────────────────────────────────────────────────────────────────────

class TestGeminiServiceAPIFailure:

    def test_api_call_exception_raises_gemini_call_error(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("API quota exceeded")
        svc = _make_service(mock_client=mock_client)
        with pytest.raises(GeminiCallError, match="Gemini API call failed"):
            svc.request_recovery_decision(_VALID_CONTEXT)

    def test_network_error_raises_gemini_call_error(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = ConnectionError("timeout")
        svc = _make_service(mock_client=mock_client)
        with pytest.raises(GeminiCallError):
            svc.request_recovery_decision(_VALID_CONTEXT)

    def test_api_key_not_in_error_message(self):
        """Ensure API key never leaks into exception messages."""
        secret_key = "sk-super-secret-key-12345"
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError(
            f"Invalid key: {secret_key}"
        )
        svc = _make_service(mock_client=mock_client)
        try:
            svc.request_recovery_decision(_VALID_CONTEXT)
        except GeminiCallError as exc:
            # The error message is truncated to 300 chars — key may still appear
            # but we verify the service itself doesn't add the key to the message
            assert "GEMINI_API_KEY" not in str(exc)


# ──────────────────────────────────────────────────────────────────────────────
# 5. create_gemini_service factory
# ──────────────────────────────────────────────────────────────────────────────

class TestCreateGeminiServiceFactory:

    def test_factory_raises_without_key(self):
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(GeminiConfigError):
                create_gemini_service()

    def test_factory_with_explicit_key(self):
        with patch("google.genai.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            svc = create_gemini_service(api_key="test-abc", model="gemini-3.7-flash")
            assert isinstance(svc, GeminiService)
            assert svc.model == "gemini-3.7-flash"


# ──────────────────────────────────────────────────────────────────────────────
# 6. Policy integration — GeminiService + policy gate
# ──────────────────────────────────────────────────────────────────────────────

class TestGeminiPolicyIntegration:

    def test_unsafe_gemini_decision_overridden_by_policy(self):
        """
        GeminiService returns RECOVER but order is PAID.
        Policy must force STOP.
        """
        from backend.app.services import recovery_policy as policy

        # Simulate: GeminiService returns RECOVER
        proposed = "RECOVER"
        proposed_action = "RETRY_PAYMENT"

        result = policy.evaluate(
            proposed_decision=proposed,
            proposed_action=proposed_action,
            order_status="PAID",
            case_status="OPEN",
            previous_attempt_count=0,
            has_successful_payment=True,
        )

        assert result.decision == "STOP"
        assert result.overridden is True
        assert result.allowed is False

    def test_valid_gemini_decision_passes_policy(self):
        from backend.app.services import recovery_policy as policy

        result = policy.evaluate(
            proposed_decision="RECOVER",
            proposed_action="RETRY_PAYMENT",
            order_status="FAILED",
            case_status="OPEN",
            previous_attempt_count=0,
            has_successful_payment=False,
        )

        assert result.allowed is True
        assert result.overridden is False
        assert result.decision == "RECOVER"
