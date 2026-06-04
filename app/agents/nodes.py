import copy
import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.guardrails import ResponseGuard
from app.agents.intent_classifier import IntentClassifier, extract_order_no, ORDER_NO_PATTERN
from app.agents.state import AgentState
from app.core.request_context import get_trace_id
from app.models.agent_log import AgentNodeLog
from app.schemas.ticket import CreateTicketRequest
from app.agents.tools import AgentTools


class AgentNodes:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.tools = AgentTools(db)

    async def _classify_intent(self, state: AgentState) -> AgentState:
        if state.get("intent"):
            return state

        classifier = IntentClassifier()
        result = await classifier.classify(state["user_message"], state.get("recent_messages", []))

        state["intent"] = result["intent"]

        if result.get("order_no"):
            state["order_no"] = result["order_no"]

        state["intent_reason"] = result.get("reason")
        state["intent_classifier"] = result["classifier"]

        return state

    async def classify_intent(self, state: AgentState) -> AgentState:
        return await self._run_with_log(
            "classify_intent",
            state,
            self._classify_intent
        )

    async def _rag_node(self, state: AgentState) -> AgentState:
        result = await self.tools.rag_answer(
            state=state,
            query=state["user_message"],
            top_k=5
        )

        state["answer"] = result["answer"]
        state["sources"] = result["sources"]
        return state

    async def rag_node(self, state: AgentState) -> AgentState:
        return await self._run_with_log(
            "rag_node",
            state,
            self._rag_node
        )

    async def _order_node(self, state: AgentState) -> AgentState:
        order_no = state.get("order_no")

        if not order_no:
            state["intent"] = "clarify"
            state["answer"] = "请提供您的订单号， 我可以帮您查询订单状态。"
            return state

        result = await self.tools.query_order(
            state=state,
            order_no=order_no
        )

        if result is None:
            state["answer"] = f"没有查询到订单{order_no}， 请检查订单号是否正确。"
            return state
        order, serialize_order = result

        state["order"] = serialize_order
        state["answer"] = (
            f"已查询到订单 {order.order_no}："
            f"支付状态为 {order.payment_status}，"
            f"履约状态为 {order.fulfillment_status}，"
            f"物流状态为 {order.logistics_status}。"
        )
        return state

    async def order_node(self, state: AgentState) -> AgentState:
        return await self._run_with_log(
            "order_node",
            state,
            self._order_node
        )

    async def _aftersales_node(self, state: AgentState) -> AgentState:
        order_no = state.get("order_no")

        if not order_no:
            state["answer"] = "请提供您的订单号，我可以帮您判断是否支持退款、换货或补发。"
            return state

        order_result = await self.tools.query_order(
            state=state,
            order_no=order_no
        )

        if order_result is None:
            state["answer"] = f"没有查询到订单 {order_no}，请确认订单号是否正确。"
            return state

        order, serialized_order = order_result

        aftersales_result = await self.tools.check_aftersales(
            state=state,
            order=order,
        )

        state["order"] = serialized_order
        state["aftersales_result"] = aftersales_result

        ticket_no = None
        if aftersales_result["requires_human_review"]:
            issue_type = "resend" if aftersales_result["resendable"] else "other"

            ticket = await self.tools.create_or_get_ticket(
                state=state,
                request=CreateTicketRequest(
                    user_id=order.user_id,
                    order_no=order.order_no,
                    session_id=state.get("session_id"),
                    issue_type=issue_type,
                    title=f"订单 {order.order_no} 需要人工审核",
                    description="Agent 售后判断结果需要人工审核。原因：" + "；".join(aftersales_result["reasons"]),
                    priority="medium",
                    source="agent",
                ),
                dedupe_by_order_issue=True,
            )
            ticket_no = ticket.ticket_no
            state["ticket_no"] = ticket_no

        reason_text = "；".join(aftersales_result["reasons"])

        state["answer"] = (
            f"订单 {order.order_no} 的售后判断结果："
            f"{reason_text}。"
        )

        if ticket_no:
            state["answer"] += f" 已为您创建或关联工单 {ticket_no}，后续会由人工继续处理。"

        return state

    async def aftersales_node(self, state: AgentState) -> AgentState:
        return await self._run_with_log(
            "aftersales_node",
            state,
            self._aftersales_node
        )

    async def _ticket_node(self, state: AgentState) -> AgentState:
        ticket = await self.tools.create_or_get_ticket(
            state=state,
            request=CreateTicketRequest(
                user_id=state.get("user_id"),
                order_no=state.get("order_no"),
                session_id=state.get("session_id"),
                issue_type="other",
                title="用户请求人工客服介入",
                description=state["user_message"],
                priority="medium",
                source="agent",
            ),
            dedupe_by_order_issue=False,
        )

        state["ticket_no"] = ticket.ticket_no
        state["answer"] = f"已为您创建工单 {ticket.ticket_no}，人工客服会继续跟进处理。"
        return state

    async def ticket_node(self, state: AgentState) -> AgentState:
        return await self._run_with_log(
            "ticket_node",
            state,
            self._ticket_node
        )

    async def _clarify_node(self, state: AgentState) -> AgentState:
        state["answer"] = "请提供更多信息，例如订单号或您想咨询的问题，我会继续帮您处理"
        return state

    async def clarify_node(self, state: AgentState) -> AgentState:
        return await self._run_with_log(
            "clarify_node",
            state,
            self._clarify_node
        )

    async def _log_node(
            self,
            node_name: str,
            input_state: AgentState,
            output_state: AgentState | None,
            duration_ms: int,
            status: str = "success",
            error_message: str | None = None
    ) -> None:
        node_log = AgentNodeLog(
            trace_id=get_trace_id(),
            session_id=input_state.get("session_id"),
            node_name=node_name,
            intent=(output_state or input_state).get("intent"),
            input_json=json.dumps(input_state, ensure_ascii=False, default=str),
            output_json=json.dumps(output_state, ensure_ascii=False, default=str)
            if output_state is not None
            else None,
            duration_ms=duration_ms,
            status=status,
            error_message=error_message,
        )

        self.db.add(node_log)
        await self.db.commit()

    async def _run_with_log(
            self,
            node_name: str,
            state: AgentState,
            handler
    ) -> AgentState:
        input_state = copy.deepcopy(state)
        start_time = time.perf_counter()

        try:
            output_state = await handler(state)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            await self._log_node(
                node_name=node_name,
                input_state=input_state,
                output_state=output_state,
                duration_ms=duration_ms,
                status="success"
            )

            return output_state

        except Exception as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            await self._log_node(
                node_name=node_name,
                input_state=input_state,
                output_state=None,
                duration_ms=duration_ms,
                status="failed",
                error_message=str(exc)
            )
            raise

    async def response_guard_node(self, state: AgentState) -> AgentState:
        return await self._run_with_log(
            "response_guard_node",
            state,
            self._response_guard_node
        )

    async def _response_guard_node(self, state: AgentState) -> AgentState:
        answer = state.get("answer")

        if not answer:
            state["guard_checked"] = False
            state["guard_safe"] = None
            state["guard_reason"] = "answer is empty"
            return state

        guard = ResponseGuard()
        result = await guard.check(
            user_message=state["user_message"],
            answer=answer,
            intent=state.get("intent"),
        )

        state["guard_checked"] = True
        state["guard_safe"] = result["safe"]
        state["guard_reason"] = result.get("reason")

        if not result["safe"] and result.get("rewritten_answer"):
            state["original_answer"] = answer
            state["answer"] = result["rewritten_answer"]

        return state
