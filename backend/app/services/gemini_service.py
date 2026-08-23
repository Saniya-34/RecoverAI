"""
backend/app/services/gemini_service.py

Clean Gemini client service using the google-genai SDK (v2.x).

This module is the ONLY place in the project that touches the Gemini API.
It is reusable by any future agent or feature that needs LLM reasoning.

SDK: google-genai==2.19.0
API: google.genai.Client — Developer API (api_key auth)

Design
──────
- GeminiService is a lightweight wrapper around google.genai.Client.
- It is instantiated once and reused (stateless per call).
- The API key is read from GEMINI_API_KEY env var — never hardcoded.
- The model name is read from AGENT_MODEL env var.
- Missing API key raises GeminiConfigError at instantiation time.
- Gemini API errors are caught and re-raised as GeminiCallError.
- Structured output is requested via response_schema + response_mime_type.
- The RecoveryDecision Pydantic schema enforces allowed decision/action values.
- No raw API key is ever logged or included in error messages.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import google.genai as genai
from google.genai import types as genai_types
from pydantic import ValidationError

from backend.app.schemas.recovery_agent import RecoveryDecision

logger = logging.getLogger(__name__)

# ── Defaults (overridden by env) ──────────────────────────────────────────────
_DEFAULT_MODEL = "gemini-3.7-flash"

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are RecoverAI, a revenue recovery decision engine for a payment platform.

Analyze the provided revenue recovery case data and return a structured JSON decision.

DECISION VALUES (choose exactly one):
- RECOVER  : A bounded recovery action should be attempted immediately.
- WAIT     : Recovery potential exists, but no immediate action should be taken.
- STOP     : Recovery should not be attempted.

ACTION VALUES (must be consistent with decision):
- If decision=RECOVER: action must be one of RETRY_PAYMENT, SEND_PAYMENT_LINK, SEND_REMINDER
- If decision=WAIT:    action must be WAIT
- If decision=STOP:    action must be STOP

ACTION SELECTION GUIDANCE:
- RETRY_PAYMENT       : Use for temporary technical failures (bank_timeout, network_error,
                        temporary_bank_error) with good customer history (≥3 prior successes).
- SEND_PAYMENT_LINK   : Use for checkout abandonment, card failures, or when the customer
                        may need a different payment method.
- SEND_REMINDER       : Use for recent abandonment (within 24h) with no prior recovery attempt.
- WAIT                : Use when situation is ambiguous or customer was recently contacted.
- STOP                : Use when order is already paid, cancelled, repeatedly failed (≥3 times
                        with no success), or customer has a poor payment history.

EVIDENCE REQUIREMENT:
- The `evidence` list MUST contain specific facts from the data provided.
- Do NOT fabricate facts. Use only what is explicitly present in the case data.
- Example evidence items: "8 previous successful payments", "failure_reason: temporary_bank_error",
  "0 prior recovery attempts", "customer success_rate: 0.89".

Respond ONLY with valid JSON matching the required schema. Do not include explanatory text.
"""


# ── Custom exceptions ─────────────────────────────────────────────────────────

class GeminiConfigError(Exception):
    """Raised when Gemini cannot be configured (missing API key, etc.)."""


class GeminiCallError(Exception):
    """Raised when a Gemini API call fails."""


class GeminiParseError(Exception):
    """Raised when the Gemini response cannot be parsed into RecoveryDecision."""


# ── Service ───────────────────────────────────────────────────────────────────

class GeminiService:
    """
    Thin, reusable wrapper around google.genai.Client.

    Instantiate once per application lifetime (or per request — it's stateless).
    The API key is validated at construction time so failures surface early.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """
        Parameters
        ----------
        api_key : Override the GEMINI_API_KEY env var (useful for testing).
        model   : Override the AGENT_MODEL env var.
        """
        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        if not resolved_key:
            raise GeminiConfigError(
                "GEMINI_API_KEY is not set. "
                "Add it to backend/.env — see .env.example for the variable name."
            )

        self._model: str = model or os.getenv("AGENT_MODEL", _DEFAULT_MODEL)
        # Never log the key — log only the first 4 chars as a visibility marker
        logger.info(
            "GeminiService: initialised model=%s key_prefix=%s***",
            self._model,
            resolved_key[:4],
        )

        try:
            self._client = genai.Client(api_key=resolved_key)
        except Exception as exc:
            raise GeminiConfigError(f"Failed to create Gemini client: {exc}") from exc

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def model(self) -> str:
        return self._model

    def request_recovery_decision(
        self, case_context: dict[str, Any]
    ) -> RecoveryDecision:
        """
        Ask Gemini to analyze a recovery case and return a structured decision.

        Parameters
        ----------
        case_context : Aggregated dict from RecoveryTools.get_case_context().
                       Must contain case, customer, payment_history, order_history,
                       and previous_recovery_attempts keys.

        Returns
        -------
        RecoveryDecision — validated Pydantic model.

        Raises
        ------
        GeminiCallError  — Gemini API returned an error.
        GeminiParseError — Response could not be parsed into RecoveryDecision.
        """
        prompt = (
            "Analyze the following revenue recovery case and return a JSON decision:\n\n"
            + json.dumps(case_context, indent=2, default=str)
        )

        logger.debug(
            "GeminiService: sending request to %s (context keys=%s)",
            self._model,
            list(case_context.keys()),
        )

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=RecoveryDecision,
                    temperature=0.1,   # low temperature for deterministic decisions
                    max_output_tokens=512,
                ),
            )
        except Exception as exc:
            # Never surface the raw exception message in case it contains credentials
            safe_msg = _safe_error_message(exc)
            logger.error("GeminiService: API call failed — %s", safe_msg)
            raise GeminiCallError(f"Gemini API call failed: {safe_msg}") from exc

        return self._parse_response(response)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _parse_response(self, response: Any) -> RecoveryDecision:
        """
        Extract and validate the RecoveryDecision from a Gemini response.

        google-genai 2.x with response_schema set and response_mime_type=application/json
        returns the parsed object in response.candidates[0].content.parts[0].text
        as a JSON string. We parse + validate it with Pydantic.
        """
        raw_text: str = ""
        try:
            raw_text = response.text.strip()
            logger.debug("GeminiService: raw response text: %s", raw_text[:200])
        except Exception as exc:
            raise GeminiParseError(
                f"Failed to extract text from Gemini response: {exc}"
            ) from exc

        # Strip markdown code fences if the model wrapped the JSON
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            raw_text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise GeminiParseError(
                f"Gemini response is not valid JSON. "
                f"First 200 chars: {raw_text[:200]!r}"
            ) from exc

        try:
            decision = RecoveryDecision(**data)
        except (ValidationError, TypeError) as exc:
            raise GeminiParseError(
                f"Gemini response failed RecoveryDecision validation: {exc}. "
                f"Data: {data}"
            ) from exc

        logger.info(
            "GeminiService: decision=%s action=%s confidence=%.2f",
            decision.decision,
            decision.action,
            decision.confidence,
        )
        return decision


# ── Utility ───────────────────────────────────────────────────────────────────

def _safe_error_message(exc: Exception) -> str:
    """
    Return a safe string representation of an exception.
    Strips anything that looks like an API key or credential.
    """
    msg = str(exc)
    # Truncate very long messages (may contain response bodies with credentials)
    return msg[:300] if len(msg) > 300 else msg


# ── Module-level factory ──────────────────────────────────────────────────────

def create_gemini_service(
    api_key: str | None = None,
    model: str | None = None,
) -> GeminiService:
    """
    Factory function — creates a GeminiService from env config.

    Raises GeminiConfigError if GEMINI_API_KEY is missing.
    """
    return GeminiService(api_key=api_key, model=model)
