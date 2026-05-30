from sqlalchemy import String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AgentRunLog(Base, TimestampMixin):
    __tablename__ = "agent_run_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    trace_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="链路追踪ID",
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="会话ID",
    )
    user_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="用户消息",
    )
    intent: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="识别出的意图",
    )
    order_no: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="订单号",
    )
    ticket_no: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="工单号",
    )
    answer: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="最终回答",
    )
    state_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="最终 Agent State JSON",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="success",
        nullable=False,
        comment="状态：success/failed",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息",
    )


class AgentNodeLog(Base, TimestampMixin):
    __tablename__ = "agent_node_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    trace_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="链路追踪ID",
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="会话ID",
    )
    node_name: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="节点名称",
    )
    intent: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="当前意图",
    )
    input_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="节点输入 State JSON",
    )
    output_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="节点输出 State JSON",
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="节点耗时毫秒",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="success",
        nullable=False,
        comment="状态：success/failed",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息",
    )