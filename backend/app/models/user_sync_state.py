from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserSyncState(Base):
    __tablename__ = "user_sync_state"
    __table_args__ = (
        CheckConstraint("last_seq >= 0", name="last_seq_nonnegative"),
        CheckConstraint(
            "minimum_valid_after >= 0 AND minimum_valid_after <= last_seq",
            name="valid_retention_boundary",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    epoch: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4, nullable=False)
    last_seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"))
    minimum_valid_after: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0")
    )
