from beanie import Document, Indexed
from pydantic import Field
from typing import Optional, Annotated
from datetime import datetime, timezone
from enum import Enum


class ReportReason(str, Enum):
    INAPPROPRIATE_CONTENT = "inappropriate_content"
    FAKE_PROFILE = "fake_profile"
    HARASSMENT = "harassment"
    SPAM = "spam"
    UNDERAGE = "underage"
    OTHER = "other"


class ReportStatus(str, Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class Report(Document):
    reporter_id: Annotated[str, Indexed()]
    reported_id: Annotated[str, Indexed()]
    reason: ReportReason
    details: Optional[str] = None
    status: ReportStatus = ReportStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None

    class Settings:
        name = "reports"
        indexes = [
            "reporter_id",
            "reported_id",
            "status",
        ]
