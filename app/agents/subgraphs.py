"""Task messages between the supervisor and independently scoped domain graphs."""

from collections.abc import Awaitable, Callable
from typing import TypedDict

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.agents.state import AgentState


class TaskEnvelope(TypedDict, total=False):
    kind: str
    question: str
    session_id: str
    retrieval_query: str | None
    order_no: str | None
    ticket_no: str | None


class TaskResult(TypedDict, total=False):
    answer: str
    order: dict | None
    aftersales_result: dict | None
    ticket_no: str | None
    sources: list[dict]
    actions: list[dict]
    human_review_required: bool
    human_review_reason: list[str] | None
    intent: str


class ChildState(TypedDict, total=False):
    task: TaskEnvelope
    result: TaskResult


def build_delegate(handler: Callable[[AgentState], Awaitable[AgentState]]):
    async def execute(state: ChildState) -> ChildState:
        task = state["task"]
        result = await handler({
            "user_message": task["question"],
            "session_id": task["session_id"],
            "retrieval_query": task.get("retrieval_query"),
            "order_no": task.get("order_no"),
            "ticket_ref": task.get("ticket_no"),
            "intent": task["kind"],
            "actions": [],
        })
        return {"result": {key: value for key, value in result.items()
                           if key in TaskResult.__annotations__}}

    graph = StateGraph(ChildState)
    graph.add_node("execute_domain_task", execute)
    graph.add_edge(START, "execute_domain_task")
    graph.add_edge("execute_domain_task", END)
    child = graph.compile(checkpointer=False)

    async def delegate(state: AgentState) -> AgentState:
        output = await child.ainvoke({"task": {
            "kind": state["intent"],
            "question": (state.get("dialogue") or {}).get("clarified_question") or state["user_message"],
            "session_id": state["session_id"],
            "retrieval_query": state.get("retrieval_query"),
            "order_no": state.get("order_no"),
            "ticket_no": state.get("ticket_ref"),
        }})
        result = output["result"]
        return {**result, "actions": [*state.get("actions", []), *result.get("actions", [])]}

    return delegate
