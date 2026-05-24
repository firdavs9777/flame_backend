from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from app.models.user import User
from app.models.conversation import Conversation, PinnedMessage
from app.models.message import Message, MessageType, MessageStatus, Reaction, ReplyInfo, MediaInfo
from app.models.match import Match
from app.models.sticker import Sticker, StickerPack, UserStickerPack, RecentSticker
from app.core.exceptions import NotFoundError, ForbiddenError, ValidationError
from app.core.database import get_database
from app.core.cache import online_tracker


class ChatService:
    @staticmethod
    async def get_conversations(
        user: User,
        limit: int = 20,
        offset: int = 0,
        include_closed: bool = False,
    ) -> Tuple[List[dict], int]:
        """
        Get user's conversations.

        OPTIMIZED:
        - Uses database-level pagination instead of in-memory
        - Batch fetches all other users in single query (fixes N+1 problem)
        - Reduces from N+1 queries to just 2 queries
        """
        user_id = str(user.id)
        db = get_database()

        # Build the query filter — exclude closed convos by default
        query: Dict[str, Any] = {
            "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
        }
        if not include_closed:
            query["is_active"] = True

        # Get total count first (for pagination info)
        total = await Conversation.find(query).count()

        # Get paginated conversations from database (not in-memory!)
        conversations = await Conversation.find(query).sort(
            -Conversation.updated_at
        ).skip(offset).limit(limit).to_list()

        if not conversations:
            return [], total

        # Collect all other user IDs
        other_user_ids = []
        for conv in conversations:
            other_id = conv.user2_id if conv.user1_id == user_id else conv.user1_id
            other_user_ids.append(other_id)

        # Batch fetch all users in ONE query (fixes N+1 problem)
        other_users = await User.find({
            "_id": {"$in": [ObjectId(uid) for uid in other_user_ids]}
        }).to_list()

        # Create lookup map for O(1) access
        user_map: Dict[str, User] = {str(u.id): u for u in other_users}

        # Build results
        results = []
        now = datetime.now(timezone.utc)

        for conv in conversations:
            other_id = conv.user2_id if conv.user1_id == user_id else conv.user1_id
            other_user = user_map.get(other_id)

            if not other_user:
                continue

            # Build last message info from cached data.
            # Status: "read" iff the OTHER user has zero unread (they've seen it).
            last_message = None
            if conv.last_message_id:
                if conv.last_message_sender_id == user_id:
                    other_unread = conv.get_unread_count(
                        conv.get_other_user_id(user_id)
                    )
                    status = "read" if other_unread == 0 else "delivered"
                else:
                    status = "delivered"
                last_message = {
                    "id": conv.last_message_id,
                    "content": conv.last_message_content,
                    "sender_id": conv.last_message_sender_id,
                    "timestamp": conv.last_message_at.isoformat() if conv.last_message_at else None,
                    "status": status,
                }

            # Check mute status
            is_muted = False
            muted_until = None
            if user_id == conv.user1_id and conv.user1_muted_until:
                if conv.user1_muted_until > now:
                    is_muted = True
                    muted_until = conv.user1_muted_until.isoformat()
            elif user_id == conv.user2_id and conv.user2_muted_until:
                if conv.user2_muted_until > now:
                    is_muted = True
                    muted_until = conv.user2_muted_until.isoformat()

            results.append({
                "conversation": conv,
                "other_user": other_user,
                "unread_count": conv.get_unread_count(user_id),
                "last_message": last_message,
                "is_muted": is_muted,
                "muted_until": muted_until,
            })

        return results, total

    @staticmethod
    async def get_conversation(
        conversation_id: str,
        user: User,
        require_active: bool = True,
    ) -> Conversation:
        """Get a specific conversation. By default refuses inactive convos
        (block/unmatch/deleted_account) so messages can't be sent across them."""
        try:
            conv = await Conversation.get(conversation_id)
        except Exception:
            raise NotFoundError("Conversation not found")
        if not conv:
            raise NotFoundError("Conversation not found")

        if str(user.id) not in [conv.user1_id, conv.user2_id]:
            raise ForbiddenError("Not authorized")

        if require_active and not conv.is_active:
            raise ForbiddenError("This conversation is no longer active")

        return conv

    @staticmethod
    async def get_messages(
        conversation_id: str,
        user: User,
        limit: int = 50,
        before: Optional[str] = None,
    ) -> Tuple[List[Message], bool]:
        """Read messages — allowed even on inactive conversations (history)."""
        conv = await ChatService.get_conversation(conversation_id, user, require_active=False)

        query: Dict[str, Any] = {
            "conversation_id": str(conv.id),
            "is_deleted": {"$ne": True}
        }

        # Cursor-based pagination using _id (more efficient)
        if before:
            # Validate ObjectId format
            if ObjectId.is_valid(before):
                query["_id"] = {"$lt": ObjectId(before)}

        messages = (
            await Message.find(query)
            .sort([("_id", -1)])  # Sort by _id descending (newest first)
            .limit(limit + 1)
            .to_list()
        )

        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        # Reverse to get chronological order (oldest to newest)
        messages.reverse()

        return messages, has_more

    @staticmethod
    async def send_message(
        conversation_id: str,
        sender: User,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        audio_url: Optional[str] = None,
        file_url: Optional[str] = None,
        sticker_id: Optional[str] = None,
        media_info: Optional[MediaInfo] = None,
        reply_to_id: Optional[str] = None,
    ) -> Message:
        """Send a message. Rejects inactive conversations (block/unmatch)."""
        conv = await ChatService.get_conversation(conversation_id, sender, require_active=True)

        # Defensive: also reject if the underlying match is no longer active
        # (e.g. one of the users blocked the other after the conversation was loaded)
        match = await Match.find_one({"_id": ObjectId(conv.match_id)}) if ObjectId.is_valid(conv.match_id) else None
        if match and not match.is_active:
            raise ForbiddenError("This conversation is no longer active")

        # Validate content
        if message_type == MessageType.TEXT:
            if not content or not content.strip():
                raise ValidationError("Message cannot be empty")
            if len(content) > 5000:
                raise ValidationError("Message too long (max 5000 characters)")

        # Handle reply
        reply_to = None
        if reply_to_id:
            reply_msg = await Message.get(reply_to_id)
            if reply_msg and reply_msg.conversation_id == str(conv.id):
                reply_sender = await User.get(reply_msg.sender_id)
                reply_to = ReplyInfo(
                    message_id=str(reply_msg.id),
                    sender_id=reply_msg.sender_id,
                    sender_name=reply_sender.name if reply_sender else "Unknown",
                    content=(reply_msg.content or "")[:100],
                    type=reply_msg.type,
                )

        # Status: DELIVERED if recipient is online (Redis presence), else SENT
        other_id = conv.get_other_user_id(str(sender.id))
        recipient_online = await online_tracker.is_online(other_id)
        status = MessageStatus.DELIVERED if recipient_online else MessageStatus.SENT

        message = Message(
            conversation_id=str(conv.id),
            sender_id=str(sender.id),
            content=content,
            type=message_type,
            image_url=image_url,
            video_url=video_url,
            audio_url=audio_url,
            file_url=file_url,
            sticker_id=sticker_id,
            media_info=media_info,
            reply_to=reply_to,
            status=status,
        )
        await message.insert()

        # Update conversation
        preview_content = content[:100]
        if message_type == MessageType.IMAGE:
            preview_content = "📷 Photo"
        elif message_type == MessageType.VIDEO:
            preview_content = "🎬 Video"
        elif message_type == MessageType.AUDIO:
            preview_content = "🎵 Audio"
        elif message_type == MessageType.VOICE:
            preview_content = "🎤 Voice message"
        elif message_type == MessageType.STICKER:
            preview_content = "🎨 Sticker"
        elif message_type == MessageType.FILE:
            preview_content = "📎 File"
        elif message_type == MessageType.GIF:
            preview_content = "GIF"

        conv.last_message_id = str(message.id)
        conv.last_message_content = preview_content
        conv.last_message_sender_id = str(sender.id)
        conv.last_message_at = message.timestamp
        conv.updated_at = datetime.now(timezone.utc)

        # Increment unread for other user
        other_user_id = conv.get_other_user_id(str(sender.id))
        conv.increment_unread(other_user_id)

        await conv.save()

        return message

    @staticmethod
    async def edit_message(
        message_id: str,
        user: User,
        new_content: str,
    ) -> Message:
        """Edit a message (only text messages, within time limit)."""
        message = await Message.get(message_id)
        if not message:
            raise NotFoundError("Message not found")

        if message.sender_id != str(user.id):
            raise ForbiddenError("Can only edit your own messages")

        if message.type != MessageType.TEXT:
            raise ValidationError("Can only edit text messages")

        if not new_content or not new_content.strip():
            raise ValidationError("Message cannot be empty")
        if len(new_content) > 5000:
            raise ValidationError("Message too long (max 5000 characters)")

        # Time limit (15 minutes — match common UX)
        ts = message.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < datetime.now(timezone.utc) - timedelta(minutes=15):
            raise ValidationError("Cannot edit messages older than 15 minutes")

        message.content = new_content
        message.is_edited = True
        message.edited_at = datetime.now(timezone.utc)
        await message.save()

        # If this is the latest message in the conversation, refresh the preview
        conv = await Conversation.get(message.conversation_id)
        if conv and conv.last_message_id == str(message.id):
            conv.last_message_content = new_content[:100]
            await conv.save()

        return message

    @staticmethod
    async def delete_message(
        message_id: str,
        user: User,
        for_everyone: bool = False,
    ) -> Message:
        """Delete a message (soft delete)."""
        message = await Message.get(message_id)
        if not message:
            raise NotFoundError("Message not found")

        if message.sender_id != str(user.id):
            raise ForbiddenError("Can only delete your own messages")

        message.is_deleted = True
        message.deleted_at = datetime.now(timezone.utc)
        message.content = "This message was deleted"
        await message.save()

        # Refresh conversation preview if this was the latest message
        conv = await Conversation.get(message.conversation_id)
        if conv and conv.last_message_id == str(message.id):
            conv.last_message_content = "This message was deleted"
            await conv.save()

        return message

    @staticmethod
    async def add_reaction(
        message_id: str,
        user: User,
        emoji: str,
    ) -> Message:
        """Add a reaction to a message."""
        message = await Message.get(message_id)
        if not message:
            raise NotFoundError("Message not found")

        # Verify user has access to conversation
        await ChatService.get_conversation(message.conversation_id, user)

        # Remove existing reaction from this user (if any)
        message.reactions = [r for r in message.reactions if r.user_id != str(user.id)]

        # Add new reaction
        message.reactions.append(Reaction(
            emoji=emoji,
            user_id=str(user.id),
        ))

        await message.save()
        return message

    @staticmethod
    async def remove_reaction(
        message_id: str,
        user: User,
    ) -> Message:
        """Remove user's reaction from a message."""
        message = await Message.get(message_id)
        if not message:
            raise NotFoundError("Message not found")

        # Verify user has access to conversation
        await ChatService.get_conversation(message.conversation_id, user)

        # Remove reaction from this user
        message.reactions = [r for r in message.reactions if r.user_id != str(user.id)]

        await message.save()
        return message

    @staticmethod
    async def pin_message(
        conversation_id: str,
        message_id: str,
        user: User,
    ) -> Conversation:
        """Pin a message in conversation."""
        conv = await ChatService.get_conversation(conversation_id, user)
        message = await Message.get(message_id)

        if not message or message.conversation_id != str(conv.id):
            raise NotFoundError("Message not found in this conversation")

        # Check if already pinned
        if any(p.message_id == message_id for p in conv.pinned_messages):
            raise ValidationError("Message already pinned")

        # Limit to 5 pinned messages
        if len(conv.pinned_messages) >= 5:
            raise ValidationError("Maximum 5 pinned messages allowed")

        conv.pinned_messages.append(PinnedMessage(
            message_id=message_id,
            content=message.content[:100],
            pinned_by=str(user.id),
        ))

        await conv.save()
        return conv

    @staticmethod
    async def unpin_message(
        conversation_id: str,
        message_id: str,
        user: User,
    ) -> Conversation:
        """Unpin a message from conversation."""
        conv = await ChatService.get_conversation(conversation_id, user)

        conv.pinned_messages = [p for p in conv.pinned_messages if p.message_id != message_id]

        await conv.save()
        return conv

    @staticmethod
    async def mute_conversation(
        conversation_id: str,
        user: User,
        duration_hours: Optional[int] = None,
    ) -> Conversation:
        """Mute a conversation."""
        conv = await ChatService.get_conversation(conversation_id, user)

        if duration_hours == 0:
            # Unmute
            muted_until = None
        elif duration_hours is None:
            # Mute forever (set to far future)
            muted_until = datetime.now(timezone.utc) + timedelta(days=365 * 100)
        else:
            muted_until = datetime.now(timezone.utc) + timedelta(hours=duration_hours)

        if str(user.id) == conv.user1_id:
            conv.user1_muted_until = muted_until
        else:
            conv.user2_muted_until = muted_until

        await conv.save()
        return conv

    @staticmethod
    async def mark_messages_read(
        conversation_id: str,
        user: User,
        message_ids: Optional[List[str]] = None,
    ):
        """Mark messages as read. Empty/None message_ids = mark ALL unread."""
        conv = await ChatService.get_conversation(conversation_id, user, require_active=False)
        user_id = str(user.id)

        query: Dict[str, Any] = {
            "conversation_id": str(conv.id),
            "sender_id": {"$ne": user_id},
            "status": {"$ne": MessageStatus.READ.value},
        }
        if message_ids:
            object_ids = [ObjectId(mid) for mid in message_ids if ObjectId.is_valid(mid)]
            if not object_ids:
                return 0
            query["_id"] = {"$in": object_ids}

        result = await Message.find(query).update_many({
            "$set": {
                "status": MessageStatus.READ.value,
                "read_at": datetime.now(timezone.utc),
            }
        })

        conv.reset_unread(user_id)
        await conv.save()
        return result.modified_count if result else 0

    @staticmethod
    async def get_conversation_by_match(match_id: str, user: User) -> Optional[Conversation]:
        """Get conversation by match ID."""
        conv = await Conversation.find_one({"match_id": match_id})
        if not conv:
            return None

        if str(user.id) not in [conv.user1_id, conv.user2_id]:
            raise ForbiddenError("Not authorized")

        return conv


class StickerService:
    """Service for sticker management."""

    @staticmethod
    async def get_sticker_packs(include_stickers: bool = False) -> List[StickerPack]:
        """Get all available sticker packs."""
        packs = await StickerPack.find_all().to_list()
        return packs

    @staticmethod
    async def get_sticker_pack(pack_id: str) -> Tuple[StickerPack, List[Sticker]]:
        """Get a sticker pack with its stickers."""
        pack = await StickerPack.get(pack_id)
        if not pack:
            raise NotFoundError("Sticker pack not found")

        stickers = await Sticker.find({"pack_id": pack_id}).sort(Sticker.order).to_list()
        return pack, stickers

    @staticmethod
    async def get_user_sticker_packs(user: User) -> List[StickerPack]:
        """Get user's saved sticker packs."""
        user_packs = await UserStickerPack.find({"user_id": str(user.id)}).to_list()
        pack_ids = [up.pack_id for up in user_packs]

        if not pack_ids:
            return []

        packs = await StickerPack.find({"_id": {"$in": [ObjectId(pid) for pid in pack_ids]}}).to_list()
        return packs

    @staticmethod
    async def add_sticker_pack(user: User, pack_id: str):
        """Add a sticker pack to user's collection."""
        pack = await StickerPack.get(pack_id)
        if not pack:
            raise NotFoundError("Sticker pack not found")

        existing = await UserStickerPack.find_one({
            "user_id": str(user.id),
            "pack_id": pack_id
        })
        if existing:
            raise ValidationError("Pack already added")

        user_pack = UserStickerPack(
            user_id=str(user.id),
            pack_id=pack_id,
        )
        await user_pack.insert()

    @staticmethod
    async def remove_sticker_pack(user: User, pack_id: str):
        """Remove a sticker pack from user's collection."""
        await UserStickerPack.find_one({
            "user_id": str(user.id),
            "pack_id": pack_id
        }).delete()

    @staticmethod
    async def get_recent_stickers(user: User, limit: int = 20) -> List[Sticker]:
        """Get user's recently used stickers."""
        recent = await RecentSticker.find(
            {"user_id": str(user.id)}
        ).sort(-RecentSticker.used_at).limit(limit).to_list()

        sticker_ids = [r.sticker_id for r in recent]
        if not sticker_ids:
            return []

        stickers = await Sticker.find(
            {"_id": {"$in": [ObjectId(sid) for sid in sticker_ids]}}
        ).to_list()

        # Sort by recent order
        sticker_map = {str(s.id): s for s in stickers}
        return [sticker_map[sid] for sid in sticker_ids if sid in sticker_map]

    @staticmethod
    async def record_sticker_use(user: User, sticker_id: str):
        """Record that a user used a sticker."""
        # Update or insert
        existing = await RecentSticker.find_one({
            "user_id": str(user.id),
            "sticker_id": sticker_id
        })
        if existing:
            existing.used_at = datetime.now(timezone.utc)
            await existing.save()
        else:
            recent = RecentSticker(
                user_id=str(user.id),
                sticker_id=sticker_id,
            )
            await recent.insert()

        # Keep only last 50 recent stickers
        all_recent = await RecentSticker.find(
            {"user_id": str(user.id)}
        ).sort(-RecentSticker.used_at).to_list()

        if len(all_recent) > 50:
            old_ids = [ObjectId(r.id) for r in all_recent[50:]]
            await RecentSticker.find({"_id": {"$in": old_ids}}).delete()

    @staticmethod
    async def get_sticker(sticker_id: str) -> Sticker:
        """Get a sticker by ID."""
        sticker = await Sticker.get(sticker_id)
        if not sticker:
            raise NotFoundError("Sticker not found")
        return sticker
