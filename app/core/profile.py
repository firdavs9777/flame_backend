"""Shared profile-completeness check used by auth and community routes."""
from app.models.user import User


def is_profile_complete(user: User) -> bool:
    """A profile is complete when the user has at least one photo,
    at least one non-empty interest, and a location with coordinates."""
    has_photos = len(user.photos) > 0
    has_interests = any((i or "").strip() for i in (user.interests or []))
    has_location = user.location is not None and user.location.coordinates is not None
    return has_photos and has_interests and has_location
