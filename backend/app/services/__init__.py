"""
backend/app/services/__init__.py

Service package entry point.

Selects the appropriate action executor based on application configuration.

By default, RecoverAI uses the simulated executor.

When USE_RAZORPAY_TEST_MODE is enabled:
    - RETRY_PAYMENT uses Razorpay Test Mode.
    - SEND_PAYMENT_LINK uses Razorpay Test Mode.
    - SEND_REMINDER, WAIT and STOP remain simulated.
"""

import logging

from backend.app.config import USE_RAZORPAY_TEST_MODE
from .action_executor import SimulatedActionExecutor

logger = logging.getLogger(__name__)


if USE_RAZORPAY_TEST_MODE:
    from .razorpay_executor import RazorpayTestModeExecutor

    executor = RazorpayTestModeExecutor()

    logger.info(
        "Razorpay Test Mode ENABLED - using RazorpayTestModeExecutor"
    )

else:
    executor = SimulatedActionExecutor()

    logger.info(
        "Razorpay Test Mode DISABLED - using SimulatedActionExecutor"
    )