from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AssistantConversation(TimestampMixin, Base):
    __tablename__ = "assistant_conversations"
    __table_args__ = (Index("ix_assistant_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False, default="新对话")


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role_allowed"),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        UniqueConstraint("conversation_id", "sequence", name="conversation_sequence"),
        UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="conversation_client_message",
        ),
        Index("ix_assistant_messages_conversation_sequence", "conversation_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_date: Mapped[date | None] = mapped_column(Date)
    provider: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    fallback_used: Mapped[bool | None] = mapped_column(Boolean)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    trace_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ai_call_logs.id", ondelete="SET NULL"),
    )
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    disclaimer: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
