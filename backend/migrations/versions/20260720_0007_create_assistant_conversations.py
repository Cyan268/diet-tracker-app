"""create assistant conversations and messages

Revision ID: 20260720_0007
Revises: 20260718_0006
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_0007"
down_revision: str | None = "20260718_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
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
            name=op.f("fk_assistant_conversations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_conversations")),
    )
    op.create_index(
        "ix_assistant_conversations_user_updated",
        "assistant_conversations",
        ["user_id", "updated_at"],
    )
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("provider", sa.String(length=60), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("trace_id", sa.Uuid(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("disclaimer", sa.String(length=240), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name=op.f("ck_assistant_messages_role_allowed"),
        ),
        sa.CheckConstraint(
            "sequence >= 1",
            name=op.f("ck_assistant_messages_sequence_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["assistant_conversations.id"],
            name=op.f("fk_assistant_messages_conversation_id_assistant_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trace_id"],
            ["ai_call_logs.id"],
            name=op.f("fk_assistant_messages_trace_id_ai_call_logs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_messages")),
        sa.UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name=op.f("uq_assistant_messages_conversation_client_message"),
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name=op.f("uq_assistant_messages_conversation_sequence"),
        ),
    )
    op.create_index(
        "ix_assistant_messages_conversation_sequence",
        "assistant_messages",
        ["conversation_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assistant_messages_conversation_sequence",
        table_name="assistant_messages",
    )
    op.drop_table("assistant_messages")
    op.drop_index(
        "ix_assistant_conversations_user_updated",
        table_name="assistant_conversations",
    )
    op.drop_table("assistant_conversations")
