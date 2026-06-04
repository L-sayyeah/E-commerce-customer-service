# app/models/document_parse_task.py
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DocumentParseTask(Base, TimestampMixin):
    __tablename__ = "document_parse_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    task_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
        comment="MinerU 任务ID",
    )
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="文件名",
    )
    file_url: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="文件URL",
    )
    parse_engine: Mapped[str] = mapped_column(
        String(32),
        default="mineru",
        nullable=False,
        comment="解析引擎",
    )
    model_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="解析模式：pipeline（默认）/ vlm(推荐) / MinerU-HTML",
    )
    language: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="语言",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="submitted",
        nullable=False,
        comment="任务状态",
    )
    full_zip_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="MinerU 解析结果 ZIP 地址",
    )
    result_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="MinerU 原始响应JSON",
    )
    document_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="入库后的知识库文档ID",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息",
    )
