from langgraph.constants import END
from langgraph.graph import StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import AgentNodes
from app.agents.state import AgentState


def build_agent_graph(db: AsyncSession):
    nodes = AgentNodes(db)

    workflow = StateGraph(AgentState)
    workflow.add_node("classify_intent", nodes.classify_intent)
    workflow.add_node("rag_node", nodes.rag_node)
    workflow.add_node("order_node", nodes.order_node)
    workflow.add_node("aftersales_node", nodes.aftersales_node)
    workflow.add_node("ticket_node", nodes.ticket_node)
    workflow.add_node("clarify_node", nodes.clarify_node)

    workflow.set_entry_point("classify_intent")
    workflow.add_conditional_edges(
        "classify_intent",
        route_by_intent, {
            "rag_qa": "rag_node",
            "order_query": "order_node",
            "aftersales_check": "aftersales_node",
            "ticket_create": "ticket_node",
            "clarify": "clarify_node",
        }
    )

    workflow.add_edge("rag_node", END)
    workflow.add_edge("order_node", END)
    workflow.add_edge("aftersales_node", END)
    workflow.add_edge("ticket_node", END)
    workflow.add_edge("clarify_node", END)

    return workflow.compile()


def route_by_intent(state: AgentState) -> str:
    return state.get("intent", "clarify")
