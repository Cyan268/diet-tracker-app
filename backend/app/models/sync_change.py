from uuid import UUID

from sqlalchemy import JSON, BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SyncChange(TimestampMixin, Base):
    __tablename__ = "sync_changes"
    __table_args__ = (
        CheckConstraint("operation IN ('upsert', 'delete')", name="operation_allowed"),
        Index("ix_sync_changes_user_cursor", "user_id", "id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    aggregate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operation: Mapped[str] = mapped_column(String(10), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
