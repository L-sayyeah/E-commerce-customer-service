import hashlib
import json
import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Principal
from app.core.exceptions import AppException
from app.core.request_context import get_trace_id
from app.models.ticket import Ticket
from app.models.ticket_log import TicketLog
from app.schemas.ticket import CreateTicketRequest
from app.services.order_service import OrderService
from app.services.session_access import require_owned_session

logger = logging.getLogger(__name__)


class TicketService:
    def __init__(self, db: AsyncSession, principal: Principal):
        self.db = db
        self.principal = principal

    async def create_ticket(self, request: CreateTicketRequest, idempotency_key: str) -> Ticket:
        if request.order_no is not None:
            order = await OrderService(self.db, self.principal).get_by_order_no(request.order_no)
            if order is None:
                raise AppException("Order not found", code=404, status_code=404)
            order_no = order.order_no
        else:
            order_no = None

        if request.session_id is not None:
            session = await require_owned_session(self.db, self.principal, request.session_id)
            session_id = session.session_id
        else:
            session_id = None

        payload = {
            "user_id": self.principal.user_id,
            "order_no": order_no,
            "session_id": session_id,
            "issue_type": request.issue_type,
            "title": request.title,
            "description": request.description,
            "priority": "medium",
            "source": "api",
        }
        request_key = hashlib.sha256(
            json.dumps([self.principal.user_id, idempotency_key]).encode("utf-8")
        ).hexdigest()
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

        existing = await self._find_replay(request_key, request_hash)
        if existing is not None:
            return existing

        trace_id = get_trace_id()
        ticket = Ticket(
            **payload,
            ticket_no=f"TK{uuid4().hex[:16].upper()}",
            status="open",
            trace_id=trace_id,
            request_key=request_key,
            request_hash=request_hash,
        )
        try:
            self.db.add(ticket)
            await self.db.flush()
            await self.db.refresh(ticket, attribute_names=["created_at"])
            self.db.add(TicketLog(
                ticket_no=ticket.ticket_no,
                action="active",
                from_status=None,
                to_status=ticket.status,
                operator_id=self.principal.user_id,
                remark="创建工单",
                trace_id=trace_id,
            ))
            await self.db.commit()
        except IntegrityError:
            # A concurrent insert of the same key wins. Roll back first so the
            # lookup starts a new transaction and can see the committed winner.
            await self.db.rollback()
            existing = await self._find_replay(request_key, request_hash)
            if existing is None:
                raise
            return existing

        logger.info("Created ticket | trace_id=%s | ticket_no=%s", trace_id, ticket.ticket_no)
        return ticket

    async def _find_replay(self, request_key: str, request_hash: str) -> Ticket | None:
        stmt = select(Ticket).where(Ticket.request_key == request_key)
        ticket = (await self.db.execute(stmt)).scalar_one_or_none()
        if ticket is not None and ticket.request_hash != request_hash:
            raise AppException("Idempotency key already used with different parameters", code=409, status_code=409)
        return ticket

    async def get_by_ticket_no(self, ticket_no: str, *, allow_admin: bool = False) -> Ticket | None:
        stmt = select(Ticket).where(Ticket.ticket_no == ticket_no)
        if allow_admin and self.principal.role == "admin":
            return (await self.db.execute(stmt)).scalar_one_or_none()

        stmt = stmt.where(Ticket.user_id == self.principal.user_id)
        ticket = (await self.db.execute(stmt)).scalar_one_or_none()
        if ticket is None or ticket.user_id != self.principal.user_id:
            return None
        if ticket.request_key is None and ticket.order_no is None:
            # Legacy tickets without an order have no independent owner evidence.
            return None
        if ticket.order_no is not None:
            order = await OrderService(self.db, self.principal).get_by_order_no(ticket.order_no)
            if order is None:
                return None
        return ticket

    async def update_status(
            self,
            ticket_no: str,
            status: str,
            remark: str | None = None,
    ) -> Ticket | None:
        if self.principal.role != "admin":
            raise AppException("Administrator privileges required", code=403, status_code=403)
        stmt = select(Ticket).where(Ticket.ticket_no == ticket_no).with_for_update()
        result = await self.db.execute(stmt)
        ticket = result.scalar_one_or_none()

        if ticket is None:
            return None

        old_status = ticket.status
        if old_status == status:
            return ticket
        ticket.status = status

        ticket_log = TicketLog(
            ticket_no=ticket.ticket_no,
            action="status_change",
            from_status=old_status,
            to_status=status,
            operator_id=self.principal.user_id,
            remark=remark,
            trace_id=get_trace_id(),
        )
        self.db.add(ticket_log)

        await self.db.commit()
        await self.db.refresh(ticket)

        logger.info(f"Update ticket status | trace_id={get_trace_id()} | ticket_no={ticket_no} | from_status={old_status} | to_status={status}")

        return ticket

    async def list_logs(self, ticket_no: str) -> list[TicketLog]:
        ticket = await self.get_by_ticket_no(ticket_no, allow_admin=True)
        if ticket is None:
            raise AppException("Ticket not found", code=404, status_code=404)
        stmt = select(TicketLog).where(TicketLog.ticket_no == ticket.ticket_no).order_by(TicketLog.id.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
