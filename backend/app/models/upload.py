from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Upload(TimestampMixin, Base):
    __tablename__ = "uploads"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed', 'delete_pending', 'deleted')",
            name="status_allowed",
        ),
        CheckConstraint("declared_size > 0", name="declared_size_positive"),
        CheckConstraint(
            "verified_size IS NULL OR verified_size > 0", name="verified_size_positive"
        ),
        CheckConstraint("width IS NULL OR width > 0", name="width_positive"),
        CheckConstraint("height IS NULL OR height > 0", name="height_positive"),
        CheckConstraint("delete_attempt_count >= 0", name="delete_attempt_count_nonnegative"),
        Index("ix_uploads_user_created", "user_id", "created_at"),
        Index("ix_uploads_cleanup", "status", "expires_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    declared_size: Mapped[int] = mapped_column(Integer, nullable=False)
    declared_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_size: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    sealed_object_key: Mapped[str | None] = mapped_column(String(500), unique=True)
    sealed_object_version: Mapped[str | None] = mapped_column(String(80))
    upload_url_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delete_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_error_code: Mapped[str | None] = mapped_column(String(60))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
