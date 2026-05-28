import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import success_response, ApiResponse
from app.schemas.chat import ChatSessionResponse, CreateChatSessionRequest, ChatMessageResponse, SendMessageRequest
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
        user_message, assistant_message = await service.send_message(request)
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
        assistant_content=assistant_message.content
    )
    return success_response(data)
