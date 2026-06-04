# app/models/rag_log.py
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RagLog(Base, TimestampMixin):
    __tablename__ = "rag_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    trace_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="链路追踪ID",
    )
    query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="用户问题",
    )
    answer: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="最终回答",
    )
    sources_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="召回来源JSON",
    )
    top_k: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="召回数量",
    )
    model_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="模型名称",
    )
    retrival_mode: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="检索模式：vector/hybrid"
    )
    rerank_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="是否启用 rerank",
    )
    rerank_model: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Rerank 模型名称",
    )
    rerank_status: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Rerank 状态：disabled/success/failed_fallback",
    )
    rerank_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Rerank 错误信息",
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