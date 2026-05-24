from beanie import Document, Indexed
from pydantic import Field
from typing import Annotated, Optional
from datetime import datetime, timezone
from enum import Enum
import pymongo


class SubscriptionPlatform(str, Enum):
    APPLE = "apple"
    GOOGLE = "google"
    STRIPE = "stripe"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PENDING = "pending"


class Subscription(Document):
    """Source of truth for premium entitlement. Driven by store webhooks."""
    user_id: Annotated[str, Indexed()]
    platform: SubscriptionPlatform
    product_id: str  # e.g. "com.flame.premium.monthly"
    original_transaction_id: Annotated[str, Indexed(unique=True)]
    status: SubscriptionStatus = SubscriptionStatus.PENDING

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    raw_receipt: Optional[str] = None  # encrypted/encoded receipt for re-validation
    last_verified_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "subscriptions"
        indexes = [
            "user_id",
            [("user_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)],
            "current_period_end",
        ]

    def is_active(self) -> bool:
        if self.status != SubscriptionStatus.ACTIVE:
            return False
        if not self.current_period_end:
            return False
        return self.current_period_end > datetime.now(timezone.utc)
