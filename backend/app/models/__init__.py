"""
backend/app/models/__init__.py

Central import point for all SQLAlchemy ORM models.

Importing this package (or any path that triggers this __init__.py)
is sufficient to register every model class with Base.metadata — which
is what Alembic's env.py and the app factory both need.

Import order follows FK dependency:
    Customer → Order → Payment / CheckoutEvent
    → RecoveryCase → AgentAction → AuditLog
"""

# 1. No FK dependencies
from backend.app.models.customer import Customer  # noqa: F401

# 2. Depends on Customer
from backend.app.models.order import Order  # noqa: F401

# 3. Depends on Customer + Order
from backend.app.models.payment import Payment  # noqa: F401
from backend.app.models.checkout_event import (  # noqa: F401
    CheckoutEvent,
    CheckoutEventType,
)

# 4. Depends on Customer + Order + Payment
from backend.app.models.recovery_case import (  # noqa: F401
    RecoveryCase,
    CaseType,
    CaseStatus,
)

# 5. Depends on RecoveryCase
from backend.app.models.agent_action import (  # noqa: F401
    AgentAction,
    ActionType,
    ActionStatus,
)

# 6. Depends on RecoveryCase + AgentAction
from backend.app.models.audit_log import AuditLog  # noqa: F401

# 7. Razorpay webhook events
from backend.app.models.razorpay_webhook_event import RazorpayWebhookEvent  # noqa: F401

__all__ = [
    # ORM models
    "Customer",
    "Order",
    "Payment",
    "CheckoutEvent",
    "RecoveryCase",
    "AgentAction",
    "AuditLog",
    "RazorpayWebhookEvent",
    # Enums
    "CheckoutEventType",
    "CaseType",
    "CaseStatus",
    "ActionType",
    "ActionStatus",
]
