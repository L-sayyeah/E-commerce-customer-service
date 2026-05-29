# backend/app/models/knowledge.py
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# 知识文档
class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    document_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="业务文档ID",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="文档标题",
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        default="manual",
        nullable=False,
        comment="来源类型：manual/upload/url/system",
    )
    source_uri: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="来源地址",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        nullable=False,
        comment="状态：active/inactive/deleted",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="文档版本",
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="文档内容哈希",
    )

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


# 知识文档切片
class KnowledgeChunk(Base, TimestampMixin):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chunk_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="业务切片ID",
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.document_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="业务文档ID",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="切片序号",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="切片文本内容",
    )
    heading_path: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="标题路径",
    )
    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="扩展元数据JSON",
    )
    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="token 数量",
    )
    milvus_vector_id: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
        nullable=True,
        comment="Milvus 向量ID",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        nullable=False,
        comment="状态：active/inactive/deleted",
    )

    document: Mapped["KnowledgeDocument"] = relationship(
        back_populates="chunks",
    )
