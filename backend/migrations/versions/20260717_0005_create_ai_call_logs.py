"""create AI call logs

Revision ID: 20260717_0005
Revises: 20260715_0004
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260717_0005"
down_revision: str | None = "20260715_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_call_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('success', 'fallback', 'failed')",
            name=op.f("ck_ai_call_logs_status_allowed"),
        ),
        sa.CheckConstraint(
            "latency_ms >= 0 AND attempt_count >= 1",
            name=op.f("ck_ai_call_logs_timing_nonnegative"),
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0",
            name=op.f("ck_ai_call_logs_tokens_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_call_logs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_call_logs")),
    )
    op.create_index(
        "ix_ai_call_logs_user_created",
        "ai_call_logs",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_call_logs_user_created", table_name="ai_call_logs")
    op.drop_table("ai_call_logs")
