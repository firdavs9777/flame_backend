from pydantic import BaseModel
from typing import Optional, List
from app.models.message import MessageType


class MessageResponse(BaseModel):
    id: str
    sender_id: str
    content: str
    type: str
    timestamp: str
    status: str


class ConversationUserResponse(BaseModel):
    id: str
    name: str
    photos: List[str]
    is_online: bool


class ConversationResponse(BaseModel):
    id: str
    match_id: str
    other_user: ConversationUserResponse
    last_message: Optional[MessageResponse] = None
    unread_count: int
    updated_at: str


class ConversationListResponse(BaseModel):
    conversations: List[ConversationResponse]
    pagination: dict


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    has_more: bool


class SendMessageRequest(BaseModel):
    content: str
    type: MessageType = MessageType.TEXT


class MarkReadRequest(BaseModel):
    message_ids: List[str]


# WebSocket Event Schemas
class WSMessage(BaseModel):
    event: str
    data: dict


class WSTypingEvent(BaseModel):
    conversation_id: str


class WSMessageReadEvent(BaseModel):
    conversation_id: str
    message_ids: List[str]
