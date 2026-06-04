from collections.abc import AsyncGenerator
from uuid import uuid4

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import build_agent_graph
from app.agents.intent_classifier import IntentClassifier
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

        recent_messages = await self.get_recent_messages(session.id, limit=6)

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
        config = {
            "configurable": {
                "thread_id": str(session.id),
                "checkpoint_ns": ""
            }
        }
        agent_result = await graph.ainvoke(
            {
                "session_id": request.session_id,
                "user_id": session.user_id,
                "user_message": request.content,
                "recent_messages": recent_messages,
                "sources": []
            },
            config=config
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

    async def get_recent_messages(self, session_db_id: int, limit: int = 6) -> list[dict]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_db_id)
            .order_by(ChatMessage.id.desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)

        messages = list(result.scalars().all())
        messages.reverse()

        return [
            {
                "role": message.role,
                "content": message.content,
                "create_at": message.created_at.isoformat() if message.created_at else None,
            }
            for message in messages
        ]

    async def stream_agent_message(self, request: SendMessageRequest) -> AsyncGenerator[dict, None]:
        trace_id = get_trace_id()

        # 获取会话信息
        stmt = select(ChatSession).where(ChatSession.session_id == request.session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if session is None:
            raise ValueError("Chat session not found")

        # 获取近期消息
        recent_messages = await self.get_recent_messages(session_db_id=session.id, limit=6)

        # 保存用户消息
        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            content=request.content,
            message_type="text",
            trace_id=trace_id
        )
        self.db.add(user_message)
        await self.db.flush()

        # 意图分析
        classifier = IntentClassifier()
        classify_result = await classifier.classify(user_message=request.content, recent_messages=recent_messages)

        intent = classify_result["intent"]
        order_no = classify_result.get("order_no")

        yield {
            "type": "intent",
            "intent": intent,
            "order_no": order_no,
            "reason": classify_result.get("reason"),
            "classifier": classify_result.get("classifier")
        }

        # 意图为rag，调用rag服务
        if intent =="rag_qa":
            knowledge_service = KnowledgeService(self.db)
            rag_service = RagService(knowledge_service, self.db)

            answer_parts: list[str] =[]
            sources: list[dict] = []

            async for event in rag_service.stream_answer(query=request.content, top_k=5):
                event_type = event["type"]

                # rag文档
                if event_type == "sources":
                    sources = event["sources"]
                    yield {
                        "type": "sources",
                        "sources": sources,
                    }

                # rag回答
                elif event_type == "token":
                    content = event["content"]
                    answer_parts.append(content)
                    yield {
                        "type": "token",
                        "content": content,
                    }

                # rag回答结束
                elif event_type == "done":
                    final_answer = "".join(answer_parts)

                    assistant_message = ChatMessage(
                        session_id=session.id,
                        role="assistant",
                        content=final_answer,
                        message_type="text",
                        trace_id=trace_id,
                    )
                    self.db.add(assistant_message)

                    await self.db.commit()
                    await self.db.refresh(user_message)
                    await self.db.refresh(assistant_message)
                    yield {
                        "type": "done",
                        "user_message_id": user_message.id,
                        "assistant_message_id": assistant_message.id,
                        "intent": intent,
                        "intent_reason": classify_result.get("reason"),
                        "intent_classifier": classify_result.get("classifier"),
                        "actions": [
                            {
                                "tool": "rag_answer",
                                "status": "success",
                                "summary": f"streamed RAG answer with {len(sources)} sources",
                                "metadata": {"source_count": len(sources)},
                            }
                        ],
                        "order_no": order_no,
                        "sources": sources,
                    }

            return

        graph = build_agent_graph(self.db)

        agent_result = await graph.ainvoke(
            {
                "session_id": request.session_id,
                "user_id": session.user_id,
                "user_message": request.content,
                "recent_messages": recent_messages,
                "intent": intent,
                "intent_reason": classify_result.get("reason"),
                "intent_classifier": classify_result.get("classifier"),
                "order_no": order_no,
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

        yield {
            "type": "final",
            "user_message_id": user_message.id,
            "assistant_message_id": assistant_message.id,
            "intent": agent_result.get("intent"),
            "intent_reason": agent_result.get("intent_reason"),
            "intent_classifier": agent_result.get("intent_classifier"),
            "actions": agent_result.get("actions", []),
            "order_no": agent_result.get("order_no"),
            "ticket_no": agent_result.get("ticket_no"),
            "answer": assistant_message.content,
            "sources": agent_result.get("sources") or []
        }