from typing import TypedDict, Any


class AgentState(TypedDict, total=False):
    session_id: str
    user_id: str | None
    user_message: str
    recent_messages: list[dict[str, Any]]

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
    human_review_reason: str | None
    human_review_payload: dict | None
    human_review_result: dict | None
