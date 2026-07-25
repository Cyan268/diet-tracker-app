"""create encrypted AI credentials

Revision ID: 20260718_0006
Revises: 20260717_0005
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0006"
down_revision: str | None = "20260717_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("encrypted_api_key", sa.LargeBinary(), nullable=False),
        sa.Column("key_last_four", sa.String(length=4), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_credentials_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_ai_credentials")),
    )


def downgrade() -> None:
    op.drop_table("ai_credentials")
