from typing import List, Optional, Tuple
from datetime import datetime, timezone
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message, MessageType, MessageStatus
from app.models.match import Match
from app.core.exceptions import NotFoundError, ForbiddenError


class ChatService:
    @staticmethod
    async def get_conversations(
        user: User,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[dict], int]:
        """Get user's conversations."""
        query = {
            "$or": [
                {"user1_id": str(user.id)},
                {"user2_id": str(user.id)},
            ]
        }

        conversations = await Conversation.find(query).sort(-Conversation.updated_at).to_list()

        results = []
        for conv in conversations:
            other_user_id = conv.get_other_user_id(str(user.id))
            other_user = await User.get(other_user_id)
            if not other_user:
                continue

            last_message = None
            if conv.last_message_id:
                last_message = {
                    "id": conv.last_message_id,
                    "content": conv.last_message_content,
                    "sender_id": conv.last_message_sender_id,
                    "timestamp": conv.last_message_at.isoformat() if conv.last_message_at else None,
                    "status": "delivered",
                }

            results.append({
                "conversation": conv,
                "other_user": other_user,
                "unread_count": conv.get_unread_count(str(user.id)),
                "last_message": last_message,
            })

        total = len(results)
        paginated = results[offset : offset + limit]

        return paginated, total

    @staticmethod
    async def get_conversation(conversation_id: str, user: User) -> Conversation:
        """Get a specific conversation."""
        conv = await Conversation.get(conversation_id)
        if not conv:
            raise NotFoundError("Conversation not found")

        if str(user.id) not in [conv.user1_id, conv.user2_id]:
            raise ForbiddenError("Not authorized")

        return conv

    @staticmethod
    async def get_messages(
        conversation_id: str,
        user: User,
        limit: int = 50,
        before: Optional[str] = None,
    ) -> Tuple[List[Message], bool]:
        """Get messages in a conversation."""
        conv = await ChatService.get_conversation(conversation_id, user)

        query = {"conversation_id": str(conv.id)}

        if before:
            before_msg = await Message.get(before)
            if before_msg:
                query["timestamp"] = {"$lt": before_msg.timestamp}

        messages = (
            await Message.find(query)
            .sort(-Message.timestamp)
            .limit(limit + 1)
            .to_list()
        )

        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        # Reverse to get chronological order
        messages.reverse()

        return messages, has_more

    @staticmethod
    async def send_message(
        conversation_id: str,
        sender: User,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        image_url: Optional[str] = None,
    ) -> Message:
        """Send a message in a conversation."""
        conv = await ChatService.get_conversation(conversation_id, sender)

        message = Message(
            conversation_id=str(conv.id),
            sender_id=str(sender.id),
            content=content,
            type=message_type,
            image_url=image_url,
            status=MessageStatus.SENT,
        )
        await message.insert()

        # Update conversation
        conv.last_message_id = str(message.id)
        conv.last_message_content = content[:100]  # Truncate for preview
        conv.last_message_sender_id = str(sender.id)
        conv.last_message_at = message.timestamp
        conv.updated_at = datetime.now(timezone.utc)

        # Increment unread for other user
        other_user_id = conv.get_other_user_id(str(sender.id))
        conv.increment_unread(other_user_id)

        await conv.save()

        return message

    @staticmethod
    async def mark_messages_read(
        conversation_id: str,
        user: User,
        message_ids: List[str],
    ):
        """Mark messages as read."""
        conv = await ChatService.get_conversation(conversation_id, user)

        # Update message statuses
        await Message.find({
            "conversation_id": str(conv.id),
            "_id": {"$in": message_ids},
            "sender_id": {"$ne": str(user.id)}
        }).update({"$set": {"status": MessageStatus.READ.value}})

        # Reset unread count
        conv.reset_unread(str(user.id))
        await conv.save()

    @staticmethod
    async def get_conversation_by_match(match_id: str, user: User) -> Optional[Conversation]:
        """Get conversation by match ID."""
        conv = await Conversation.find_one(Conversation.match_id == match_id)
        if not conv:
            return None

        if str(user.id) not in [conv.user1_id, conv.user2_id]:
            raise ForbiddenError("Not authorized")

        return conv
