from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FoodItem(TimestampMixin, Base):
    __tablename__ = "food_items"
    __table_args__ = (
        CheckConstraint(
            "kcal_per_100g >= 0 AND protein_per_100g >= 0 AND fat_per_100g >= 0 "
            "AND carbs_per_100g >= 0 AND sugar_per_100g >= 0 "
            "AND sodium_per_100g >= 0 AND caffeine_per_100g >= 0",
            name="nutrition_nonnegative",
        ),
        CheckConstraint(
            "serving_weight_g IS NULL OR serving_weight_g > 0",
            name="serving_weight_positive",
        ),
        Index("ix_food_items_name", "name"),
        Index("ix_food_items_owner_name", "owner_user_id", "name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(80))
    serving_unit: Mapped[str | None] = mapped_column(String(30))
    serving_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    kcal_per_100g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    protein_per_100g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    fat_per_100g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    carbs_per_100g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    sugar_per_100g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    sodium_per_100g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    caffeine_per_100g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="user")
