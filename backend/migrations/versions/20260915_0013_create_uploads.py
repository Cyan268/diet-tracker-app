"""Create private image upload records.

Revision ID: 20260915_0013
Revises: 20260909_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0013"
down_revision: str | None = "20260909_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("declared_size", sa.Integer(), nullable=False),
        sa.Column("declared_sha256", sa.String(64), nullable=False),
        sa.Column("verified_size", sa.Integer()),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("sha256", sa.String(64)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("sealed_object_key", sa.String(500)),
        sa.Column("sealed_object_version", sa.String(80)),
        sa.Column("upload_url_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delete_attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(60)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'failed', 'delete_pending', 'deleted')",
            name="status_allowed",
        ),
        sa.CheckConstraint("declared_size > 0", name="declared_size_positive"),
        sa.CheckConstraint(
            "verified_size IS NULL OR verified_size > 0", name="verified_size_positive"
        ),
        sa.CheckConstraint("width IS NULL OR width > 0", name="width_positive"),
        sa.CheckConstraint("height IS NULL OR height > 0", name="height_positive"),
        sa.CheckConstraint("delete_attempt_count >= 0", name="delete_attempt_count_nonnegative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key", name="uq_uploads_object_key"),
        sa.UniqueConstraint("sealed_object_key", name="uq_uploads_sealed_object_key"),
    )
    op.create_index("ix_uploads_user_created", "uploads", ["user_id", "created_at"])
    op.create_index("ix_uploads_cleanup", "uploads", ["status", "expires_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_uploads_cleanup", table_name="uploads")
    op.drop_index("ix_uploads_user_created", table_name="uploads")
    op.drop_table("uploads")
