"""create profile, food catalog, and food logs

Revision ID: 20260715_0003
Revises: 20260715_0002
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0003"
down_revision: str | None = "20260715_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("gender", sa.String(length=10), nullable=False),
        sa.Column("age", sa.SmallInteger(), nullable=False),
        sa.Column("height_cm", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("activity_level", sa.String(length=20), nullable=False),
        sa.Column("goal", sa.String(length=10), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')",
            name=op.f("ck_user_profiles_activity_level_allowed"),
        ),
        sa.CheckConstraint(
            "age BETWEEN 13 AND 120",
            name=op.f("ck_user_profiles_age_range"),
        ),
        sa.CheckConstraint(
            "gender IN ('male', 'female')",
            name=op.f("ck_user_profiles_gender_allowed"),
        ),
        sa.CheckConstraint(
            "goal IN ('lose', 'maintain', 'gain')",
            name=op.f("ck_user_profiles_goal_allowed"),
        ),
        sa.CheckConstraint(
            "height_cm BETWEEN 80 AND 250",
            name=op.f("ck_user_profiles_height_range"),
        ),
        sa.CheckConstraint(
            "weight_kg BETWEEN 20 AND 400",
            name=op.f("ck_user_profiles_weight_range"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profiles")),
    )

    op.create_table(
        "food_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("serving_unit", sa.String(length=30), nullable=True),
        sa.Column("serving_weight_g", sa.Numeric(precision=8, scale=3), nullable=True),
        sa.Column("kcal_per_100g", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("protein_per_100g", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("fat_per_100g", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("carbs_per_100g", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("sugar_per_100g", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("sodium_per_100g", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("caffeine_per_100g", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "kcal_per_100g >= 0 AND protein_per_100g >= 0 AND fat_per_100g >= 0 "
            "AND carbs_per_100g >= 0 AND sugar_per_100g >= 0 "
            "AND sodium_per_100g >= 0 AND caffeine_per_100g >= 0",
            name=op.f("ck_food_items_nutrition_nonnegative"),
        ),
        sa.CheckConstraint(
            "serving_weight_g IS NULL OR serving_weight_g > 0",
            name=op.f("ck_food_items_serving_weight_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_food_items_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_items")),
    )
    op.create_index("ix_food_items_name", "food_items", ["name"], unique=False)
    op.create_index(
        "ix_food_items_owner_name",
        "food_items",
        ["owner_user_id", "name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_food_items_owner_user_id"),
        "food_items",
        ["owner_user_id"],
        unique=False,
    )

    op.create_table(
        "food_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(length=12), nullable=False),
        sa.Column("food_item_id", sa.Uuid(), nullable=True),
        sa.Column("custom_name", sa.String(length=200), nullable=True),
        sa.Column("amount", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=False),
        sa.Column("kcal", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("protein", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("fat", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("carbs", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("sugar", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("sodium", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("caffeine", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("amount > 0", name=op.f("ck_food_logs_amount_positive")),
        sa.CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'drink')",
            name=op.f("ck_food_logs_meal_type_allowed"),
        ),
        sa.CheckConstraint(
            "kcal >= 0 AND protein >= 0 AND fat >= 0 AND carbs >= 0 "
            "AND sugar >= 0 AND sodium >= 0 AND caffeine >= 0",
            name=op.f("ck_food_logs_nutrition_nonnegative"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_food_logs_version_positive")),
        sa.ForeignKeyConstraint(
            ["food_item_id"],
            ["food_items.id"],
            name=op.f("fk_food_logs_food_item_id_food_items"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_food_logs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_logs")),
        sa.UniqueConstraint("user_id", "client_id", name="uq_food_logs_user_client"),
    )
    op.create_index(
        op.f("ix_food_logs_user_id"),
        "food_logs",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_food_logs_user_date",
        "food_logs",
        ["user_id", "log_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_food_logs_user_date", table_name="food_logs")
    op.drop_index(op.f("ix_food_logs_user_id"), table_name="food_logs")
    op.drop_table("food_logs")
    op.drop_index(op.f("ix_food_items_owner_user_id"), table_name="food_items")
    op.drop_index("ix_food_items_owner_name", table_name="food_items")
    op.drop_index("ix_food_items_name", table_name="food_items")
    op.drop_table("food_items")
    op.drop_table("user_profiles")
