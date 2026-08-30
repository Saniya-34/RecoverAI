from datetime import datetime, timezone

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class RazorpayWebhookEvent(Base):
    """
    Stores processed Razorpay webhook event IDs.

    The event_id itself is the primary key so that the same
    Razorpay webhook event can never be processed twice.
    """

    __tablename__ = "razorpay_webhook_events"

    event_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
        nullable=False,
    )

    received_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )