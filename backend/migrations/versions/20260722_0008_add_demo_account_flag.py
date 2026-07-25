"""add demo account flag

Revision ID: 20260722_0008
Revises: 20260720_0007
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0008"
down_revision: str | None = "20260720_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_demo",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_demo")
