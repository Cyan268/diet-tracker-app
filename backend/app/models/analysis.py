from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AnalysisJob(TimestampMixin, Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "client_request_id",
            name="uq_analysis_jobs_user_client_request",
        ),
        CheckConstraint("input_type IN ('text', 'image')", name="input_type_allowed"),
        CheckConstraint(
            "(input_type = 'text' AND upload_id IS NULL) OR "
            "(input_type = 'image' AND upload_id IS NOT NULL)",
            name="input_upload_consistent",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'retry_wait', 'succeeded', 'failed', "
            "'unknown', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("input_key_version >= 1", name="input_key_version_positive"),
        CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="lease_fields_consistent",
        ),
        Index("ix_analysis_jobs_claim", "status", "next_attempt_at", "created_at", "id"),
        Index("ix_analysis_jobs_user_created", "user_id", "created_at"),
        Index("ix_analysis_jobs_upload_id", "upload_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    upload_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("uploads.id", ondelete="RESTRICT"),
    )
    client_request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_type: Mapped[str] = mapped_column(String(12), nullable=False)
    input_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    input_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    result_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(60))


class AnalysisAttempt(Base):
    __tablename__ = "analysis_attempts"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "attempt_number",
            name="uq_analysis_attempts_job_number",
        ),
        UniqueConstraint("lease_token", name="uq_analysis_attempts_lease_token"),
        CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        CheckConstraint(
            "phase IN ('claimed', 'dispatching', 'response_received', 'finished')",
            name="phase_allowed",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'retry_wait', 'failed', 'unknown', "
            "'cancelled', 'fenced')",
            name="status_allowed",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="input_tokens_nonnegative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="output_tokens_nonnegative",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="total_tokens_nonnegative",
        ),
        CheckConstraint(
            "cost_status IN ('unknown', 'estimated', 'provider')",
            name="cost_status_allowed",
        ),
        CheckConstraint(
            "token_usage_source IS NULL OR "
            "token_usage_source IN ('provider', 'estimated', 'unknown')",
            name="token_usage_source_allowed",
        ),
        CheckConstraint(
            "estimated_cost_usd IS NULL OR estimated_cost_usd >= 0",
            name="estimated_cost_nonnegative",
        ),
        Index("ix_analysis_attempts_job_started", "job_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_token: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    phase: Mapped[str] = mapped_column(String(24), nullable=False, default="claimed")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(60))
    retryable: Mapped[bool | None] = mapped_column(Boolean)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    token_usage_source: Mapped[str | None] = mapped_column(String(20))
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 8))
    cost_status: Mapped[str] = mapped_column(String(12), nullable=False, default="unknown")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    dispatch_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisDraft(TimestampMixin, Base):
    __tablename__ = "analysis_drafts"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_analysis_drafts_job"),
        CheckConstraint(
            "status IN ('review', 'confirmed', 'expired', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_analysis_drafts_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="review")
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    result_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalysisEntity(TimestampMixin, Base):
    __tablename__ = "analysis_entities"
    __table_args__ = (
        UniqueConstraint("draft_id", "position", name="uq_analysis_entities_draft_position"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'drink')",
            name="meal_type_allowed",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        Index("ix_analysis_entities_draft", "draft_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    draft_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_drafts.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    meal_type: Mapped[str] = mapped_column(String(12), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    matched_food_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("food_items.id", ondelete="SET NULL"),
    )
    catalog_revision: Mapped[str | None] = mapped_column(String(80))
    candidates: Mapped[list[dict[str, object]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )


class AnalysisConfirmation(Base):
    __tablename__ = "analysis_confirmations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "client_confirmation_id",
            name="uq_analysis_confirmations_user_client_confirmation",
        ),
        UniqueConstraint("draft_id", name="uq_analysis_confirmations_draft"),
        CheckConstraint("confirmed_draft_version >= 1", name="draft_version_positive"),
        Index("ix_analysis_confirmations_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    draft_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_drafts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    client_confirmation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    log_ids: Mapped[list[dict[str, str | None]]] = mapped_column(JSON, nullable=False)
    result_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class AnalysisCorrection(Base):
    __tablename__ = "analysis_corrections"
    __table_args__ = (
        CheckConstraint(
            "field_name IN ('entity_added', 'entity_removed', 'name', 'amount', 'unit', "
            "'meal_type', 'food_match')",
            name="field_name_allowed",
        ),
        Index("ix_analysis_corrections_confirmation", "confirmation_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    confirmation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_confirmations.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_entities.id", ondelete="SET NULL"),
    )
    field_name: Mapped[str] = mapped_column(String(40), nullable=False)
    before_value: Mapped[object | None] = mapped_column(JSON)
    after_value: Mapped[object | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
