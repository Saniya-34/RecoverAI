"""Razorpay Test Mode service for RecoverAI."""

import logging
import os
from typing import Any

import razorpay

logger = logging.getLogger(__name__)


class RazorpayError(Exception):
    """Raised when a Razorpay operation fails."""


class RazorpayService:
    """Thin wrapper around the official Razorpay Python SDK."""

    def __init__(self) -> None:
        key_id = os.getenv("RAZORPAY_KEY_ID")
        key_secret = os.getenv("RAZORPAY_KEY_SECRET")

        if not key_id or not key_secret:
            raise RazorpayError(
                "Razorpay credentials are not configured. "
                "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET."
            )

        self.client = razorpay.Client(
            auth=(key_id, key_secret)
        )

        self.client.set_app_details(
            {
                "title": "RecoverAI",
                "version": "0.6.0",
            }
        )

        logger.info("Razorpay Test Mode service initialized.")

    def create_payment_link(
        self,
        amount: int,
        currency: str = "INR",
        notes: dict[str, Any] | None = None,
        description: str = "RecoverAI payment",
        case_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Create a Razorpay Payment Link.

        `amount` must be in the smallest currency unit.
        For INR, ₹1 = 100 paise.

        The RecoverAI case ID is stored in Razorpay notes so that
        webhook processing can identify the originating case.
        """

        if amount <= 0:
            raise RazorpayError("Payment amount must be greater than zero.")

        payment_notes = dict(notes or {})

        if case_id is not None:
            payment_notes.setdefault("recovery_case_id", str(case_id))

        reference_id = payment_notes.get("reference_id")

        if not reference_id:
            if case_id is not None:
                reference_id = f"recoverai_case_{case_id}"
            else:
                raise RazorpayError(
                    "reference_id is required when case_id is not provided."
                )

            payment_notes["reference_id"] = reference_id

        customer_name = payment_notes.pop("customer_name", None)
        customer_contact = payment_notes.pop("customer_contact", None)
        customer_email = payment_notes.pop("customer_email", None)

        payload: dict[str, Any] = {
            "amount": amount,
            "currency": currency,
            "accept_partial": False,
            "reference_id": str(reference_id),
            "description": description,
            "reminder_enable": True,
            "notes": payment_notes,
        }

        customer: dict[str, str] = {}

        if customer_name:
            customer["name"] = str(customer_name)

        if customer_contact:
            customer["contact"] = str(customer_contact)

        if customer_email:
            customer["email"] = str(customer_email)

        if customer:
            payload["customer"] = customer

        try:
            response = self.client.payment_link.create(payload)

            if not response.get("id") or not response.get("short_url"):
                raise RazorpayError(
                    "Razorpay returned an invalid payment-link response."
                )

            logger.info(
                "Razorpay payment link created: id=%s reference_id=%s",
                response.get("id"),
                reference_id,
            )

            return response

        except RazorpayError:
            raise

        except Exception as exc:
            logger.exception("Failed to create Razorpay payment link.")
            raise RazorpayError(
                f"Failed to create Razorpay payment link: {exc}"
            ) from exc

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        """Fetch a Razorpay payment by payment ID."""

        if not payment_id:
            raise RazorpayError("payment_id is required.")

        try:
            response = self.client.payment.fetch(payment_id)

            logger.info(
                "Fetched Razorpay payment: id=%s status=%s",
                payment_id,
                response.get("status"),
            )

            return response

        except Exception as exc:
            logger.exception(
                "Failed to fetch Razorpay payment: id=%s",
                payment_id,
            )
            raise RazorpayError(
                f"Failed to fetch Razorpay payment: {exc}"
            ) from exc

    def fetch_payment_link(
        self,
        payment_link_id: str,
    ) -> dict[str, Any]:
        """Fetch a Razorpay Payment Link by ID."""

        if not payment_link_id:
            raise RazorpayError("payment_link_id is required.")

        try:
            response = self.client.payment_link.fetch(payment_link_id)

            logger.info(
                "Fetched Razorpay payment link: id=%s status=%s",
                payment_link_id,
                response.get("status"),
            )

            return response

        except Exception as exc:
            logger.exception(
                "Failed to fetch Razorpay payment link: id=%s",
                payment_link_id,
            )
            raise RazorpayError(
                f"Failed to fetch Razorpay payment link: {exc}"
            ) from exc

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        """
        Verify a Razorpay webhook signature.

        The webhook secret is different from the Razorpay API secret.
        The raw request body must be used for verification.
        """

        webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")

        if not webhook_secret:
            raise RazorpayError(
                "RAZORPAY_WEBHOOK_SECRET is not configured."
            )

        if not payload:
            raise RazorpayError("Webhook payload cannot be empty.")

        if not signature:
            raise RazorpayError("Webhook signature is missing.")

        try:
            # Razorpay's Python SDK expects the webhook body as a string.
            raw_body = payload.decode("utf-8")

            self.client.utility.verify_webhook_signature(
                raw_body,
                signature,
                webhook_secret,
            )

            return True

        except Exception as exc:
            logger.warning(
                "Razorpay webhook signature verification failed."
            )
            raise RazorpayError(
                "Invalid Razorpay webhook signature."
            ) from exc