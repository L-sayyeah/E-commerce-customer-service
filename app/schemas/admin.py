from datetime import datetime

from pydantic import BaseModel


class RagLogResponse(BaseModel):
    id: int
    trace_id: str | None
    query: str
    answer: str | None
    sources_json: str | None
    top_k: int
    model_name: str | None
    rerank_enabled: bool
    rerank_model: str | None
    rerank_status: str | None
    rerank_error: str | None
    retrieval_mode: str | None
    status: str
    error_message: str | None
    created_at: datetime


class AgentRunLogResponse(BaseModel):
    id: int
    trace_id: str | None
    session_id: str | None
    user_message: str
    intent: str | None
    order_no: str | None
    ticket_no: str | None
    answer: str | None
    state_json: str | None
    status: str
    error_message: str | None
    created_at: datetime


class AgentNodeLogResponse(BaseModel):
    id: int
    trace_id: str | None
    session_id: str | None
    node_name: str
    intent: str | None
    input_json: str | None
    output_json: str | None
    duration_ms: int | None
    status: str
    error_message: str | None
    created_at: datetime


class ChatMessageLogResponse(BaseModel):
    id: int
    role: str
    content: str
    message_type: str
    trace_id: str | None
    created_at: datetime


class TraceLogDetailResponse(BaseModel):
    trace_id: str
    chat_messages: list[ChatMessageLogResponse]
    rag_logs: list[RagLogResponse]
    agent_run_logs: list[AgentRunLogResponse]
    agent_node_logs: list[AgentNodeLogResponse]
