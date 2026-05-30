from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, Base


# 工单模型
class Ticket(Base, TimestampMixin):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    ticket_no: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="工单号",
    )
    user_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="用户ID",
    )
    order_no: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="关联订单号",
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="关联客服会话ID",
    )
    issue_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="问题类型：refund/exchange/resend/logistics/product/other",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="工单标题",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="工单描述",
    )
    priority: Mapped[str] = mapped_column(
        String(32),
        default="medium",
        nullable=False,
        comment="优先级：low/medium/high/urgent",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="open",
        nullable=False,
        comment="状态：open/in_progress/resolved/closed",
    )
    source: Mapped[str] = mapped_column(
        String(32),
        default="api",
        nullable=False,
        comment="来源：api/agents/admin",
    )
    trace_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="链路追踪ID",
    )
