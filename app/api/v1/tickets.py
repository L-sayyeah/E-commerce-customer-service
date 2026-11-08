from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AdminPrincipal, CurrentPrincipal
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import ApiResponse, success_response
from app.models.ticket import Ticket
from app.schemas.ticket import TicketResponse, CreateTicketRequest, UpdateTicketStatusRequest, TicketLogResponse
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/tickets", tags=["tickets"])


# 创建工单响应模型
def build_ticket_response(ticket: Ticket) -> TicketResponse:
    return TicketResponse(
        id=ticket.id,
        ticket_no=ticket.ticket_no,
        user_id=ticket.user_id,
        order_no=ticket.order_no,
        session_id=ticket.session_id,
        issue_type=ticket.issue_type,
        title=ticket.title,
        description=ticket.description,
        priority=ticket.priority,
        status=ticket.status,
        source=ticket.source,
        trace_id=ticket.trace_id,
        created_at=ticket.created_at,
    )


def build_ticket_log_response(log) -> TicketLogResponse:
    return TicketLogResponse(
        id=log.id,
        ticket_no=log.ticket_no,
        action=log.action,
        from_status=log.from_status,
        to_status=log.to_status,
        operator_id=log.operator_id,
        remark=log.remark,
        trace_id=log.trace_id,
        created_at=log.created_at,
    )


@router.post("", response_model=ApiResponse[TicketResponse])
async def create_ticket(
    request: CreateTicketRequest,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")],
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db, principal)
    ticket = await service.create_ticket(request, idempotency_key)
    return success_response(build_ticket_response(ticket))


@router.get("/{ticket_no}", response_model=ApiResponse[TicketResponse])
async def get_ticket(ticket_no: str, principal: CurrentPrincipal, db: AsyncSession = Depends(get_db)):
    service = TicketService(db, principal)
    ticket = await service.get_by_ticket_no(ticket_no, allow_admin=True)

    if ticket is None:
        raise AppException("Ticket not found", code=404, status_code=404)

    return success_response(build_ticket_response(ticket))


@router.patch("/{ticket_no}/status", response_model=ApiResponse[TicketResponse])
async def update_ticket_status(ticket_no: str, request: UpdateTicketStatusRequest, principal: AdminPrincipal, db: AsyncSession = Depends(get_db)):
    allowed_statuses = {"open", "in_progress", "resolved", "closed"}

    if request.status not in allowed_statuses:
        raise AppException(
            message="Invalid status",
            code=400,
            status_code=400,
        )

    service = TicketService(db, principal)
    ticket = await service.update_status(
        ticket_no=ticket_no,
        status=request.status,
        remark=request.remark
    )

    if ticket is None:
        raise AppException("Ticket not found", code=404, status_code=404)

    return success_response(build_ticket_response(ticket))


@router.get("/{ticket_no}/logs", response_model=ApiResponse[list[TicketLogResponse]])
async def list_ticket_logs(ticket_no: str, principal: CurrentPrincipal, db: AsyncSession = Depends(get_db)):
    service = TicketService(db, principal)
    logs = await service.list_logs(ticket_no)
    return success_response([build_ticket_log_response(log) for log in logs])