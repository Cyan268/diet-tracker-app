"""Create durable analysis attempt records.

Revision ID: 20260909_0012
Revises: 20260908_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909_0012"
down_revision: str | None = "20260908_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=False),
        sa.Column("phase", sa.String(24), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("provider_request_id", sa.String(200)),
        sa.Column("error_code", sa.String(60)),
        sa.Column("retryable", sa.Boolean()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("token_usage_source", sa.String(20)),
        sa.Column("estimated_cost_usd", sa.Numeric(14, 8)),
        sa.Column("cost_status", sa.String(12), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("dispatch_started_at", sa.DateTime(timezone=True)),
        sa.Column("response_received_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        sa.CheckConstraint(
            "phase IN ('claimed', 'dispatching', 'response_received', 'finished')",
            name="phase_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'retry_wait', 'failed', 'unknown', "
            "'cancelled', 'fenced')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="input_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="output_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="total_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "cost_status IN ('unknown', 'estimated', 'provider')",
            name="cost_status_allowed",
        ),
        sa.CheckConstraint(
            "token_usage_source IS NULL OR "
            "token_usage_source IN ('provider', 'estimated', 'unknown')",
            name="token_usage_source_allowed",
        ),
        sa.CheckConstraint(
            "estimated_cost_usd IS NULL OR estimated_cost_usd >= 0",
            name="estimated_cost_nonnegative",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "attempt_number",
            name="uq_analysis_attempts_job_number",
        ),
        sa.UniqueConstraint("lease_token", name="uq_analysis_attempts_lease_token"),
    )
    op.create_index(
        "ix_analysis_attempts_job_started",
        "analysis_attempts",
        ["job_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_attempts_job_started", table_name="analysis_attempts")
    op.drop_table("analysis_attempts")
