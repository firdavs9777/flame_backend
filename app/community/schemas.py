from pydantic import BaseModel, Field
from typing import Optional, List
from app.models.user import Gender
from app.models.report import ReportReason


# User Profile Schemas
class PhotoResponse(BaseModel):
    id: str
    url: str
    is_primary: bool
    order: int


class LocationResponse(BaseModel):
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    coordinates: Optional[dict] = None


class PreferencesResponse(BaseModel):
    min_age: int
    max_age: int
    max_distance: int
    show_distance: bool
    show_online_status: bool


class NotificationSettingsResponse(BaseModel):
    new_matches: bool
    new_messages: bool
    super_likes: bool
    promotions: bool


class SettingsResponse(BaseModel):
    notifications_enabled: bool
    discovery_enabled: bool
    dark_mode: bool


class FullUserResponse(BaseModel):
    id: str
    email: str
    name: str
    age: int
    gender: str
    looking_for: str
    bio: Optional[str] = None
    interests: List[str]
    photos: List[PhotoResponse]
    location: Optional[LocationResponse] = None
    is_online: bool
    is_verified: bool
    last_active: str
    created_at: str
    preferences: PreferencesResponse
    settings: SettingsResponse


class PublicUserResponse(BaseModel):
    id: str
    name: str
    age: int
    gender: str
    bio: Optional[str] = None
    interests: List[str]
    photos: List[str]
    location: Optional[str] = None
    distance: Optional[float] = None
    is_online: bool
    last_active: str
    common_interests: Optional[List[str]] = None


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=50)
    bio: Optional[str] = Field(default=None, max_length=500)
    interests: Optional[List[str]] = Field(default=None, min_length=1, max_length=10)
    looking_for: Optional[Gender] = None


class UpdateLocationRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class UpdatePreferencesRequest(BaseModel):
    min_age: Optional[int] = Field(default=None, ge=18, le=100)
    max_age: Optional[int] = Field(default=None, ge=18, le=100)
    max_distance: Optional[int] = Field(default=None, ge=1, le=500)
    show_distance: Optional[bool] = None
    show_online_status: Optional[bool] = None


class UpdateNotificationsRequest(BaseModel):
    new_matches: Optional[bool] = None
    new_messages: Optional[bool] = None
    super_likes: Optional[bool] = None
    promotions: Optional[bool] = None


class ReorderPhotosRequest(BaseModel):
    photo_ids: List[str]


class DeleteAccountRequest(BaseModel):
    password: str
    reason: Optional[str] = None


# Discovery Schemas
class DiscoverResponse(BaseModel):
    users: List[PublicUserResponse]
    pagination: dict


# Swipe Schemas
class SwipeRequest(BaseModel):
    user_id: str


class SwipeResponse(BaseModel):
    liked: Optional[bool] = None
    passed: Optional[bool] = None
    super_liked: Optional[bool] = None
    is_match: bool = False
    match: Optional[dict] = None
    remaining_super_likes: Optional[int] = None


class UndoResponse(BaseModel):
    undone: bool
    user: dict


# Match Schemas
class MatchUserResponse(BaseModel):
    id: str
    name: str
    age: int
    photos: List[str]
    is_online: bool
    last_active: str


class MatchResponse(BaseModel):
    id: str
    user: MatchUserResponse
    matched_at: str
    is_new: bool
    last_message: Optional[dict] = None


class MatchListResponse(BaseModel):
    matches: List[MatchResponse]
    pagination: dict


# Reporting & Blocking Schemas
class ReportRequest(BaseModel):
    user_id: str
    reason: ReportReason
    details: Optional[str] = None


class BlockRequest(BaseModel):
    user_id: str


class BlockedUserResponse(BaseModel):
    id: str
    name: str
    blocked_at: str


# Device Schemas
class RegisterDeviceRequest(BaseModel):
    token: str
    platform: str = "ios"
