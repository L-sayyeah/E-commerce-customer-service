from typing import TypedDict, Any


class AgentState(TypedDict, total=False):
    session_id: str
    user_id: str | None
    user_message: str

    intent: str
    intent_reason: str | None
    intent_classifier: str | None
    order_no: str | None

    order: dict[str, Any] | None
    aftersales_result: dict[str, Any] | None
    ticket_no: str | None

    answer: str
    sources: list[dict[str, Any]]
    error: str | None
