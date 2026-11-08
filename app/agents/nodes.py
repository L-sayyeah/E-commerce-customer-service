import copy
import json
import time

from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context_builder import ContextBuilder
from app.agents.dialogue_state import policy_query
from app.agents.guardrails import ResponseGuard
from app.agents.intent_classifier import IntentClassifier
from app.agents.state import AgentState
from app.core.config import Principal
from app.core.request_context import get_trace_id
from app.models.agent_log import AgentNodeLog
from app.services.adaptive_retrieval import chat_evidence_budget, ticket_policy_queries
from app.agents.tools import AgentTools


class AgentNodes:
    def __init__(self, db: AsyncSession, principal: Principal):
        self.db = db
        self.tools = AgentTools(db, principal)

    async def _classify_intent(self, state: AgentState) -> AgentState:
        dialogue = state.get("dialogue") or {}
        question = state["user_message"]
        policy_question = any(word in question for word in ("政策", "规则", "到账", "多久"))
        if dialogue.get("clarification_prompt"):
            state.update(intent="clarify", intent_reason="ambiguous policy scope", intent_classifier="dst")
            return state
        if dialogue.get("ambiguous_order"):
            state.update(intent="clarify", intent_reason="ambiguous order reference", intent_classifier="dst")
            return state
        if dialogue.get("policy_intent"):
            state.update(intent="rag_qa", intent_reason="policy scope resolved", intent_classifier="dst")
            return state
        if not state.get("ticket_ref") and len(ticket_policy_queries(question)) >= 2 and not any(
            phrase in question for phrase in ("帮我建单", "帮我创建", "帮我提交", "给我建单", "转人工")
        ):
            state.update(
                intent="rag_qa", intent_reason="multiple ticket policy questions", intent_classifier="rule",
            )
            return state
        if state.get("order_no") and any(word in question for word in ("退款", "退货", "换货", "补发", "售后")) and (
            any(word in question for word in ("政策", "规则", "条款"))
            and any(word in question for word in ("同时", "以及", "顺便", "分别", "也想", "并说明"))
        ):
            state.update(
                intent="aftersales_check",
                intent_reason="order eligibility and policy explanation requested",
                intent_classifier="dst",
                policy_context_requested=True,
            )
            return state
        if dialogue.get("follow_up") and state.get("order_no") and not policy_question:
            if any(word in question for word in ("退款", "退货", "补发", "换货", "售后", "还能退")):
                state.update(intent="aftersales_check", intent_reason="order reference resolved", intent_classifier="dst")
                return state
            if any(word in question for word in ("物流", "发货", "签收", "到哪", "状态")):
                state.update(intent="order_query", intent_reason="order reference resolved", intent_classifier="dst")
                return state

        result = await IntentClassifier().classify(question, state.get("recent_messages", []))
        state["intent"] = result["intent"]
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
        question = state["user_message"]
        retrieval_query = state.get("retrieval_query")
        result = await self.tools.rag_answer(
            state=state,
            query=question,
            top_k=chat_evidence_budget(retrieval_query or question),
            retrieval_query=retrieval_query,
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

        reason_text = "；".join(aftersales_result["reasons"])

        state["answer"] = (
            f"订单 {order.order_no} 按当前系统通用规则的初步判断："
            f"{reason_text}。"
        )

        if aftersales_result["requires_human_review"]:
            state["answer"] += " 如需人工跟进，请确认后提交工单。"

        return state

    async def aftersales_node(self, state: AgentState) -> AgentState:
        return await self._run_with_log(
            "aftersales_node",
            state,
            self._aftersales_node
        )

    async def _ticket_node(self, state: AgentState) -> AgentState:
        if state.get("intent") != "ticket_query":
            state["answer"] = "可以通过提交工单申请人工跟进。请确认订单及问题后提交。"
            return state

        ticket_no = state.get("ticket_ref")
        if not ticket_no:
            state["answer"] = "请提供要查询的工单号。"
            return state

        ticket = await self.tools.query_ticket(state, ticket_no)
        if ticket is None:
            state["answer"] = "没有查询到该工单，请确认工单号。"
        else:
            state["ticket_no"] = ticket["ticket_no"]
            state["answer"] = f'工单 {ticket["ticket_no"]} 当前状态为 {ticket["status"]}。'
        return state

    async def ticket_node(self, state: AgentState) -> AgentState:
        return await self._run_with_log(
            "ticket_node",
            state,
            self._ticket_node
        )

    async def _clarify_node(self, state: AgentState) -> AgentState:
        dialogue = state.get("dialogue") or {}
        if dialogue.get("clarification_prompt"):
            state["answer"] = dialogue["clarification_prompt"]
        elif dialogue.get("ambiguous_order"):
            state["answer"] = "请确认您指的是哪一笔订单，或直接提供订单号。"
        else:
            state["answer"] = "请提供更多信息，例如订单号或您想咨询的问题，我会继续帮您处理。"
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

        if state.get("intent") in {"order_query", "aftersales_check", "ticket_query", "ticket_create", "clarify"}:
            return state
        if not answer:
            state["guard_checked"] = False
            state["guard_safe"] = None
            state["guard_reason"] = "answer is empty"
            return state

        guard = ResponseGuard()
        result = await guard.check(
            user_message=(state.get("dialogue") or {}).get("clarified_question") or state["user_message"],
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

    async def build_context_node(self, state: AgentState) -> dict:
        builder = ContextBuilder()

        question = state.get("user_message", "")
        dialogue = state.get("dialogue") or {}
        context = builder.build(
            user_message=question,
            recent_messages=[item for item in state.get("recent_messages", []) if item.get("role") == "user"],
        )
        inherited = bool(dialogue.get("order_inherited"))
        region = dialogue.get("region")
        updates = {
            **context,
            "order_no": dialogue.get("order_no"),
            "recent_order_no": dialogue.get("order_no"),
            "ticket_ref": dialogue.get("ticket_no"),
            "is_follow_up": bool(dialogue.get("follow_up")),
            "memory_used": inherited or bool(region),
            "memory_reason": "引用已解析的历史槽位" if inherited or region else None,
            "context_summary": "订单指代有歧义" if dialogue.get("ambiguous_order") else (
                "使用本轮和历史中的用户槽位" if inherited or region else "使用本轮信息"
            ),
            "retrieval_query": policy_query(question, dialogue)[1],
        }

        actions = list(state.get("actions") or [])
        actions.append(
            {
                "tool": "context_builder",
                "status": "success",
                "summary": updates["context_summary"],
                "metadata": {
                    "memory_used": updates["memory_used"],
                    "recent_order_no": updates["recent_order_no"],
                    "last_intent": context["last_intent"],
                },
            }
        )
        updates["actions"] = actions

        return updates

    async def human_review_node(self, state: AgentState) -> AgentState:
        if not state.get("human_review_required"):
            return {}

        review_result = interrupt(
            {
                "type": "human_review",
                "reason": state.get("human_review_reason"),
                "order_no": state.get("order_no"),
                "intent": state.get("intent"),
                "answer": state.get("answer"),
                "actions": state.get("actions", []),
            }
        )

        return {
            "human_review_result": review_result,
            "actions": [
                *state.get("actions", []),
                {
                    "tool": "human_review",
                    "status": "approved" if review_result.get("approved") else "rejected",
                    "summary": review_result.get("review_comment"),
                    "metadata": review_result,
                },
            ],
        }