from uuid import uuid4

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import get_trace_id
from app.models.ticket import Ticket
from app.models.ticket_log import TicketLog
from app.schemas.ticket import CreateTicketRequest

logger = logging.getLogger(__name__)


class TicketService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_ticket(self, request: CreateTicketRequest) -> Ticket:
        trace_id = get_trace_id()

        ticket = Ticket(
            ticket_no=f"TK{uuid4().hex[:16].upper()}",
            user_id=request.user_id,
            order_no=request.order_no,
            session_id=request.session_id,
            issue_type=request.issue_type,
            title=request.title,
            description=request.description,
            priority=request.priority,
            status="open",
            source=request.source,
            trace_id=trace_id,
        )

        self.db.add(ticket)
        await self.db.flush()

        ticket_log = TicketLog(
            ticket_no=ticket.ticket_no,
            action="active",
            from_status=None,
            to_status=ticket.status,
            operator_id=None,
            remark="创建工单",
            trace_id=trace_id,
        )
        self.db.add(ticket_log)

        await self.db.commit()
        await self.db.refresh(ticket)

        logger.info(f"Create ticket | trace_id={trace_id} | ticket_no={ticket.ticket_no} | order_no={request.order_no}")

        return ticket

    async def get_by_ticket_no(self, ticket_no: str) -> Ticket | None:
        stmt = select(Ticket).where(Ticket.ticket_no == ticket_no)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_open_ticket_by_order_and_issue(self, order_no: str, issue_type: str) -> Ticket | None:
        stmt = select(Ticket).where(
            Ticket.order_no == order_no,
            Ticket.issue_type == issue_type,
            Ticket.status.in_(["open", "in_progress"])
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
            self,
            ticket_no: str,
            status: str,
            operator_id: str | None = None,
            remark: str | None = None,
    ) -> Ticket | None:
        stmt = select(Ticket).where(Ticket.ticket_no == ticket_no)
        result = await self.db.execute(stmt)
        ticket = result.scalar_one_or_none()

        if ticket is None:
            return None

        old_status = ticket.status
        ticket.status = status

        ticket_log = TicketLog(
            ticket_no=ticket.ticket_no,
            action="status_change",
            from_status=old_status,
            to_status=status,
            operator_id=operator_id,
            remark=remark,
            trace_id=get_trace_id(),
        )
        self.db.add(ticket_log)

        await self.db.commit()
        await self.db.refresh(ticket)

        logger.info(f"Update ticket status | trace_id={get_trace_id()} | ticket_no={ticket_no} | from_status={old_status} | to_status={status}")

        return ticket

    async def list_logs(self, ticket_no: str) -> list[TicketLog]:
        stmt = select(TicketLog).where(TicketLog.ticket_no == ticket_no).order_by(TicketLog.id.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
