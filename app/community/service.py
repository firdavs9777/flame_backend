from typing import List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from math import radians, cos, sin, asin, sqrt
from app.models.user import User, Photo, Location, Coordinates
from app.models.swipe import Swipe, SwipeType
from app.models.match import Match
from app.models.block import Block
from app.models.report import Report
from app.models.conversation import Conversation
from app.core.exceptions import NotFoundError, ValidationError, ForbiddenError
from app.core.security import verify_password


def haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate the distance between two points on Earth in miles."""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 3956  # Radius of Earth in miles
    return c * r


class UserService:
    @staticmethod
    async def get_user_by_id(user_id: str, requester: User) -> User:
        """Get a user by ID with privacy filtering."""
        user = await User.get(user_id)
        if not user:
            raise NotFoundError("User not found")

        # Check if blocked
        is_blocked = await Block.find_one({"$or": [
            {"blocker_id": str(requester.id), "blocked_id": user_id},
            {"blocker_id": user_id, "blocked_id": str(requester.id)}
        ]})
        if is_blocked:
            raise NotFoundError("User not found")

        return user

    @staticmethod
    async def update_profile(user: User, data: dict) -> User:
        """Update user profile."""
        for key, value in data.items():
            if value is not None and hasattr(user, key):
                setattr(user, key, value)

        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return user

    @staticmethod
    async def update_location(user: User, latitude: float, longitude: float) -> User:
        """Update user location with reverse geocoding."""
        from app.core.location import location_service

        # Reverse geocode to get city/state/country
        city, state, country = await location_service.reverse_geocode(latitude, longitude)

        user.location = Location(
            city=city,
            state=state,
            country=country,
            coordinates=Coordinates(latitude=latitude, longitude=longitude),
        )
        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return user

    @staticmethod
    async def update_preferences(user: User, data: dict) -> User:
        """Update user preferences."""
        for key, value in data.items():
            if value is not None and hasattr(user.preferences, key):
                setattr(user.preferences, key, value)

        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return user

    @staticmethod
    async def update_notification_settings(user: User, data: dict) -> User:
        """Update notification settings."""
        for key, value in data.items():
            if value is not None and hasattr(user.notification_settings, key):
                setattr(user.notification_settings, key, value)

        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return user

    @staticmethod
    async def add_photo(user: User, photo_url: str, is_primary: bool = False) -> Photo:
        """Add a photo to user profile."""
        if len(user.photos) >= 6:
            raise ValidationError("Maximum 6 photos allowed")

        photo_id = f"photo_{len(user.photos) + 1}_{int(datetime.now(timezone.utc).timestamp())}"
        order = len(user.photos)

        # If this is the first photo or marked as primary, update other photos
        if is_primary or len(user.photos) == 0:
            for p in user.photos:
                p.is_primary = False
            is_primary = True
            order = 0
            # Shift other photos
            for p in user.photos:
                p.order += 1

        photo = Photo(
            id=photo_id,
            url=photo_url,
            is_primary=is_primary,
            order=order,
        )
        user.photos.append(photo)
        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return photo

    @staticmethod
    async def delete_photo(user: User, photo_id: str):
        """Delete a photo from user profile."""
        if len(user.photos) <= 1:
            raise ValidationError("Must have at least one photo")

        photo_to_delete = None
        for p in user.photos:
            if p.id == photo_id:
                photo_to_delete = p
                break

        if not photo_to_delete:
            raise NotFoundError("Photo not found")

        user.photos.remove(photo_to_delete)

        # Reorder remaining photos
        for i, p in enumerate(user.photos):
            p.order = i
            if i == 0:
                p.is_primary = True

        user.updated_at = datetime.now(timezone.utc)
        await user.save()

    @staticmethod
    async def reorder_photos(user: User, photo_ids: List[str]) -> List[Photo]:
        """Reorder user photos."""
        if len(photo_ids) != len(user.photos):
            raise ValidationError("Must include all photo IDs")

        photo_map = {p.id: p for p in user.photos}

        for photo_id in photo_ids:
            if photo_id not in photo_map:
                raise ValidationError(f"Photo {photo_id} not found")

        # Reorder
        new_photos = []
        for i, photo_id in enumerate(photo_ids):
            photo = photo_map[photo_id]
            photo.order = i
            photo.is_primary = (i == 0)
            new_photos.append(photo)

        user.photos = new_photos
        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return user.photos

    @staticmethod
    async def delete_account(user: User, password: str, reason: Optional[str] = None):
        """Delete user account."""
        # Verify password (skip for social auth users)
        if user.password_hash and not verify_password(password, user.password_hash):
            raise ForbiddenError("Invalid password")

        # Delete related data
        await Swipe.find({"$or": [
            {"swiper_id": str(user.id)},
            {"swiped_id": str(user.id)}
        ]}).delete()

        await Match.find({"$or": [
            {"user1_id": str(user.id)},
            {"user2_id": str(user.id)}
        ]}).delete()

        await Conversation.find({"$or": [
            {"user1_id": str(user.id)},
            {"user2_id": str(user.id)}
        ]}).delete()

        await Block.find({"$or": [
            {"blocker_id": str(user.id)},
            {"blocked_id": str(user.id)}
        ]}).delete()

        # Delete user
        await user.delete()


class DiscoveryService:
    @staticmethod
    async def get_potential_matches(
        user: User,
        limit: int = 10,
        offset: int = 0,
    ) -> Tuple[List[User], int]:
        """Get potential matches for user based on preferences."""
        # Get users who we've already swiped on
        swiped = await Swipe.find(Swipe.swiper_id == str(user.id)).to_list()
        swiped_ids = [s.swiped_id for s in swiped]

        # Get blocked users (both directions)
        blocked = await Block.find({"$or": [
            {"blocker_id": str(user.id)},
            {"blocked_id": str(user.id)}
        ]}).to_list()
        blocked_ids = set()
        for b in blocked:
            blocked_ids.add(b.blocker_id)
            blocked_ids.add(b.blocked_id)
        blocked_ids.discard(str(user.id))

        # Exclude already swiped and blocked users
        exclude_ids = set(swiped_ids) | blocked_ids
        exclude_ids.add(str(user.id))

        # Get gender values (handle both enum and string)
        looking_for = user.looking_for.value if hasattr(user.looking_for, 'value') else user.looking_for
        gender = user.gender.value if hasattr(user.gender, 'value') else user.gender

        # Build query based on preferences
        query = {
            "gender": looking_for,
            "looking_for": gender,
            "age": {"$gte": user.preferences.min_age, "$lte": user.preferences.max_age},
            "settings.discovery_enabled": True,
        }

        # Get all potential matches
        potential_users = await User.find(query).to_list()

        # Filter out excluded users and calculate distance
        results = []
        for potential in potential_users:
            if str(potential.id) in exclude_ids:
                continue

            # Calculate distance if both have locations
            distance = None
            if (
                user.location
                and user.location.coordinates
                and potential.location
                and potential.location.coordinates
            ):
                distance = haversine(
                    user.location.coordinates.longitude,
                    user.location.coordinates.latitude,
                    potential.location.coordinates.longitude,
                    potential.location.coordinates.latitude,
                )

                # Filter by max distance preference
                if distance > user.preferences.max_distance:
                    continue

            # Calculate common interests
            common = list(set(user.interests) & set(potential.interests))

            results.append({
                "user": potential,
                "distance": distance,
                "common_interests": common,
            })

        total = len(results)
        paginated = results[offset : offset + limit]

        return paginated, total


class SwipeService:
    @staticmethod
    async def like(swiper: User, swiped_id: str) -> Tuple[bool, Optional[Match]]:
        """Like a user (swipe right)."""
        # Check if already swiped
        existing = await Swipe.find_one({
            "swiper_id": str(swiper.id),
            "swiped_id": swiped_id
        })
        if existing:
            raise ValidationError("Already swiped on this user")

        # Check if user exists
        swiped_user = await User.get(swiped_id)
        if not swiped_user:
            raise NotFoundError("User not found")

        # Create swipe
        swipe = Swipe(
            swiper_id=str(swiper.id),
            swiped_id=swiped_id,
            swipe_type=SwipeType.LIKE,
        )
        await swipe.insert()

        # Check for mutual like (match)
        mutual = await Swipe.find_one({
            "swiper_id": swiped_id,
            "swiped_id": str(swiper.id),
            "swipe_type": {"$in": ["like", "super_like"]}
        })

        if mutual:
            # Create match
            match = Match(
                user1_id=str(swiper.id),
                user2_id=swiped_id,
            )
            await match.insert()

            # Create conversation
            conversation = Conversation(
                match_id=str(match.id),
                user1_id=str(swiper.id),
                user2_id=swiped_id,
            )
            await conversation.insert()

            return True, match

        return False, None

    @staticmethod
    async def pass_user(swiper: User, swiped_id: str):
        """Pass on a user (swipe left)."""
        existing = await Swipe.find_one({
            "swiper_id": str(swiper.id),
            "swiped_id": swiped_id
        })
        if existing:
            raise ValidationError("Already swiped on this user")

        swipe = Swipe(
            swiper_id=str(swiper.id),
            swiped_id=swiped_id,
            swipe_type=SwipeType.PASS,
        )
        await swipe.insert()

    @staticmethod
    async def super_like(swiper: User, swiped_id: str) -> Tuple[bool, Optional[Match], int]:
        """Super like a user."""
        # Check and reset super likes if needed (daily reset)
        now = datetime.now(timezone.utc)
        if swiper.super_likes_reset_at is None or swiper.super_likes_reset_at < now:
            # Reset super likes for the new day
            swiper.super_likes_remaining = 3
            # Set reset time to midnight UTC tomorrow
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            swiper.super_likes_reset_at = tomorrow
            await swiper.save()

        # Check if user has super likes remaining
        if swiper.super_likes_remaining <= 0:
            raise ValidationError("No super likes remaining today")

        existing = await Swipe.find_one({
            "swiper_id": str(swiper.id),
            "swiped_id": swiped_id
        })
        if existing:
            raise ValidationError("Already swiped on this user")

        swiped_user = await User.get(swiped_id)
        if not swiped_user:
            raise NotFoundError("User not found")

        # Decrement super likes
        swiper.super_likes_remaining -= 1
        await swiper.save()

        swipe = Swipe(
            swiper_id=str(swiper.id),
            swiped_id=swiped_id,
            swipe_type=SwipeType.SUPER_LIKE,
        )
        await swipe.insert()

        # Check for match
        mutual = await Swipe.find_one({
            "swiper_id": swiped_id,
            "swiped_id": str(swiper.id),
            "swipe_type": {"$in": ["like", "super_like"]}
        })

        if mutual:
            match = Match(
                user1_id=str(swiper.id),
                user2_id=swiped_id,
            )
            await match.insert()

            conversation = Conversation(
                match_id=str(match.id),
                user1_id=str(swiper.id),
                user2_id=swiped_id,
            )
            await conversation.insert()

            return True, match, swiper.super_likes_remaining

        return False, None, swiper.super_likes_remaining

    @staticmethod
    async def undo_last_swipe(user: User) -> Optional[Swipe]:
        """Undo the last swipe. Requires premium subscription."""
        # Check if user has active premium subscription
        now = datetime.now(timezone.utc)
        if not user.is_premium:
            raise ForbiddenError("Undo feature requires premium subscription")

        if user.premium_expires_at and user.premium_expires_at < now:
            # Premium has expired, update status
            user.is_premium = False
            await user.save()
            raise ForbiddenError("Premium subscription has expired")

        # Get last swipe
        last_swipe = await Swipe.find(
            Swipe.swiper_id == str(user.id)
        ).sort(-Swipe.created_at).first_or_none()

        if not last_swipe:
            raise NotFoundError("No swipe to undo")

        # If the swipe resulted in a match, we need to undo that too
        if last_swipe.swipe_type in [SwipeType.LIKE, SwipeType.SUPER_LIKE]:
            match = await Match.find_one({"$or": [
                {"user1_id": str(user.id), "user2_id": last_swipe.swiped_id},
                {"user1_id": last_swipe.swiped_id, "user2_id": str(user.id)}
            ]})
            if match and match.is_active:
                match.is_active = False
                await match.save()
                # Also remove conversation
                conversation = await Conversation.find_one(
                    Conversation.match_id == str(match.id)
                )
                if conversation:
                    await conversation.delete()

        # Delete the swipe
        await last_swipe.delete()

        return last_swipe


class MatchService:
    @staticmethod
    async def get_matches(
        user: User,
        limit: int = 20,
        offset: int = 0,
        new_only: bool = False,
    ) -> Tuple[List[dict], int]:
        """Get user's matches."""
        query = {
            "$or": [
                {"user1_id": str(user.id)},
                {"user2_id": str(user.id)},
            ],
            "is_active": True,
        }

        matches = await Match.find(query).sort(-Match.matched_at).to_list()

        results = []
        for match in matches:
            other_user_id = match.get_other_user_id(str(user.id))
            other_user = await User.get(other_user_id)
            if not other_user:
                continue

            is_new = match.is_new_for_user(str(user.id))

            if new_only and not is_new:
                continue

            # Get last message from conversation
            conversation = await Conversation.find_one(
                Conversation.match_id == str(match.id)
            )
            last_message = None
            if conversation and conversation.last_message_content:
                last_message = {
                    "id": conversation.last_message_id,
                    "content": conversation.last_message_content,
                    "sender_id": conversation.last_message_sender_id,
                    "timestamp": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
                }

            results.append({
                "match": match,
                "other_user": other_user,
                "is_new": is_new,
                "last_message": last_message,
            })

        total = len(results)
        paginated = results[offset : offset + limit]

        return paginated, total

    @staticmethod
    async def unmatch(user: User, match_id: str):
        """Unmatch with a user."""
        match = await Match.get(match_id)
        if not match:
            raise NotFoundError("Match not found")

        if str(user.id) not in [match.user1_id, match.user2_id]:
            raise ForbiddenError("Not authorized")

        match.is_active = False
        await match.save()

        # Mark conversation as inactive too
        conversation = await Conversation.find_one(
            Conversation.match_id == match_id
        )
        if conversation:
            await conversation.delete()


class BlockService:
    @staticmethod
    async def block_user(blocker: User, blocked_id: str):
        """Block a user."""
        if str(blocker.id) == blocked_id:
            raise ValidationError("Cannot block yourself")

        blocked_user = await User.get(blocked_id)
        if not blocked_user:
            raise NotFoundError("User not found")

        existing = await Block.find_one({
            "blocker_id": str(blocker.id),
            "blocked_id": blocked_id
        })
        if existing:
            raise ValidationError("User already blocked")

        block = Block(
            blocker_id=str(blocker.id),
            blocked_id=blocked_id,
        )
        await block.insert()

        # Remove any existing match
        match = await Match.find_one({"$or": [
            {"user1_id": str(blocker.id), "user2_id": blocked_id, "is_active": True},
            {"user1_id": blocked_id, "user2_id": str(blocker.id), "is_active": True}
        ]})
        if match:
            match.is_active = False
            await match.save()

    @staticmethod
    async def unblock_user(blocker: User, blocked_id: str):
        """Unblock a user."""
        block = await Block.find_one({
            "blocker_id": str(blocker.id),
            "blocked_id": blocked_id
        })
        if not block:
            raise NotFoundError("User not blocked")

        await block.delete()

    @staticmethod
    async def get_blocked_users(user: User) -> List[dict]:
        """Get list of blocked users."""
        blocks = await Block.find(Block.blocker_id == str(user.id)).to_list()

        results = []
        for block in blocks:
            blocked_user = await User.get(block.blocked_id)
            if blocked_user:
                results.append({
                    "id": block.blocked_id,
                    "name": blocked_user.name,
                    "blocked_at": block.created_at.isoformat(),
                })

        return results


class ReportService:
    @staticmethod
    async def report_user(reporter: User, reported_id: str, reason: str, details: Optional[str] = None):
        """Report a user."""
        if str(reporter.id) == reported_id:
            raise ValidationError("Cannot report yourself")

        reported_user = await User.get(reported_id)
        if not reported_user:
            raise NotFoundError("User not found")

        report = Report(
            reporter_id=str(reporter.id),
            reported_id=reported_id,
            reason=reason,
            details=details,
        )
        await report.insert()
