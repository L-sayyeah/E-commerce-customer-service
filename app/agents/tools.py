from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ticket import CreateTicketRequest
from app.services.aftersales_rule_service import AftersalesRuleService
from app.services.knoewledge_service import KnowledgeService
from app.services.order_service import OrderService
from app.services.rag_service import RagService
from app.services.ticket_service import TicketService


def ensure_actions(state: dict) -> list[dict[str, Any]]:
    if "actions" not in state or state["actions"] is None:
        state["actions"] = []
    return state["actions"]


def add_action(
        state: dict,
        tool: str,
        status: str,
        summary: str,
        metadata: dict[str, Any] | None = None
) -> None:
    ensure_actions(state).append(
        {
            "tool": tool,
            "status": status,
            "summary": summary,
            "metadata": metadata or {}
        }
    )


def serialize_order(order) -> dict[str, Any]:
    return {
        "order_no": order.order_no,
        "user_id": order.user_id,
        "platform": order.platform,
        "country": order.country,
        "currency": order.currency,
        "total_amount": str(order.total_amount)
        if isinstance(order.total_amount, Decimal)
        else order.total_amount,
        "payment_status": order.payment_status,
        "fulfillment_status": order.fulfillment_status,
        "logistics_status": order.logistics_status,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
    }

class AgentTools:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def rag_answer(self, state: dict, query: str, top_k: int = 5) -> dict:
        try:
            knowledge_service = KnowledgeService(self.db)
            rag_service = RagService(knowledge_service, self.db)

            result = await rag_service.answer(query=query, top_k=top_k)

            add_action(
                state,
                tool="rag_answer",
                status="success",
                summary=f"generated RAG answer with {len(result.get('sources', []))} sources",
                metadata={
                    "source_count": len(result.get("sources", [])),
                    "retrieval_mode": result.get("retrieval_mode"),
                },
            )
            return result
        except Exception as exc:
            add_action(
                state,
                tool="rag_answer",
                status="failed",
                summary=str(exc),
            )
            raise

    async def query_order(self, state: dict, order_no: str,):
        try:
            service = OrderService(self.db)
            order = await service.get_by_order_no(order_no)

            if order is None:
                add_action(
                    state,
                    tool="query_order",
                    status="not_found",
                    summary=f"order not found: {order_no}",
                    metadata={"order_no": order_no},
                )
                return None

            serialized = serialize_order(order)

            add_action(
                state,
                tool="query_order",
                status="success",
                summary=f"found order {order_no}",
                metadata={
                    "order_no": order_no,
                    "logistics_status": order.logistics_status,
                    "payment_status": order.payment_status,
                },
            )
            return order, serialized

        except Exception as exc:
            add_action(
                state,
                tool="query_order",
                status="failed",
                summary=str(exc),
                metadata={"order_no": order_no},
            )
            raise

    async def check_aftersales(self, state: dict, order) -> dict:
        try:
            service = AftersalesRuleService()
            result = service.evaluate(order)

            add_action(
                state,
                tool="check_aftersales",
                status="success",
                summary=(
                    "checked aftersales eligibility, "
                    f"requires_human_review={result['requires_human_review']}"
                ),
                metadata={
                    "order_no": order.order_no,
                    "refundable": result["refundable"],
                    "exchangeable": result["exchangeable"],
                    "resendable": result["resendable"],
                    "requires_human_review": result["requires_human_review"],
                },
            )

            return result

        except Exception as exc:
            add_action(
                state,
                tool="check_aftersales",
                status="failed",
                summary=str(exc),
                metadata={"order_no": getattr(order, "order_no", None)},
            )
            raise

    async def create_or_get_ticket(self, state: dict, request: CreateTicketRequest, dedupe_by_order_issue: bool = True):
        try:
            service = TicketService(self.db)

            if dedupe_by_order_issue and request.order_no:
                existing_ticket = await service.get_open_ticket_by_order_and_issue(
                    order_no=request.order_no,
                    issue_type=request.issue_type,
                )

                if existing_ticket is not None:
                    add_action(
                        state,
                        tool="create_or_get_ticket",
                        status="reused",
                        summary=f"reused open ticket {existing_ticket.ticket_no}",
                        metadata={
                            "ticket_no": existing_ticket.ticket_no,
                            "order_no": request.order_no,
                            "issue_type": request.issue_type,
                        },
                    )
                    return existing_ticket

            ticket = await service.create_ticket(request)

            add_action(
                state,
                tool="create_or_get_ticket",
                status="created",
                summary=f"created ticket {ticket.ticket_no}",
                metadata={
                    "ticket_no": ticket.ticket_no,
                    "order_no": ticket.order_no,
                    "issue_type": ticket.issue_type,
                },
            )

            return ticket

        except Exception as exc:
            add_action(
                state,
                tool="create_or_get_ticket",
                status="failed",
                summary=str(exc),
                metadata={
                    "order_no": request.order_no,
                    "issue_type": request.issue_type,
                },
            )
            raise
