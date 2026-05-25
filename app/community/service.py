from typing import List, Optional, Tuple
from datetime import datetime, timezone
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from app.models.user import User, Photo, Location, Coordinates, GeoPoint
from app.models.swipe import Swipe, SwipeType
from app.models.match import Match
from app.models.block import Block
from app.models.report import Report
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.refresh_token import RefreshToken
from app.models.device import Device
from app.models.subscription import Subscription, SubscriptionStatus
from app.core.exceptions import NotFoundError, ValidationError, ForbiddenError
from app.core.security import verify_password
from app.core.database import get_database

MILES_PER_METER = 0.000621371


class UserService:
    @staticmethod
    async def get_user_by_id(user_id: str, requester: User) -> User:
        """Get a user by ID with privacy filtering."""
        try:
            user = await User.get(user_id)
        except Exception:
            raise NotFoundError("User not found")
        if not user or user.is_deleted:
            raise NotFoundError("User not found")

        is_blocked = await Block.find_one({"$or": [
            {"blocker_id": str(requester.id), "blocked_id": user_id},
            {"blocker_id": user_id, "blocked_id": str(requester.id)}
        ]})
        if is_blocked:
            raise NotFoundError("User not found")

        return user

    @staticmethod
    async def update_profile(user: User, data: dict) -> User:
        """Update user profile — schema-bounded fields only."""
        allowed = {"name", "age", "gender", "bio", "interests", "looking_for"}
        for key, value in data.items():
            if key in allowed and value is not None:
                setattr(user, key, value)

        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return user

    @staticmethod
    async def update_location(user: User, latitude: float, longitude: float) -> User:
        """Update user location. Reverse geocoding happens in background."""
        # Set coordinates immediately so discovery works without waiting on Nominatim
        user.location = Location(
            city=user.location.city if user.location else None,
            state=user.location.state if user.location else None,
            country=user.location.country if user.location else None,
            coordinates=Coordinates(latitude=latitude, longitude=longitude),
        )
        # GeoJSON shape — [lng, lat] order for 2dsphere
        user.location_geo = GeoPoint(coordinates=[longitude, latitude])
        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return user

    @staticmethod
    async def update_preferences(user: User, data: dict) -> User:
        allowed = {"min_age", "max_age", "max_distance", "show_distance", "show_online_status"}
        for key, value in data.items():
            if key in allowed and value is not None and hasattr(user.preferences, key):
                setattr(user.preferences, key, value)

        if user.preferences.min_age > user.preferences.max_age:
            raise ValidationError("min_age cannot exceed max_age")

        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return user

    @staticmethod
    async def update_notification_settings(user: User, data: dict) -> User:
        allowed = {"new_matches", "new_messages", "super_likes", "promotions"}
        for key, value in data.items():
            if key in allowed and value is not None and hasattr(user.notification_settings, key):
                setattr(user.notification_settings, key, value)

        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return user

    @staticmethod
    async def add_photo(user: User, photo_url: str, is_primary: bool = False) -> Photo:
        if len(user.photos) >= 6:
            raise ValidationError("Maximum 6 photos allowed")

        photo_id = f"photo_{len(user.photos) + 1}_{int(datetime.now(timezone.utc).timestamp())}"
        order = len(user.photos)

        if is_primary or len(user.photos) == 0:
            for p in user.photos:
                p.is_primary = False
            is_primary = True
            order = 0
            for p in user.photos:
                p.order += 1

        photo = Photo(id=photo_id, url=photo_url, is_primary=is_primary, order=order)
        user.photos.append(photo)
        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        return photo

    @staticmethod
    async def delete_photo(user: User, photo_id: str):
        if len(user.photos) <= 1:
            raise ValidationError("Must have at least one photo")

        photo_to_delete = next((p for p in user.photos if p.id == photo_id), None)
        if not photo_to_delete:
            raise NotFoundError("Photo not found")

        # Delete underlying storage object
        from app.core.storage import storage
        try:
            await storage.delete_file(photo_to_delete.url)
        except Exception:
            pass  # best-effort; user wants the photo gone from the profile

        user.photos.remove(photo_to_delete)
        for i, p in enumerate(user.photos):
            p.order = i
            p.is_primary = (i == 0)

        user.updated_at = datetime.now(timezone.utc)
        await user.save()

    @staticmethod
    async def reorder_photos(user: User, photo_ids: List[str]) -> List[Photo]:
        if len(photo_ids) != len(user.photos):
            raise ValidationError("Must include all photo IDs")
        if len(set(photo_ids)) != len(photo_ids):
            raise ValidationError("Duplicate photo IDs in order list")

        photo_map = {p.id: p for p in user.photos}
        for photo_id in photo_ids:
            if photo_id not in photo_map:
                raise ValidationError(f"Photo {photo_id} not found")

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
        """Soft-delete account and purge all related data."""
        if user.password_hash and not verify_password(password, user.password_hash):
            raise ForbiddenError("Invalid password")

        user_id = str(user.id)
        from app.core.storage import storage

        # Delete photos from object storage (best-effort)
        for p in user.photos:
            try:
                await storage.delete_file(p.url)
            except Exception:
                pass

        # Purge swipes, blocks, reports authored by this user
        await Swipe.find({"$or": [
            {"swiper_id": user_id}, {"swiped_id": user_id}
        ]}).delete()
        await Block.find({"$or": [
            {"blocker_id": user_id}, {"blocked_id": user_id}
        ]}).delete()
        await Report.find({"reporter_id": user_id}).delete()

        # Deactivate matches & conversations (keep messages for moderation/legal hold)
        await Match.find({"$or": [
            {"user1_id": user_id}, {"user2_id": user_id}
        ]}).update({"$set": {"is_active": False}})
        await Conversation.find({"$or": [
            {"user1_id": user_id}, {"user2_id": user_id}
        ]}).update({"$set": {"is_active": False, "closed_reason": "deleted_account"}})

        # Revoke auth + devices
        await RefreshToken.find(RefreshToken.user_id == user_id).update(
            {"$set": {"is_revoked": True}}
        )
        await Device.find(Device.user_id == user_id).delete()

        # Cancel subscriptions
        await Subscription.find(Subscription.user_id == user_id).update(
            {"$set": {"status": SubscriptionStatus.CANCELLED.value, "cancelled_at": datetime.now(timezone.utc)}}
        )

        # Soft delete: keep the user row so reports referencing them still resolve.
        user.is_deleted = True
        user.deleted_at = datetime.now(timezone.utc)
        user.is_online = False
        user.email = f"deleted_{user_id}@deleted.local"
        user.name = "Deleted user"
        user.bio = None
        user.interests = ["deleted"]
        user.photos = []
        user.location = None
        user.location_geo = None
        user.password_hash = ""
        user.google_id = None
        user.apple_id = None
        user.facebook_id = None
        user.verification_code = None
        user.password_reset_token = None
        await user.save()


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    from math import radians, cos, sin, asin, sqrt
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * asin(sqrt(a)) * 3956


class DiscoveryService:
    @staticmethod
    async def get_potential_matches(
        user: User,
        limit: int = 10,
        offset: int = 0,
    ) -> Tuple[List[dict], int]:
        """Discover potential matches using MongoDB $geoNear aggregation.
        DB-side pagination, indexed geo filter, sorted by proximity."""
        user_id = str(user.id)

        if not user.location_geo:
            return [], 0
        if not user.is_profile_complete():
            return [], 0

        # Collect excluded ids: already-swiped + blocked (both directions) + self
        swiped_docs = await Swipe.find(Swipe.swiper_id == user_id).to_list()
        excluded = {s.swiped_id for s in swiped_docs}

        blocks = await Block.find({"$or": [
            {"blocker_id": user_id}, {"blocked_id": user_id}
        ]}).to_list()
        for b in blocks:
            excluded.add(b.blocker_id)
            excluded.add(b.blocked_id)
        excluded.discard(user_id)
        excluded.add(user_id)

        # Convert string ids to ObjectId for $nin
        excluded_oids = []
        for sid in excluded:
            try:
                excluded_oids.append(ObjectId(sid))
            except Exception:
                pass

        looking_for = user.looking_for.value if hasattr(user.looking_for, "value") else user.looking_for
        gender = user.gender.value if hasattr(user.gender, "value") else user.gender
        max_distance_meters = int(user.preferences.max_distance / MILES_PER_METER)

        pipeline = [
            {
                "$geoNear": {
                    "near": {
                        "type": "Point",
                        "coordinates": user.location_geo.coordinates,
                    },
                    "distanceField": "distance_meters",
                    "maxDistance": max_distance_meters,
                    "spherical": True,
                    "key": "location_geo",
                    "query": {
                        "_id": {"$nin": excluded_oids},
                        "is_deleted": {"$ne": True},
                        "gender": looking_for,
                        "looking_for": gender,
                        "age": {"$gte": user.preferences.min_age, "$lte": user.preferences.max_age},
                        "settings.discovery_enabled": True,
                        "photos.0": {"$exists": True},
                        "interests.0": {"$exists": True, "$ne": ""},
                    },
                }
            },
            {"$skip": offset},
            {"$limit": limit + 1},  # +1 to detect has_more
        ]

        db = get_database()
        cursor = db["users"].aggregate(pipeline)
        raw_results = await cursor.to_list(length=limit + 1)

        # has_more is derived; total count for large sets is intentionally cheap (-1 sentinel)
        has_more = len(raw_results) > limit
        raw_results = raw_results[:limit]

        results = []
        user_interests = set(user.interests)
        for doc in raw_results:
            # Reconstruct User
            doc["_id"] = doc["_id"]  # already ObjectId
            potential = User(**doc)
            distance_meters = doc.get("distance_meters")
            distance_miles = distance_meters * MILES_PER_METER if distance_meters is not None else None
            common = list(user_interests & set(potential.interests))
            results.append({
                "user": potential,
                "distance": distance_miles,
                "common_interests": common,
            })

        # Approximate total = current page; client should rely on has_more for paging
        total = offset + len(results) + (1 if has_more else 0)
        return results, total


class SwipeService:
    @staticmethod
    async def _try_create_match(swiper_id: str, swiped_id: str) -> Optional[Match]:
        """Atomically create a Match + Conversation if mutual. Returns the Match,
        or None if no mutual interest yet. Idempotent on concurrent calls."""
        mutual = await Swipe.find_one({
            "swiper_id": swiped_id,
            "swiped_id": swiper_id,
            "swipe_type": {"$in": [SwipeType.LIKE.value, SwipeType.SUPER_LIKE.value]},
        })
        if not mutual:
            return None

        low, high = Match.canonical_pair(swiper_id, swiped_id)

        # Already matched?
        existing = await Match.find_one({"user_low": low, "user_high": high})
        if existing:
            if not existing.is_active:
                existing.is_active = True
                await existing.save()
            return existing

        match = Match(
            user1_id=swiper_id,
            user2_id=swiped_id,
            user_low=low,
            user_high=high,
        )
        try:
            await match.insert()
        except DuplicateKeyError:
            # Concurrent like won the race — return the winner.
            return await Match.find_one({"user_low": low, "user_high": high})

        # Conversation (match_id is unique-indexed; rare race protected by upsert)
        existing_conv = await Conversation.find_one({"match_id": str(match.id)})
        if not existing_conv:
            conv = Conversation(
                match_id=str(match.id),
                user1_id=swiper_id,
                user2_id=swiped_id,
            )
            try:
                await conv.insert()
            except DuplicateKeyError:
                pass

        return match

    @staticmethod
    async def _ensure_can_swipe(swiper: User, swiped_id: str):
        if swiper.is_deleted:
            raise ForbiddenError("Account is deleted")
        if swiper.id and str(swiper.id) == swiped_id:
            raise ValidationError("Cannot swipe on yourself")

        swiped_user = await User.get(swiped_id)
        if not swiped_user or swiped_user.is_deleted:
            raise NotFoundError("User not found")

        # Block check (either direction)
        blocked = await Block.find_one({"$or": [
            {"blocker_id": str(swiper.id), "blocked_id": swiped_id},
            {"blocker_id": swiped_id, "blocked_id": str(swiper.id)},
        ]})
        if blocked:
            raise NotFoundError("User not found")

    @staticmethod
    async def like(swiper: User, swiped_id: str) -> Tuple[bool, Optional[Match]]:
        await SwipeService._ensure_can_swipe(swiper, swiped_id)
        swipe = Swipe(
            swiper_id=str(swiper.id),
            swiped_id=swiped_id,
            swipe_type=SwipeType.LIKE,
        )
        try:
            await swipe.insert()
        except DuplicateKeyError:
            raise ValidationError("Already swiped on this user")

        match = await SwipeService._try_create_match(str(swiper.id), swiped_id)
        return (match is not None), match

    @staticmethod
    async def pass_user(swiper: User, swiped_id: str):
        await SwipeService._ensure_can_swipe(swiper, swiped_id)
        swipe = Swipe(
            swiper_id=str(swiper.id),
            swiped_id=swiped_id,
            swipe_type=SwipeType.PASS,
        )
        try:
            await swipe.insert()
        except DuplicateKeyError:
            raise ValidationError("Already swiped on this user")

    @staticmethod
    def _today_key() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    async def super_like(swiper: User, swiped_id: str) -> Tuple[bool, Optional[Match], int]:
        await SwipeService._ensure_can_swipe(swiper, swiped_id)

        today = SwipeService._today_key()
        # Free users: 1/day. Premium: 5/day.
        daily_cap = 5 if SubscriptionService.is_premium(swiper) else 1

        if swiper.super_likes_day != today:
            swiper.super_likes_day = today
            swiper.super_likes_remaining = daily_cap
            await swiper.save()

        if swiper.super_likes_remaining <= 0:
            raise ValidationError("No super likes remaining today")

        swipe = Swipe(
            swiper_id=str(swiper.id),
            swiped_id=swiped_id,
            swipe_type=SwipeType.SUPER_LIKE,
        )
        try:
            await swipe.insert()
        except DuplicateKeyError:
            raise ValidationError("Already swiped on this user")

        swiper.super_likes_remaining -= 1
        await swiper.save()

        match = await SwipeService._try_create_match(str(swiper.id), swiped_id)
        return (match is not None), match, swiper.super_likes_remaining

    @staticmethod
    async def undo_last_swipe(user: User) -> Optional[Swipe]:
        """Undo the last swipe. Premium-only."""
        if not SubscriptionService.is_premium(user):
            raise ForbiddenError("Undo requires premium subscription")

        last_swipe = await Swipe.find(
            Swipe.swiper_id == str(user.id)
        ).sort(-Swipe.created_at).first_or_none()

        if not last_swipe:
            raise NotFoundError("No swipe to undo")

        # If the swipe produced a match, undo that too
        if last_swipe.swipe_type in [SwipeType.LIKE, SwipeType.SUPER_LIKE]:
            low, high = Match.canonical_pair(str(user.id), last_swipe.swiped_id)
            match = await Match.find_one({"user_low": low, "user_high": high})
            if match and match.is_active:
                match.is_active = False
                await match.save()
                conv = await Conversation.find_one({"match_id": str(match.id)})
                if conv:
                    conv.is_active = False
                    conv.closed_reason = "unmatched"
                    await conv.save()

            # Refund super-like if applicable
            if last_swipe.swipe_type == SwipeType.SUPER_LIKE:
                today = SwipeService._today_key()
                if user.super_likes_day == today:
                    user.super_likes_remaining += 1
                    await user.save()

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
        """DB-paginated matches with batched user + conversation fetch (no N+1)."""
        user_id = str(user.id)

        query: dict = {
            "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
            "is_active": True,
        }
        if new_only:
            query["$or"] = [
                {"user1_id": user_id, "user1_seen": False},
                {"user2_id": user_id, "user2_seen": False},
            ]

        total = await Match.find(query).count()
        matches = await Match.find(query).sort(-Match.matched_at).skip(offset).limit(limit).to_list()

        if not matches:
            return [], total

        # Batch fetch other users
        other_ids = []
        for m in matches:
            other_ids.append(m.get_other_user_id(user_id))
        other_oids = []
        for oid in other_ids:
            try:
                other_oids.append(ObjectId(oid))
            except Exception:
                pass

        other_users = await User.find({"_id": {"$in": other_oids}}).to_list()
        user_map = {str(u.id): u for u in other_users}

        # Batch fetch conversations
        match_ids = [str(m.id) for m in matches]
        convs = await Conversation.find({"match_id": {"$in": match_ids}}).to_list()
        conv_map = {c.match_id: c for c in convs}

        results = []
        for m in matches:
            other = user_map.get(m.get_other_user_id(user_id))
            if not other or other.is_deleted:
                continue
            conv = conv_map.get(str(m.id))
            last_message = None
            if conv and conv.last_message_content:
                last_message = {
                    "id": conv.last_message_id,
                    "content": conv.last_message_content,
                    "sender_id": conv.last_message_sender_id,
                    "timestamp": conv.last_message_at.isoformat() if conv.last_message_at else None,
                }
            results.append({
                "match": m,
                "other_user": other,
                "is_new": m.is_new_for_user(user_id),
                "last_message": last_message,
            })

        return results, total

    @staticmethod
    async def unmatch(user: User, match_id: str):
        match = await Match.get(match_id)
        if not match:
            raise NotFoundError("Match not found")

        if str(user.id) not in [match.user1_id, match.user2_id]:
            raise ForbiddenError("Not authorized")

        match.is_active = False
        await match.save()

        conv = await Conversation.find_one({"match_id": match_id})
        if conv:
            conv.is_active = False
            conv.closed_reason = "unmatched"
            await conv.save()


class BlockService:
    @staticmethod
    async def block_user(blocker: User, blocked_id: str):
        if str(blocker.id) == blocked_id:
            raise ValidationError("Cannot block yourself")

        blocked_user = await User.get(blocked_id)
        if not blocked_user:
            raise NotFoundError("User not found")

        existing = await Block.find_one({
            "blocker_id": str(blocker.id),
            "blocked_id": blocked_id,
        })
        if existing:
            raise ValidationError("User already blocked")

        block = Block(blocker_id=str(blocker.id), blocked_id=blocked_id)
        await block.insert()

        # Deactivate any matches and conversations in BOTH directions
        low, high = Match.canonical_pair(str(blocker.id), blocked_id)
        match = await Match.find_one({"user_low": low, "user_high": high, "is_active": True})
        if match:
            match.is_active = False
            await match.save()
            conv = await Conversation.find_one({"match_id": str(match.id)})
            if conv:
                conv.is_active = False
                conv.closed_reason = "blocked"
                await conv.save()

    @staticmethod
    async def unblock_user(blocker: User, blocked_id: str):
        block = await Block.find_one({
            "blocker_id": str(blocker.id),
            "blocked_id": blocked_id,
        })
        if not block:
            raise NotFoundError("User not blocked")
        await block.delete()

    @staticmethod
    async def get_blocked_users(user: User) -> List[dict]:
        blocks = await Block.find(Block.blocker_id == str(user.id)).to_list()
        if not blocks:
            return []

        blocked_oids = []
        for b in blocks:
            try:
                blocked_oids.append(ObjectId(b.blocked_id))
            except Exception:
                pass

        users = await User.find({"_id": {"$in": blocked_oids}}).to_list()
        user_map = {str(u.id): u for u in users}

        results = []
        for b in blocks:
            u = user_map.get(b.blocked_id)
            if not u:
                continue
            results.append({
                "id": b.blocked_id,
                "name": u.name,
                "blocked_at": b.created_at.isoformat(),
            })
        return results


class ReportService:
    @staticmethod
    async def report_user(reporter: User, reported_id: str, reason: str, details: Optional[str] = None):
        if str(reporter.id) == reported_id:
            raise ValidationError("Cannot report yourself")

        reported_user = await User.get(reported_id)
        if not reported_user:
            raise NotFoundError("User not found")

        # Rate limit: 1 report per (reporter, reported) per day
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=1)
        existing = await Report.find_one({
            "reporter_id": str(reporter.id),
            "reported_id": reported_id,
            "created_at": {"$gte": since},
        })
        if existing:
            raise ValidationError("You have already reported this user recently")

        report = Report(
            reporter_id=str(reporter.id),
            reported_id=reported_id,
            reason=reason,
            details=details,
        )
        await report.insert()


class SubscriptionService:
    """Premium entitlement is derived from active Subscription rows + cached
    fields on User for fast checks. Webhooks update both."""

    @staticmethod
    def is_premium(user: User) -> bool:
        if not user.is_premium:
            return False
        if not user.premium_expires_at:
            return False
        # Handle naive datetime from older docs
        exp = user.premium_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > datetime.now(timezone.utc)

    @staticmethod
    async def apply_subscription(user: User, sub: Subscription) -> User:
        """Sync cached premium flags from a Subscription record."""
        active = sub.is_active()
        user.is_premium = active
        user.premium_expires_at = sub.current_period_end if active else None
        await user.save()
        return user
