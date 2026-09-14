from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FoodItemRevision(Base):
    __tablename__ = "food_item_revisions"
    __table_args__ = (
        UniqueConstraint("food_item_id", "revision", name="uq_food_revisions_item_revision"),
        CheckConstraint(
            "basis_unit IN ('g', 'ml', 'serving')",
            name="basis_unit_allowed",
        ),
        CheckConstraint("basis_quantity > 0", name="basis_quantity_positive"),
        CheckConstraint(
            "serving_weight_g IS NULL OR serving_weight_g > 0",
            name="serving_weight_positive",
        ),
        CheckConstraint(
            "density_g_per_ml IS NULL OR density_g_per_ml > 0",
            name="density_positive",
        ),
        CheckConstraint(
            "kcal >= 0 AND protein_g >= 0 AND fat_g >= 0 AND carbs_g >= 0 "
            "AND sugar_g >= 0 AND sodium_mg >= 0 AND caffeine_mg >= 0",
            name="nutrition_nonnegative",
        ),
        Index("ix_food_revisions_item_created", "food_item_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    food_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("food_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(80))
    basis_unit: Mapped[str] = mapped_column(String(12), nullable=False)
    basis_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    serving_unit: Mapped[str | None] = mapped_column(String(30))
    serving_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    density_g_per_ml: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    nutrition_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    kcal: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    carbs_g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    sugar_g: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    sodium_mg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    caffeine_mg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FoodAlias(Base):
    __tablename__ = "food_aliases"
    __table_args__ = (
        UniqueConstraint(
            "food_item_id",
            "normalized_alias",
            name="uq_food_aliases_item_normalized",
        ),
        Index("ix_food_aliases_normalized", "normalized_alias"),
        Index(
            "ix_food_aliases_normalized_trgm",
            "normalized_alias",
            postgresql_using="gin",
            postgresql_ops={"normalized_alias": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    food_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("food_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
