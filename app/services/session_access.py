from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Principal
from app.core.exceptions import AppException
from app.models.chat import ChatSession


async def require_owned_session(
    db: AsyncSession, principal: Principal, session_id: str,
) -> ChatSession:
    stmt = select(ChatSession).where(
        ChatSession.session_id == session_id,
        ChatSession.user_id == principal.user_id,
        ChatSession.owner_verified.is_(True),
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None or session.user_id != principal.user_id:
        raise AppException("Chat session not found", code=404, status_code=404)
    return session
