from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.schemas.admin import RagLogResponse, AgentRunLogResponse, AgentNodeLogResponse, TraceLogDetailResponse, \
    ChatMessageLogResponse
from app.services.admin_log_service import AdminLogService

router = APIRouter(prefix="/admin", tags=["admin"])


def build_rag_log_response(log) -> RagLogResponse:
    return RagLogResponse(
        id=log.id,
        trace_id=log.trace_id,
        query=log.query,
        answer=log.answer,
        sources_json=log.sources_json,
        top_k=log.top_k,
        model_name=log.model_name,
        status=log.status,
        error_message=log.error_message,
        created_at=log.created_at,
    )


def build_agent_run_log_response(log) -> AgentRunLogResponse:
    return AgentRunLogResponse(
        id=log.id,
        trace_id=log.trace_id,
        session_id=log.session_id,
        user_message=log.user_message,
        intent=log.intent,
        order_no=log.order_no,
        ticket_no=log.ticket_no,
        answer=log.answer,
        state_json=log.state_json,
        status=log.status,
        error_message=log.error_message,
        created_at=log.created_at,
    )


def build_agent_node_log_response(log) -> AgentNodeLogResponse:
    return AgentNodeLogResponse(
        id=log.id,
        trace_id=log.trace_id,
        session_id=log.session_id,
        node_name=log.node_name,
        intent=log.intent,
        input_json=log.input_json,
        output_json=log.output_json,
        duration_ms=log.duration_ms,
        status=log.status,
        error_message=log.error_message,
        created_at=log.created_at,
    )


@router.get("/logs/rag", response_model=ApiResponse[list[RagLogResponse]])
async def list_rag_logs(
        trace_id: str | None = None,
        status: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        db: AsyncSession = Depends(get_db)
):
    service = AdminLogService(db)
    logs = await service.list_rag_logs(
        trace_id=trace_id,
        status=status,
        limit=limit
    )

    return success_response([build_rag_log_response(log) for log in logs])


@router.get("/logs/agent-runs", response_model=ApiResponse[list[AgentRunLogResponse]])
async def list_agent_run_logs(
        trace_id: str | None = None,
        intent: str | None = None,
        status: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        db: AsyncSession = Depends(get_db)
):
    service = AdminLogService(db)
    logs = await service.list_agent_run_logs(
        trace_id=trace_id,
        intent=intent,
        status=status,
        limit=limit
    )

    return success_response([build_agent_run_log_response(log) for log in logs])


@router.get("/logs/agent-nodes", response_model=ApiResponse[list[AgentNodeLogResponse]])
async def list_agent_node_logs(
        trace_id: str | None = None,
        node_name: str | None = None,
        intent: str | None = None,
        status: str | None = None,
        limit: int = Query(default=20, ge=1, le=200),
        db: AsyncSession = Depends(get_db)
):
    service = AdminLogService(db)
    logs = await service.list_agent_node_logs(
        trace_id=trace_id,
        node_name=node_name,
        intent=intent,
        status=status,
        limit=limit
    )

    return success_response([build_agent_node_log_response(log) for log in logs])


@router.get("/logs/traces/{trace_id}", response_model=ApiResponse[TraceLogDetailResponse])
async def get_trace_detail(trace_id: str, db: AsyncSession = Depends(get_db)):
    service = AdminLogService(db)
    detail = await service.get_trace_detail(trace_id)

    data = TraceLogDetailResponse(
        trace_id=trace_id,
        chat_messages=[
            ChatMessageLogResponse(
                id=message.id,
                role=message.role,
                content=message.content,
                message_type=message.message_type,
                trace_id=message.trace_id,
                created_at=message.created_at,
            )
            for message in detail["chat_messages"]
        ],
        rag_logs=[
            build_rag_log_response(log)
            for log in detail["rag_logs"]
        ],
        agent_run_logs=[
            build_agent_run_log_response(log)
            for log in detail["agent_run_logs"]
        ],
        agent_node_logs=[
            build_agent_node_log_response(log)
            for log in detail["agent_node_logs"]
        ]
    )

    return success_response(data)
