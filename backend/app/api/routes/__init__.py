"""Routes package – sub-packages for each feature."""

from .agent import router as agent_router
from .audit import router as audit_router
from .dashboard import router as dashboard_router
from .events import router as events_router
from .health import router as health_router
from .recovery_cases import router as recovery_cases_router
from .razorpay_webhook import router as razorpay_webhook_router

__all__ = [
    "agent_router",
    "audit_router",
    "dashboard_router",
    "events_router",
    "health_router",
    "recovery_cases_router",
    "razorpay_webhook_router",
]