"""Create immutable food revisions, aliases, and trigram indexes.

Revision ID: 20260908_0011
Revises: 20260907_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0011"
down_revision: str | None = "20260907_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column("food_items", sa.Column("normalized_name", sa.String(200), nullable=True))
    op.add_column("food_items", sa.Column("brand_normalized", sa.String(120), nullable=True))
    op.add_column("food_items", sa.Column("catalog_key", sa.String(180), nullable=True))
    op.add_column(
        "food_items",
        sa.Column(
            "current_revision",
            sa.String(80),
            server_default="legacy-v1",
            nullable=False,
        ),
    )
    op.add_column("food_items", sa.Column("source_reference", sa.String(500), nullable=True))
    op.add_column(
        "food_items",
        sa.Column(
            "nutrition_basis_unit",
            sa.String(12),
            server_default="g",
            nullable=False,
        ),
    )
    op.add_column(
        "food_items",
        sa.Column(
            "nutrition_basis_quantity",
            sa.Numeric(10, 3),
            server_default="100",
            nullable=False,
        ),
    )
    op.add_column("food_items", sa.Column("density_g_per_ml", sa.Numeric(10, 6)))
    op.add_column(
        "food_items",
        sa.Column(
            "nutrition_complete",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE food_items
        SET normalized_name = lower(regexp_replace(name, '[[:space:]（）()·._-]+', '', 'g')),
            brand_normalized = CASE
                WHEN brand IS NULL THEN NULL
                ELSE lower(regexp_replace(brand, '[[:space:]（）()·._-]+', '', 'g'))
            END
        """
    )

    op.add_column("food_logs", sa.Column("display_name", sa.String(200), nullable=True))
    op.add_column("food_logs", sa.Column("nutrition_source", sa.String(60), nullable=True))
    op.add_column("food_logs", sa.Column("catalog_revision", sa.String(80), nullable=True))
    op.add_column(
        "food_logs",
        sa.Column("nutrition_source_reference", sa.String(500), nullable=True),
    )
    op.execute(
        """
        UPDATE food_logs AS log
        SET display_name = food.name,
            nutrition_source = food.source,
            catalog_revision = food.current_revision,
            nutrition_source_reference = food.source_reference
        FROM food_items AS food
        WHERE log.food_item_id = food.id
        """
    )
    op.execute(
        """
        UPDATE food_logs
        SET display_name = custom_name,
            nutrition_source = 'legacy_custom'
        WHERE food_item_id IS NULL
        """
    )
    op.alter_column("food_items", "normalized_name", nullable=False, server_default="")
    op.create_check_constraint(
        op.f("ck_food_items_nutrition_basis_unit_allowed"),
        "food_items",
        "nutrition_basis_unit IN ('g', 'ml', 'serving')",
    )
    op.create_check_constraint(
        op.f("ck_food_items_nutrition_basis_positive"),
        "food_items",
        "nutrition_basis_quantity > 0",
    )
    op.create_check_constraint(
        op.f("ck_food_items_density_positive"),
        "food_items",
        "density_g_per_ml IS NULL OR density_g_per_ml > 0",
    )
    op.create_index("ix_food_items_normalized_name", "food_items", ["normalized_name"])
    op.create_index(
        "ix_food_items_normalized_name_trgm",
        "food_items",
        ["normalized_name"],
        postgresql_using="gin",
        postgresql_ops={"normalized_name": "gin_trgm_ops"},
    )
    op.create_index(
        "uq_food_items_global_catalog_key",
        "food_items",
        ["catalog_key"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NULL AND catalog_key IS NOT NULL"),
    )
    op.create_index(
        "uq_food_items_private_catalog_key",
        "food_items",
        ["owner_user_id", "catalog_key"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NOT NULL AND catalog_key IS NOT NULL"),
    )

    op.create_table(
        "food_item_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("food_item_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("brand", sa.String(120)),
        sa.Column("category", sa.String(80)),
        sa.Column("basis_unit", sa.String(12), nullable=False),
        sa.Column("basis_quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("serving_unit", sa.String(30)),
        sa.Column("serving_weight_g", sa.Numeric(8, 3)),
        sa.Column("density_g_per_ml", sa.Numeric(10, 6)),
        sa.Column("nutrition_complete", sa.Boolean(), nullable=False),
        sa.Column("kcal", sa.Numeric(10, 3), nullable=False),
        sa.Column("protein_g", sa.Numeric(10, 3), nullable=False),
        sa.Column("fat_g", sa.Numeric(10, 3), nullable=False),
        sa.Column("carbs_g", sa.Numeric(10, 3), nullable=False),
        sa.Column("sugar_g", sa.Numeric(10, 3), nullable=False),
        sa.Column("sodium_mg", sa.Numeric(10, 3), nullable=False),
        sa.Column("caffeine_mg", sa.Numeric(10, 3), nullable=False),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("source_reference", sa.String(500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("basis_unit IN ('g', 'ml', 'serving')", name="basis_unit_allowed"),
        sa.CheckConstraint("basis_quantity > 0", name="basis_quantity_positive"),
        sa.CheckConstraint(
            "serving_weight_g IS NULL OR serving_weight_g > 0",
            name="serving_weight_positive",
        ),
        sa.CheckConstraint(
            "density_g_per_ml IS NULL OR density_g_per_ml > 0",
            name="density_positive",
        ),
        sa.CheckConstraint(
            "kcal >= 0 AND protein_g >= 0 AND fat_g >= 0 AND carbs_g >= 0 "
            "AND sugar_g >= 0 AND sodium_mg >= 0 AND caffeine_mg >= 0",
            name="nutrition_nonnegative",
        ),
        sa.ForeignKeyConstraint(["food_item_id"], ["food_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "food_item_id",
            "revision",
            name="uq_food_revisions_item_revision",
        ),
    )
    op.create_index(
        "ix_food_revisions_item_created",
        "food_item_revisions",
        ["food_item_id", "created_at"],
    )

    op.create_table(
        "food_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("food_item_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(200), nullable=False),
        sa.Column("normalized_alias", sa.String(200), nullable=False),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["food_item_id"], ["food_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "food_item_id",
            "normalized_alias",
            name="uq_food_aliases_item_normalized",
        ),
    )
    op.create_index("ix_food_aliases_normalized", "food_aliases", ["normalized_alias"])
    op.create_index(
        "ix_food_aliases_normalized_trgm",
        "food_aliases",
        ["normalized_alias"],
        postgresql_using="gin",
        postgresql_ops={"normalized_alias": "gin_trgm_ops"},
    )

    op.execute(
        """
        INSERT INTO food_item_revisions (
            id, food_item_id, revision, display_name, brand, category,
            basis_unit, basis_quantity, serving_unit, serving_weight_g, density_g_per_ml,
            nutrition_complete,
            kcal, protein_g, fat_g, carbs_g, sugar_g, sodium_mg, caffeine_mg,
            source, source_reference
        )
        SELECT
            gen_random_uuid(), id, current_revision, name, brand, category,
            nutrition_basis_unit, nutrition_basis_quantity, serving_unit,
            serving_weight_g, density_g_per_ml, nutrition_complete,
            kcal_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g,
            sugar_per_100g, sodium_per_100g, caffeine_per_100g,
            source, source_reference
        FROM food_items
        """
    )


def downgrade() -> None:
    for column in (
        "nutrition_source_reference",
        "catalog_revision",
        "nutrition_source",
        "display_name",
    ):
        op.drop_column("food_logs", column)
    op.drop_index("ix_food_aliases_normalized_trgm", table_name="food_aliases")
    op.drop_index("ix_food_aliases_normalized", table_name="food_aliases")
    op.drop_table("food_aliases")
    op.drop_index("ix_food_revisions_item_created", table_name="food_item_revisions")
    op.drop_table("food_item_revisions")
    op.drop_index("uq_food_items_private_catalog_key", table_name="food_items")
    op.drop_index("uq_food_items_global_catalog_key", table_name="food_items")
    op.drop_index("ix_food_items_normalized_name_trgm", table_name="food_items")
    op.drop_index("ix_food_items_normalized_name", table_name="food_items")
    op.drop_constraint(op.f("ck_food_items_density_positive"), "food_items", type_="check")
    op.drop_constraint(op.f("ck_food_items_nutrition_basis_positive"), "food_items", type_="check")
    op.drop_constraint(
        op.f("ck_food_items_nutrition_basis_unit_allowed"), "food_items", type_="check"
    )
    for column in (
        "nutrition_complete",
        "density_g_per_ml",
        "nutrition_basis_quantity",
        "nutrition_basis_unit",
        "source_reference",
        "current_revision",
        "catalog_key",
        "brand_normalized",
        "normalized_name",
    ):
        op.drop_column("food_items", column)
