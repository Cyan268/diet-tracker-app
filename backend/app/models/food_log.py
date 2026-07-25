from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FoodLog(TimestampMixin, Base):
    __tablename__ = "food_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "client_id", name="uq_food_logs_user_client"),
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'drink')",
            name="meal_type_allowed",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "kcal >= 0 AND protein >= 0 AND fat >= 0 AND carbs >= 0 "
            "AND sugar >= 0 AND sodium >= 0 AND caffeine >= 0",
            name="nutrition_nonnegative",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_food_logs_user_date", "user_id", "log_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(12), nullable=False)
    food_item_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("food_items.id", ondelete="SET NULL"),
    )
    custom_name: Mapped[str | None] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    kcal: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    protein: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    fat: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    carbs: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    sugar: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    sodium: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    caffeine: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
