from typing import TypedDict, Any


class AgentState(TypedDict, total=False):
    session_id: str
    user_id: str | None
    user_message: str
    recent_messages: list[dict[str, Any]]
    dialogue: dict[str, Any]
    retrieval_query: str | None
    ticket_ref: str | None
    policy_context_requested: bool

    intent: str
    intent_reason: str | None
    intent_classifier: str | None
    order_no: str | None

    order: dict[str, Any] | None
    aftersales_result: dict[str, Any] | None
    ticket_no: str | None

    answer: str
    sources: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    error: str | None

    guard_checked: bool
    guard_safe: bool | None
    guard_reason: str | None
    original_answer: str | None

    # 上下文信息
    recent_order_no: str | None
    recent_ticket_id: int | None
    last_intent: str | None
    is_follow_up: bool
    memory_used: bool
    memory_reason: str | None
    context_summary: str | None

    human_review_required: bool
    human_review_reason: list[str] | None
    human_review_payload: dict | None
    human_review_result: dict | None


def new_turn_state(
    session_id: str,
    user_id: str,
    user_message: str,
    recent_messages: list[dict[str, Any]],
    dialogue: dict[str, Any] | None = None,
) -> AgentState:
    """Overwrite run-local checkpoint channels when starting a new user turn."""
    return {
        "session_id": session_id,
        "user_id": user_id,
        "user_message": user_message,
        "recent_messages": recent_messages,
        "dialogue": dialogue or {},
        "retrieval_query": None,
        "ticket_ref": None,
        "policy_context_requested": False,
        "intent": "",
        "intent_reason": None,
        "intent_classifier": None,
        "order_no": None,
        "order": None,
        "aftersales_result": None,
        "ticket_no": None,
        "answer": "",
        "sources": [],
        "actions": [],
        "error": None,
        "guard_checked": False,
        "guard_safe": None,
        "guard_reason": None,
        "original_answer": None,
        "recent_order_no": None,
        "recent_ticket_id": None,
        "last_intent": None,
        "is_follow_up": False,
        "memory_used": False,
        "memory_reason": None,
        "context_summary": None,
        "human_review_required": False,
        "human_review_reason": None,
        "human_review_payload": None,
        "human_review_result": None,
    }
