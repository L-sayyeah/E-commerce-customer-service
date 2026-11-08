from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Principal
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
    def __init__(self, db: AsyncSession, principal: Principal):
        self.db = db
        self.principal = principal

    async def rag_answer(
        self, state: dict, query: str, top_k: int = 5, *, retrieval_query: str | None = None,
    ) -> dict:
        try:
            knowledge_service = KnowledgeService(self.db)
            rag_service = RagService(knowledge_service, self.db)

            result = await rag_service.answer(query=query, top_k=top_k, retrieval_query=retrieval_query)

            add_action(
                state,
                tool="rag_answer",
                status="success",
                summary=f"generated RAG answer with {len(result.get('sources', []))} sources",
                metadata={
                    "source_count": len(result.get("sources", [])),
                    "retrieval_mode": result.get("retrieval_mode"),
                    "retrieval_trace": result.get("retrieval_trace"),
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
            service = OrderService(self.db, self.principal)
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

            if result.get("requires_human_review"):
                state["human_review_required"] = True
                state["human_review_reason"] = result.get("reasons")

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

    async def query_ticket(self, state: dict, ticket_no: str) -> dict | None:
        ticket = await TicketService(self.db, self.principal).get_by_ticket_no(ticket_no)
        if ticket is None:
            add_action(state, "query_ticket", "not_found", "Ticket not found")
            return None
        add_action(state, "query_ticket", "success", "Ticket status retrieved")
        return {"ticket_no": ticket.ticket_no, "status": ticket.status}
