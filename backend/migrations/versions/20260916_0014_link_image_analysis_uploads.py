"""Link image analysis jobs to verified uploads.

Revision ID: 20260916_0014
Revises: 20260915_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0014"
down_revision: str | None = "20260915_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analysis_jobs", sa.Column("upload_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_analysis_jobs_upload_id_uploads",
        "analysis_jobs",
        "uploads",
        ["upload_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_analysis_jobs_upload_id", "analysis_jobs", ["upload_id"])
    op.create_check_constraint(
        "ck_analysis_jobs_input_upload_consistent",
        "analysis_jobs",
        "(input_type = 'text' AND upload_id IS NULL) OR "
        "(input_type = 'image' AND upload_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_analysis_jobs_input_upload_consistent", "analysis_jobs", type_="check")
    op.drop_index("ix_analysis_jobs_upload_id", table_name="analysis_jobs")
    op.drop_constraint("fk_analysis_jobs_upload_id_uploads", "analysis_jobs", type_="foreignkey")
    op.drop_column("analysis_jobs", "upload_id")
