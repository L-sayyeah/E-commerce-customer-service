import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from app.agents.graph import build_agent_graph
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.request_context import get_trace_id
from app.core.response import success_response, ApiResponse
from app.models.agent_log import AgentRunLog
from app.schemas.chat import ChatSessionResponse, CreateChatSessionRequest, ChatMessageResponse, SendMessageRequest, \
    ChatRagSource
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/sessions", response_model=ApiResponse[ChatSessionResponse])
async def create_chat_session(request: CreateChatSessionRequest, db: AsyncSession = Depends(get_db)):
    service = ChatService(db)
    session = await service.create_session(request)
    data = ChatSessionResponse(
        id=session.id,
        session_id=session.session_id,
        user_id=session.user_id,
        channel=session.channel,
        status=session.status,
        create_at=session.created_at
    )
    return success_response(data)


@router.post("/messages", response_model=ApiResponse[ChatMessageResponse])
async def send_message(request: SendMessageRequest, db: AsyncSession = Depends(get_db)):
    service = ChatService(db)
    try:
        user_message, assistant_message, agent_result = await service.send_message(request)
        sources = agent_result.get("sources") or []
    except ValueError as exc:
        logger.error(f"Error sending message: {exc}")
        raise AppException(
            message=str(exc),
            code=400,
            status_code=400
        )
    data = ChatMessageResponse(
        session_id=request.session_id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        assistant_content=assistant_message.content,
        intent=agent_result.get("intent"),
        order_no=agent_result.get("order_no"),
        ticket_no=agent_result.get("ticket_no"),
        sources=[
            ChatRagSource(
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                heading_path=item["heading_path"],
                content=item["content"],
                score=item["score"]
            )
            for item in sources
        ]
    )
    return success_response(data)


@router.post("/messages/stream")
async def send_message_stream(request: SendMessageRequest, db: AsyncSession = Depends(get_db)):
    service = ChatService(db)

    async def event_generator():
        try:
            async for event in service.stream_message(request):
                event_type = event["type"]

                if event_type == "sources":
                    yield {
                        "event": event_type,
                        "data": json.dumps(
                            {
                                "sources": event["sources"]
                            },
                            ensure_ascii=False
                        )
                    }
                elif event_type == "token":
                    yield {
                        "event": event_type,
                        "data": json.dumps(
                            {
                                "content": event["content"]
                            },
                            ensure_ascii=False
                        )
                    }
                elif event_type == "done":
                    yield {
                        "event": event_type,
                        "data": json.dumps(
                            {
                                "user_message_id": event["user_message_id"],
                                "assistant_message_id": event["assistant_message_id"],
                                "sources": event["sources"]
                            },
                            ensure_ascii=False
                        )
                    }
        except ValueError as exc:
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "message": str(exc)
                    },
                    ensure_ascii=False
                )
            }

    return EventSourceResponse(event_generator())


@router.post("/agent/messages", response_model=ApiResponse[dict])
async def send_agent_message(request: SendMessageRequest, db: AsyncSession = Depends(get_db)):
    graph = build_agent_graph(db)

    try:
        result = await graph.ainvoke(
            {
                "session_id": request.session_id,
                "user_message": request.content,
                "sources": []
            }
        )
        agent_log = AgentRunLog(
            trace_id=get_trace_id(),
            session_id=request.session_id,
            user_message=request.content,
            intent=result.get("intent"),
            order_no=result.get("order_no"),
            ticket_no=result.get("ticket_no"),
            answer=result.get("answer"),
            state_json=json.dumps(result, ensure_ascii=False, default=str),
            status="success",
            error_message=None,
        )
        db.add(agent_log)
        await db.commit()
        return success_response(result)
    except Exception as exc:
        agent_log = AgentRunLog(
            trace_id=get_trace_id(),
            session_id=request.session_id,
            user_message=request.content,
            intent=None,
            order_no=None,
            ticket_no=None,
            answer=None,
            state_json=None,
            status="failed",
            error_message=str(exc),
        )
        db.add(agent_log)
        await db.commit()
        raise