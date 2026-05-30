from collections.abc import AsyncGenerator
from uuid import uuid4

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import build_agent_graph
from app.models.chat import ChatSession, ChatMessage
from app.schemas.chat import CreateChatSessionRequest, SendMessageRequest
from app.core.request_context import get_trace_id
from app.services.knoewledge_service import KnowledgeService
from app.services.rag_service import RagService

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
    async def send_message(self, request: SendMessageRequest) -> tuple[ChatMessage, ChatMessage, dict]:
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

        graph = build_agent_graph(self.db)
        agent_result = await graph.ainvoke(
            {
                "session_id": request.session_id,
                "user_id": session.user_id,
                "user_message": request.content,
                "sources": []
            }
        )

        assistant_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=agent_result.get("answer", "抱歉，我暂时无法处理这个问题，请稍后再试。"),
            message_type="text",
            trace_id=trace_id
        )
        self.db.add(assistant_message)

        await self.db.commit()
        await self.db.refresh(user_message)
        await self.db.refresh(assistant_message)

        logger.info(
            f"Saved agent chat message：{request.session_id}, trace_id={trace_id}, user_message_id={user_message.id}, "
            f"assistant_message_id={assistant_message.id} | intent={agent_result.get('intent')}")

        return user_message, assistant_message, agent_result

    async def stream_message(self, request: SendMessageRequest) -> AsyncGenerator[dict, None]:
        trace_id = get_trace_id()

        stmt = select(ChatSession).where(ChatSession.session_id == request.session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if session is None:
            raise ValueError("Chat session not found")

        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            content=request.content,
            message_type="text",
            trace_id=trace_id,
        )
        self.db.add(user_message)
        await self.db.flush()

        knowledge_service = KnowledgeService(self.db)
        rag_service = RagService(knowledge_service, self.db)

        answer_parts: list[str] = []
        sources: list[dict] = []

        async for event in rag_service.stream_answer(query=request.content, top_k=5):
            event_type = event["type"]

            if event_type == "sources":
                sources = event["sources"]
                yield {
                    "type": event_type,
                    "sources": sources
                }

            elif event_type == "token":
                answer_parts.append(event["content"])
                yield {
                    "type": event_type,
                    "content": event["content"]
                }

            elif event_type == "done":
                final_answer = "".join(answer_parts)
                assistant_message = ChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=final_answer,
                    message_type="text",
                    trace_id=trace_id
                )
                self.db.add(assistant_message)

                await self.db.commit()
                await self.db.refresh(user_message)
                await self.db.refresh(assistant_message)

                logger.info(f"Saved streaming chat message | trace_id={trace_id} | session_id={request.session_id}"
                            f" | user_message_id={user_message.id} | assistant_message_id={assistant_message.id}")

                yield {
                    "type": "done",
                    "user_message_id": user_message.id,
                    "assistant_message_id": assistant_message.id,
                    "sources": sources
                }