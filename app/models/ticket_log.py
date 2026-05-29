# backend/app/models/ticket_log.py
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TicketLog(Base, TimestampMixin):
    __tablename__ = "ticket_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    ticket_no: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="工单号",
    )
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="操作类型：create/status_change/comment/assign",
    )
    from_status: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="原状态",
    )
    to_status: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="新状态",
    )
    operator_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="操作人ID",
    )
    remark: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="备注",
    )
    trace_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="链路追踪ID",
    )
