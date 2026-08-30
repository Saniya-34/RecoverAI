"""
Application configuration.

Loads environment variables from backend/.env once and provides
centralized configuration for the application.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


# Project root:
# RecoverAI/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load backend/.env
ENV_FILE = PROJECT_ROOT / "backend" / ".env"

load_dotenv(dotenv_path=ENV_FILE)


def get_env(name: str, default: str | None = None) -> str | None:
    """Read an environment variable after application configuration is loaded."""
    return os.getenv(name, default)


DATABASE_URL = get_env("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured. "
        "Set DATABASE_URL in backend/.env."
    )


USE_RAZORPAY_TEST_MODE = get_env(
    "USE_RAZORPAY_TEST_MODE",
    "false",
).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


RAZORPAY_KEY_ID = get_env("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = get_env("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = get_env("RAZORPAY_WEBHOOK_SECRET")