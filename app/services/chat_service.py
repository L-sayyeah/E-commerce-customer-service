from uuid import uuid4

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatSession, ChatMessage
from app.schemas.chat import CreateChatSessionRequest, SendMessageRequest
from app.core.request_context import get_trace_id

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # 创建会话
    async def create_session(self, request: CreateChatSessionRequest) -> ChatSession:
        session = ChatSession(
            session_id=str(uuid4()),
            user_id=request.user_id,
            channel=request.channel,
            status="active"
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        logger.info(f"创建会话成功：{session.session_id}")
        return session

    # 发送消息
    async def send_message(self, request: SendMessageRequest) -> tuple[ChatMessage, ChatMessage]:
        stmt = select(ChatSession).where(ChatSession.session_id == request.session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if not session:
            logger.error(f"会话不存在：{request.session_id}")
            raise ValueError("会话不存在")

        trace_id = get_trace_id()
        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            content=request.content,
            message_type="text",
            trace_id=trace_id
        )
        self.db.add(user_message)
        await self.db.flush()

        assistant_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content="已收到你的问题，后续会有回复",
            message_type="text",
            trace_id=trace_id
        )
        self.db.add(assistant_message)

        await self.db.commit()
        await self.db.refresh(user_message)
        await self.db.refresh(assistant_message)

        logger.info(
            f"会话保存对话消息：{request.session_id}, trace_id={trace_id}, user_message_id={user_message.id}, "
            f"assistant_message_id={assistant_message.id}")

        return user_message, assistant_message
