from uuid import UUID

from sqlalchemy import ForeignKey, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AiCredential(TimestampMixin, Base):
    __tablename__ = "ai_credentials"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="openai")
    encrypted_api_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_last_four: Mapped[str] = mapped_column(String(4), nullable=False)
