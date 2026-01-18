from beanie import Document, Indexed
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Annotated
from datetime import datetime, timezone
from enum import Enum


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    NON_BINARY = "non_binary"
    OTHER = "other"


class Photo(BaseModel):
    id: str
    url: str
    is_primary: bool = False
    order: int = 0


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class Location(BaseModel):
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    coordinates: Optional[Coordinates] = None


class UserPreferences(BaseModel):
    min_age: int = 18
    max_age: int = 50
    max_distance: int = 50  # in miles/km
    show_distance: bool = True
    show_online_status: bool = True


class NotificationSettings(BaseModel):
    new_matches: bool = True
    new_messages: bool = True
    super_likes: bool = True
    promotions: bool = False


class UserSettings(BaseModel):
    notifications_enabled: bool = True
    discovery_enabled: bool = True
    dark_mode: bool = False


class User(Document):
    email: Annotated[EmailStr, Indexed(unique=True)]
    password_hash: str
    name: str = Field(min_length=2, max_length=50)
    age: int = Field(ge=18, le=100)
    gender: Gender
    looking_for: Gender
    bio: Optional[str] = Field(default=None, max_length=500)
    interests: List[str] = Field(default_factory=list, min_length=1, max_length=10)
    photos: List[Photo] = Field(default_factory=list)
    location: Optional[Location] = None

    is_online: bool = False
    is_verified: bool = False
    last_active: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    preferences: UserPreferences = Field(default_factory=UserPreferences)
    notification_settings: NotificationSettings = Field(default_factory=NotificationSettings)
    settings: UserSettings = Field(default_factory=UserSettings)

    # Auth related
    verification_code: Optional[str] = None  # 6-digit code for email verification
    verification_code_expires: Optional[datetime] = None
    password_reset_token: Optional[str] = None  # Token for password reset links
    password_reset_token_expires: Optional[datetime] = None

    # Super like tracking
    super_likes_remaining: int = 3  # Daily super likes
    super_likes_reset_at: Optional[datetime] = None

    # Premium status
    is_premium: bool = False
    premium_expires_at: Optional[datetime] = None

    # Social auth
    google_id: Optional[str] = None
    apple_id: Optional[str] = None
    facebook_id: Optional[str] = None

    class Settings:
        name = "users"
        indexes = [
            "email",
            "google_id",
            "apple_id",
            "facebook_id",
            [
                ("location.coordinates.latitude", 1),
                ("location.coordinates.longitude", 1),
            ],
        ]

    def update_last_active(self):
        self.last_active = datetime.now(timezone.utc)
        self.is_online = True

    def get_primary_photo(self) -> Optional[str]:
        for photo in self.photos:
            if photo.is_primary:
                return photo.url
        return self.photos[0].url if self.photos else None
