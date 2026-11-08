from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateTicketRequest(BaseModel):
    user_id: str | None = None
    order_no: str | None = Field(default=None, min_length=1, max_length=64)
    session_id: str | None = Field(default=None, min_length=1, max_length=64)
    issue_type: Literal["refund", "exchange", "resend", "logistics", "product", "other"]
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    priority: str = "medium"
    source: str = "api"


class TicketResponse(BaseModel):
    id: int
    ticket_no: str
    user_id: str | None
    order_no: str | None
    session_id: str | None
    issue_type: str
    title: str
    description: str
    priority: str
    status: str
    source: str
    trace_id: str | None
    created_at: datetime


class UpdateTicketStatusRequest(BaseModel):
    status: str = Field(description="open/in_progress/resolved/closed")
    operator_id: str | None = Field(default=None, description="操作人ID")
    remark: str | None = Field(default=None, description="备注")


class TicketLogResponse(BaseModel):
    id: int
    ticket_no: str
    action: str
    from_status: str | None
    to_status: str | None
    operator_id: str | None
    remark: str | None
    trace_id: str | None
    created_at: datetime
