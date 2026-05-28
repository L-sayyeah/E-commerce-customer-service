from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, Base


# 客服会话模型
class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="会话ID"
    )
    user_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="用户ID"
    )
    channel: Mapped[str] = mapped_column(
        String(32),
        default="web",
        nullable=False,
        comment="会话来源渠道"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        nullable=False,
        comment="会话状态： active/closed/human_handoff"
    )
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="会话摘要"
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan"
    )


# 客服消息模型
class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="会话ID"
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="消息角色： user/assistant/system/tool"
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="消息内容"
    )
    message_type: Mapped[str] = mapped_column(
        String(32),
        default="text",
        nullable=False,
        comment="消息类型： text/image/file/order/tool_result"
    )
    trace_id: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        comment="链路追踪ID"
    )
    session: Mapped["ChatSession"] = relationship(
        back_populates="messages"
    )
