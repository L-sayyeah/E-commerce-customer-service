from collections.abc import AsyncGenerator
from uuid import uuid4

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import build_agent_graph
from app.agents.dialogue_state import (
    DialogueState, ORDER_COUNTRIES, POLICY_SCOPE_CONFIRMATION, needs_verified_policy_order,
    pending_policy_question, policy_query, resolve_policy_scope,
)
from app.agents.state import new_turn_state
from app.models.chat import ChatSession, ChatMessage
from app.schemas.chat import CreateChatSessionRequest, SendMessageRequest
from app.core.config import Principal
from app.core.request_context import get_trace_id
from app.services.adaptive_retrieval import chat_evidence_budget
from app.services.knoewledge_service import KnowledgeService
from app.services.order_service import OrderService
from app.services.rag_service import RagService
from app.services.session_access import require_owned_session

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, db: AsyncSession, principal: Principal):
        self.db = db
        self.principal = principal

    # 创建会话
    async def create_session(self, request: CreateChatSessionRequest) -> ChatSession:
        session = ChatSession(
            session_id=str(uuid4()),
            user_id=self.principal.user_id,
            owner_verified=True,
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
        session = await require_owned_session(self.db, self.principal, request.session_id)

        session_db_id = session.id
        user_message, state = await self._prepare_turn(session, request.content)
        graph = build_agent_graph(self.db, self.principal)
        result = await graph.ainvoke(state, config=self._thread_config(session))
        assistant = await self._save_assistant(
            session_db_id, user_message, result["answer"],
            clarification=bool(result["dialogue"].get("clarification_prompt")),
        )
        return user_message, assistant, result

    async def _prepare_turn(self, session: ChatSession, text: str):
        recent_messages = await self.get_recent_messages(session.id)
        dialogue = await self._build_dialogue(session.id, text, recent_messages)
        message = ChatMessage(
            session_id=session.id, role="user", content=text,
            message_type="text", trace_id=get_trace_id(),
        )
        self.db.add(message)
        await self.db.flush()
        return message, new_turn_state(
            session.session_id, self.principal.user_id, text, recent_messages, dialogue,
        )

    async def _build_dialogue(self, session_id: int, text: str, recent_messages: list[dict]) -> dict:
        # Replay only user turns so model output cannot write dialogue slots.
        stmt = select(ChatMessage.content).where(
            ChatMessage.session_id == session_id, ChatMessage.role == "user",
        ).order_by(ChatMessage.id)
        history = (await self.db.execute(stmt)).scalars()
        dialogue = DialogueState()
        for message in history:
            dialogue.apply(message)
        previous_policy_regions = dialogue.policy_regions
        current = dialogue.for_turn(text)
        pending_question = pending_policy_question(recent_messages)

        verified_region = None
        if dialogue.active_order and needs_verified_policy_order(text, pending_question):
            order = await OrderService(self.db, self.principal).get_by_order_no(dialogue.active_order)
            if order is not None:
                verified_region = ORDER_COUNTRIES.get(order.country.strip().upper())

        return resolve_policy_scope(current, text, previous_policy_regions, verified_region, pending_question)

    async def _save_assistant(
        self, session_db_id: int, user_message: ChatMessage, answer: str, *, clarification: bool = False,
    ):
        assistant = ChatMessage(
            session_id=session_db_id, role="assistant", content=answer,
            message_type=POLICY_SCOPE_CONFIRMATION if clarification else "text",
            trace_id=get_trace_id(),
        )
        self.db.add(assistant)
        await self.db.commit()
        await self.db.refresh(user_message)
        await self.db.refresh(assistant)
        return assistant

    @staticmethod
    def _thread_config(session: ChatSession) -> dict:
        return {"configurable": {"thread_id": str(session.id), "checkpoint_ns": ""}}

    async def stream_message(self, request: SendMessageRequest, session: ChatSession) -> AsyncGenerator[dict, None]:
        trace_id = get_trace_id()

        user_message, state = await self._prepare_turn(session, request.content)
        dialogue = state["dialogue"]
        clarification = dialogue.get("clarification_prompt")
        if clarification:
            assistant = await self._save_assistant(session.id, user_message, clarification, clarification=True)
            yield {"type": "token", "content": clarification}
            yield {"type": "done", "user_message_id": user_message.id,
                   "assistant_message_id": assistant.id, "sources": []}
            return

        question, retrieval_query = policy_query(request.content, dialogue)
        knowledge_service = KnowledgeService(self.db)
        rag_service = RagService(knowledge_service, self.db)

        answer_parts: list[str] = []
        sources: list[dict] = []

        async for event in rag_service.stream_answer(
            query=question,
            top_k=chat_evidence_budget(retrieval_query or question),
            retrieval_query=retrieval_query,
        ):
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
                assistant_message = await self._save_assistant(session.id, user_message, final_answer)

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
                "message_type": message.message_type,
                "create_at": message.created_at.isoformat() if message.created_at else None,
            }
            for message in messages
        ]

    async def stream_agent_message(self, request: SendMessageRequest, session: ChatSession) -> AsyncGenerator[dict, None]:
        session_db_id = session.id
        user_message, state = await self._prepare_turn(session, request.content)
        graph = build_agent_graph(self.db, self.principal)
        intent_sent = False
        result = state

        async for snapshot in graph.astream(state, config=self._thread_config(session), stream_mode="values"):
            result = snapshot
            if snapshot.get("intent") and not intent_sent:
                yield {
                    "type": "intent",
                    "intent": snapshot["intent"],
                    "order_no": snapshot.get("order_no"),
                    "reason": snapshot.get("intent_reason"),
                    "classifier": snapshot.get("intent_classifier"),
                }
                intent_sent = True

        assistant = await self._save_assistant(
            session_db_id, user_message, result["answer"],
            clarification=bool(result["dialogue"].get("clarification_prompt")),
        )
        metadata = {
            "user_message_id": user_message.id,
            "assistant_message_id": assistant.id,
            "intent": result["intent"],
            "intent_reason": result.get("intent_reason"),
            "intent_classifier": result.get("intent_classifier"),
            "actions": result.get("actions", []),
            "order_no": result.get("order_no"),
            "ticket_no": result.get("ticket_no"),
            "sources": result.get("sources", []),
        }
        if result["intent"] == "rag_qa":
            yield {"type": "sources", "sources": metadata["sources"]}
            yield {"type": "token", "content": assistant.content}
            yield {"type": "done", **metadata}
        else:
            yield {"type": "final", "answer": assistant.content, **metadata}
