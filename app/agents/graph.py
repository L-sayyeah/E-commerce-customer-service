from langgraph.constants import END, START
from langgraph.graph import StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.checkpoint import get_agent_checkpointer
from app.agents.dialogue_state import ORDER_COUNTRIES
from app.agents.intent_classifier import ORDER_NO_PATTERN
from app.agents.nodes import AgentNodes
from app.agents.state import AgentState
from app.agents.subgraphs import build_delegate
from app.core.config import Principal


def build_agent_graph(db: AsyncSession, principal: Principal):
    nodes = AgentNodes(db, principal)

    workflow = StateGraph(AgentState)
    workflow.add_node("build_context", nodes.build_context_node)
    workflow.add_node("classify_intent", nodes.classify_intent)
    policy_agent = build_delegate(nodes.rag_node)
    workflow.add_node("policy_agent", policy_agent)

    async def explain_policy(state: AgentState) -> AgentState:
        order = state["order"] or {}
        question = ORDER_NO_PATTERN.sub("该订单", state["user_message"].upper())
        country_code = order["country"].strip().upper()
        country = ORDER_COUNTRIES.get(country_code, order["country"])
        if order["logistics_status"] == "lost":
            policy_question = f"{country}跨境订单包裹确认丢失时，补发的适用政策和审核要求是什么？"
        else:
            policy_question = f"{country}地区政策说明（仅解释规则和例外）：{question}"
        try:
            result = await policy_agent({
                "session_id": state["session_id"],
                "intent": "rag_qa",
                "user_message": policy_question,
                "actions": state.get("actions", []),
            })
            # Guard only the generated policy prose. Preserve the order
            # agent's verified facts and deterministic handoff instructions.
            guarded = await nodes.response_guard_node({
                **result, "session_id": state["session_id"],
                "user_message": policy_question, "intent": "rag_qa",
            })
            result["answer"] = guarded["answer"]
        except Exception:
            await db.rollback()
            return {
                "answer": state["answer"] + "\n\n暂时无法核实地区政策，具体资格请人工确认。",
                "actions": [
                    *state.get("actions", []),
                    {"tool": "rag_answer", "status": "failed", "summary": "Policy explanation unavailable"},
                ],
            }
        return {
            "answer": state["answer"] + "\n\n适用政策参考：" + result["answer"],
            "sources": result.get("sources", []),
            "actions": result.get("actions", []),
        }

    workflow.add_node("aftersales_policy", explain_policy)

    async def order_task(state: AgentState) -> AgentState:
        if state["intent"] == "aftersales_check":
            return await nodes.aftersales_node(state)
        return await nodes.order_node(state)

    workflow.add_node("order_agent", build_delegate(order_task))
    workflow.add_node("ticket_agent", build_delegate(nodes.ticket_node))
    workflow.add_node("clarify_node", nodes.clarify_node)
    workflow.add_node("response_guard_node", nodes.response_guard_node)
    workflow.add_node("human_review_node", nodes.human_review_node)

    workflow.add_edge(START, "build_context")
    workflow.add_edge("build_context", "classify_intent")
    workflow.add_conditional_edges(
        "classify_intent",
        route_by_intent, {
            "rag_qa": "policy_agent",
            "order_query": "order_agent",
            "aftersales_check": "order_agent",
            "ticket_create": "ticket_agent",
            "ticket_query": "ticket_agent",
            "clarify": "clarify_node",
        }
    )

    workflow.add_edge("policy_agent", "response_guard_node")
    workflow.add_conditional_edges(
        "order_agent",
        lambda state: "policy" if state.get("policy_context_requested") and state.get("order") else "reply",
        {"policy": "aftersales_policy", "reply": "response_guard_node"},
    )
    workflow.add_edge("aftersales_policy", "response_guard_node")
    workflow.add_edge("ticket_agent", "response_guard_node")
    workflow.add_edge("clarify_node", "response_guard_node")
    workflow.add_edge("human_review_node", "response_guard_node")

    workflow.add_edge("response_guard_node", END)

    return workflow.compile(checkpointer=get_agent_checkpointer())


def route_by_intent(state: AgentState) -> str:
    return state.get("intent", "clarify")
