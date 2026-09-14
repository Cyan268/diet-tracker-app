"""Create durable analysis jobs, drafts, entities, confirmations, and corrections.

Revision ID: 20260907_0010
Revises: 20260831_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0010"
down_revision: str | None = "20260831_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("input_type", sa.String(length=12), nullable=False),
        sa.Column("input_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("input_key_version", sa.Integer(), nullable=False),
        sa.Column("input_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("result_schema_version", sa.String(length=40), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=60), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint("input_type IN ('text', 'image')", name="input_type_allowed"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'retry_wait', 'succeeded', 'failed', "
            "'unknown', 'cancelled')",
            name="status_allowed",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        sa.CheckConstraint("input_key_version >= 1", name="input_key_version_positive"),
        sa.CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="lease_fields_consistent",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "client_request_id",
            name="uq_analysis_jobs_user_client_request",
        ),
    )
    op.create_index(
        "ix_analysis_jobs_claim",
        "analysis_jobs",
        ["status", "next_attempt_at", "created_at", "id"],
    )
    op.create_index(
        "ix_analysis_jobs_user_created",
        "analysis_jobs",
        ["user_id", "created_at"],
    )

    op.create_table(
        "analysis_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("result_schema_version", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('review', 'confirmed', 'expired', 'cancelled')",
            name="status_allowed",
        ),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_analysis_drafts_job"),
    )
    op.create_index(
        "ix_analysis_drafts_user_created",
        "analysis_drafts",
        ["user_id", "created_at"],
    )

    op.create_table(
        "analysis_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("raw_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=False),
        sa.Column("meal_type", sa.String(length=12), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("matched_food_id", sa.Uuid(), nullable=True),
        sa.Column("catalog_revision", sa.String(length=80), nullable=True),
        sa.Column("candidates", sa.JSON(), server_default="[]", nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("position >= 0", name="position_nonnegative"),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'drink')",
            name="meal_type_allowed",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        sa.ForeignKeyConstraint(["draft_id"], ["analysis_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_food_id"], ["food_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "draft_id",
            "position",
            name="uq_analysis_entities_draft_position",
        ),
    )
    op.create_index(
        "ix_analysis_entities_draft",
        "analysis_entities",
        ["draft_id", "position"],
    )

    op.create_table(
        "analysis_confirmations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("client_confirmation_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("confirmed_draft_version", sa.Integer(), nullable=False),
        sa.Column("log_ids", sa.JSON(), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("confirmed_draft_version >= 1", name="draft_version_positive"),
        sa.ForeignKeyConstraint(["draft_id"], ["analysis_drafts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_id", name="uq_analysis_confirmations_draft"),
        sa.UniqueConstraint(
            "user_id",
            "client_confirmation_id",
            name="uq_analysis_confirmations_user_client_confirmation",
        ),
    )
    op.create_index(
        "ix_analysis_confirmations_user_created",
        "analysis_confirmations",
        ["user_id", "created_at"],
    )

    op.create_table(
        "analysis_corrections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("confirmation_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("field_name", sa.String(length=40), nullable=False),
        sa.Column("before_value", sa.JSON(), nullable=True),
        sa.Column("after_value", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "field_name IN ('entity_added', 'entity_removed', 'name', 'amount', 'unit', "
            "'meal_type', 'food_match')",
            name="field_name_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["confirmation_id"], ["analysis_confirmations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["analysis_entities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_corrections_confirmation",
        "analysis_corrections",
        ["confirmation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_corrections_confirmation",
        table_name="analysis_corrections",
    )
    op.drop_table("analysis_corrections")
    op.drop_index(
        "ix_analysis_confirmations_user_created",
        table_name="analysis_confirmations",
    )
    op.drop_table("analysis_confirmations")
    op.drop_index("ix_analysis_entities_draft", table_name="analysis_entities")
    op.drop_table("analysis_entities")
    op.drop_index("ix_analysis_drafts_user_created", table_name="analysis_drafts")
    op.drop_table("analysis_drafts")
    op.drop_index("ix_analysis_jobs_user_created", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_claim", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
