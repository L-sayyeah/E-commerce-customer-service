from datetime import datetime

from pydantic import BaseModel, Field


class CreateChatSessionRequest(BaseModel):
    user_id: str | None = Field(default=None, description="用户ID")
    channel: str = Field(default="web", description="会话渠道")


class ChatSessionResponse(BaseModel):
    id: int
    session_id: str
    user_id: str | None
    channel: str
    status: str
    create_at: datetime


class SendMessageRequest(BaseModel):
    session_id: str = Field(description="业务会话ID")
    content: str = Field(min_length=1, description="用户消息内容")


class ChatRagSource(BaseModel):
    chunk_id: str
    document_id: str
    heading_path: str | None
    content: str
    score: float


class ChatMessageResponse(BaseModel):
    session_id: str
    user_message_id: int
    assistant_message_id: int
    assistant_content: str
    intent: str | None = None
    order_no: str | None = None
    ticket_no: str | None = None
    sources: list[ChatRagSource] = []
