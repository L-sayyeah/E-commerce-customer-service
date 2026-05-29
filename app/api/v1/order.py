from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import ApiResponse, success_response
from app.schemas.order import OrderResponse
from app.services.order_service import OrderService
from app.schemas.aftersales import AftersalesEligibilityResponse
from app.services.aftersales_rule_service import AftersalesRuleService
from app.schemas.ticket import CreateTicketRequest
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/orders", tags=["order"])


@router.get("/{order_no}", response_model=ApiResponse[OrderResponse])
async def get_order(order_no: str, db: AsyncSession = Depends(get_db)):
    service = OrderService(db)
    order = await service.get_by_order_no(order_no)

    if order is None:
        raise AppException(
            message="Order not found",
            code=404,
            status_code=404
        )

    data = OrderResponse(
        id=order.id,
        order_no=order.order_no,
        user_id=order.user_id,
        platform=order.platform,
        country=order.country,
        currency=order.currency,
        total_amount=order.total_amount,
        payment_status=order.payment_status,
        fulfillment_status=order.fulfillment_status,
        logistics_status=order.logistics_status,
        shipped_at=order.shipped_at,
        delivered_at=order.delivered_at,
        created_at=order.created_at
    )
    return success_response(data)


@router.get("/{order_no}/aftersales-eligibility", response_model=ApiResponse[AftersalesEligibilityResponse])
async def get_aftersales_eligibility(order_no: str, db: AsyncSession = Depends(get_db)):
    order_service = OrderService(db)
    order = await order_service.get_by_order_no(order_no)
    if order is None:
        raise AppException(
            message="Order not found",
            code=404,
            status_code=404
        )
    rule_service = AftersalesRuleService()
    result = rule_service.evaluate(order)

    ticket_no: str | None = None

    if result["requires_human_review"]:
        issue_type = "resend" if result["resendable"] else "other"
        ticket_service = TicketService(db)

        existing_ticket = await ticket_service.get_open_ticket_by_order_and_issue(
            order_no=order.order_no,
            issue_type=issue_type
        )
        if existing_ticket is not None:
            ticket_no = existing_ticket.ticket_no
        else:
            ticket = await ticket_service.create_ticket(
                CreateTicketRequest(
                    user_id=order.user_id,
                    order_no=order.order_no,
                    session_id=None,
                    issue_type=issue_type,
                    title=f"订单 {order.order_no} 需要人工审核",
                    description="售后规则判断结果需要人工审核。原因："
                                + "；".join(result["reasons"]),
                    priority="medium",
                    source="api",
                )
            )
            ticket_no = ticket.ticket_no

    data = AftersalesEligibilityResponse(
        order_no=order.order_no,
        refundable=result["refundable"],
        exchangeable=result["exchangeable"],
        resendable=result["resendable"],
        requires_human_review=result["requires_human_review"],
        reasons=result["reasons"],
        ticket_no=ticket_no
    )
    return success_response(data)
