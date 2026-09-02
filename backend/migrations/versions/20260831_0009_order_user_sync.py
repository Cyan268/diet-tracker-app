"""Order log writes per user, retaining the v1 global cursor.

Revision ID: 20260831_0009
Revises: 20260722_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0009"
down_revision: str | None = "20260722_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Release requires a write maintenance window: old writers do not follow this lock.
    op.create_table(
        "user_sync_state",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("epoch", sa.Uuid(), nullable=False),
        sa.Column("last_seq", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("minimum_valid_after", sa.BigInteger(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.CheckConstraint("last_seq >= 0", name="last_seq_nonnegative"),
        sa.CheckConstraint(
            "minimum_valid_after >= 0 AND minimum_valid_after <= last_seq",
            name="valid_retention_boundary",
        ),
    )
    op.add_column("sync_changes", sa.Column("user_seq", sa.BigInteger(), nullable=True))
    op.execute("""
        INSERT INTO user_sync_state (user_id, epoch, last_seq, minimum_valid_after)
        SELECT id, gen_random_uuid(), 0, 0 FROM users
    """)
    op.execute("""
        WITH ordered AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY id) AS seq
            FROM sync_changes
        )
        UPDATE sync_changes SET user_seq = ordered.seq FROM ordered
        WHERE sync_changes.id = ordered.id
    """)
    op.execute("""
        UPDATE user_sync_state SET last_seq = COALESCE(
            (SELECT MAX(user_seq) FROM sync_changes WHERE user_id = user_sync_state.user_id), 0
        )
    """)
    op.alter_column("sync_changes", "user_seq", nullable=False)
    op.create_unique_constraint("uq_sync_changes_user_seq", "sync_changes", ["user_id", "user_seq"])
    op.create_check_constraint("user_seq_positive", "sync_changes", "user_seq > 0")


def downgrade() -> None:
    op.drop_constraint("user_seq_positive", "sync_changes", type_="check")
    op.drop_constraint("uq_sync_changes_user_seq", "sync_changes", type_="unique")
    op.drop_column("sync_changes", "user_seq")
    op.drop_table("user_sync_state")
