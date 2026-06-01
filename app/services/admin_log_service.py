from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_log import AgentRunLog, AgentNodeLog
from app.models.chat import ChatMessage
from app.models.rag_log import RagLog


class AdminLogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_rag_logs(
            self,
            trace_id: str | None = None,
            status: str | None = None,
            limit: int = 20
    ) -> list[RagLog]:
        stmt = select(RagLog)

        if trace_id:
            stmt = stmt.where(RagLog.trace_id == trace_id)

        if status:
            stmt = stmt.where(RagLog.status == status)

        stmt = stmt.order_by(RagLog.id.desc()).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_agent_run_logs(
            self,
            trace_id: str | None = None,
            intent: str | None = None,
            status: str | None = None,
            limit: int = 20,
    ) -> list[AgentRunLog]:
        stmt = select(AgentRunLog)

        if trace_id:
            stmt = stmt.where(AgentRunLog.trace_id == trace_id)

        if intent:
            stmt = stmt.where(AgentRunLog.intent == intent)

        if status:
            stmt = stmt.where(AgentRunLog.status == status)

        stmt = stmt.order_by(AgentRunLog.id.desc()).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_agent_node_logs(
            self,
            trace_id: str | None = None,
            node_name: str | None = None,
            intent: str | None = None,
            status: str | None = None,
            limit: int = 50,
    ) -> list[AgentNodeLog]:
        stmt = select(AgentNodeLog)

        if trace_id:
            stmt = stmt.where(AgentNodeLog.trace_id == trace_id)

        if node_name:
            stmt = stmt.where(AgentNodeLog.node_name == node_name)

        if intent:
            stmt = stmt.where(AgentNodeLog.intent == intent)

        if status:
            stmt = stmt.where(AgentNodeLog.status == status)

        stmt = stmt.order_by(AgentNodeLog.id.desc()).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_trace_detail(self, trace_id: str) -> dict:
        chat_stmt = select(ChatMessage).where(ChatMessage.trace_id == trace_id).order_by(ChatMessage.id.asc())
        rag_stmt = select(RagLog).where(RagLog.trace_id == trace_id).order_by(RagLog.id.asc())
        agent_run_stmt = select(AgentRunLog).where(AgentRunLog.trace_id == trace_id).order_by(AgentRunLog.id.asc())
        agent_node_stmt = select(AgentNodeLog).where(AgentNodeLog.trace_id == trace_id).order_by(AgentNodeLog.id.asc())

        chat_result = await self.db.execute(chat_stmt)
        rag_result = await self.db.execute(rag_stmt)
        agent_run_result = await self.db.execute(agent_run_stmt)
        agent_node_result = await self.db.execute(agent_node_stmt)

        return {
            "chat_messages": list(chat_result.scalars().all()),
            "rag_logs": list(rag_result.scalars().all()),
            "agent_run_logs": list(agent_run_result.scalars().all()),
            "agent_node_logs": list(agent_node_result.scalars().all()),
        }
