from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Numeric, String, Uuid, text
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
        CheckConstraint(
            "nutrition_basis_unit IN ('g', 'ml', 'serving')",
            name="nutrition_basis_unit_allowed",
        ),
        CheckConstraint("nutrition_basis_quantity > 0", name="nutrition_basis_positive"),
        CheckConstraint(
            "density_g_per_ml IS NULL OR density_g_per_ml > 0",
            name="density_positive",
        ),
        Index("ix_food_items_name", "name"),
        Index("ix_food_items_owner_name", "owner_user_id", "name"),
        Index("ix_food_items_normalized_name", "normalized_name"),
        Index(
            "ix_food_items_normalized_name_trgm",
            "normalized_name",
            postgresql_using="gin",
            postgresql_ops={"normalized_name": "gin_trgm_ops"},
        ),
        Index(
            "uq_food_items_global_catalog_key",
            "catalog_key",
            unique=True,
            postgresql_where=text("owner_user_id IS NULL AND catalog_key IS NOT NULL"),
        ),
        Index(
            "uq_food_items_private_catalog_key",
            "owner_user_id",
            "catalog_key",
            unique=True,
            postgresql_where=text("owner_user_id IS NOT NULL AND catalog_key IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    brand: Mapped[str | None] = mapped_column(String(120))
    brand_normalized: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(80))
    catalog_key: Mapped[str | None] = mapped_column(String(180))
    current_revision: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="legacy-v1",
        server_default=text("'legacy-v1'"),
    )
    source_reference: Mapped[str | None] = mapped_column(String(500))
    nutrition_basis_unit: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default="g",
        server_default=text("'g'"),
    )
    nutrition_basis_quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 3),
        nullable=False,
        default=Decimal("100"),
        server_default=text("100"),
    )
    density_g_per_ml: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    nutrition_complete: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
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
