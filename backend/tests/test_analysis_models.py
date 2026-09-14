from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    AnalysisAttempt,
    AnalysisConfirmation,
    AnalysisCorrection,
    AnalysisDraft,
    AnalysisEntity,
    AnalysisJob,
    Base,
    User,
)


def test_analysis_models_are_registered_with_required_identity_constraints() -> None:
    jobs = Base.metadata.tables[AnalysisJob.__tablename__]
    attempts = Base.metadata.tables[AnalysisAttempt.__tablename__]
    drafts = Base.metadata.tables[AnalysisDraft.__tablename__]
    entities = Base.metadata.tables[AnalysisEntity.__tablename__]
    confirmations = Base.metadata.tables[AnalysisConfirmation.__tablename__]
    corrections = Base.metadata.tables[AnalysisCorrection.__tablename__]

    assert {"user_id", "client_request_id", "request_hash", "input_ciphertext"} <= set(
        jobs.columns.keys()
    )
    assert "input_payload" not in jobs.columns
    assert jobs.columns.input_ciphertext.nullable is False
    assert jobs.columns.input_key_version.nullable is False
    assert {constraint.name for constraint in jobs.constraints} >= {
        "uq_analysis_jobs_user_client_request",
        "ck_analysis_jobs_status_allowed",
        "ck_analysis_jobs_lease_fields_consistent",
    }
    assert {constraint.name for constraint in attempts.constraints} >= {
        "uq_analysis_attempts_job_number",
        "uq_analysis_attempts_lease_token",
        "ck_analysis_attempts_phase_allowed",
        "ck_analysis_attempts_status_allowed",
        "ck_analysis_attempts_cost_status_allowed",
    }

    assert drafts.columns.job_id.unique is None
    assert {constraint.name for constraint in drafts.constraints} >= {
        "uq_analysis_drafts_job",
        "ck_analysis_drafts_version_positive",
    }
    assert {constraint.name for constraint in entities.constraints} >= {
        "uq_analysis_entities_draft_position",
        "ck_analysis_entities_confidence_range",
    }
    assert {constraint.name for constraint in confirmations.constraints} >= {
        "uq_analysis_confirmations_user_client_confirmation",
        "uq_analysis_confirmations_draft",
    }
    assert corrections.columns.confirmation_id.foreign_keys
    assert corrections.columns.entity_id.nullable is True


async def test_analysis_models_and_constraints_on_postgres(pg_session_factory) -> None:
    owner_id = uuid4()
    request_id = uuid4()
    now = datetime.now(UTC)

    async with pg_session_factory() as session:
        transaction = await session.begin()
        owner = User(
            id=owner_id,
            email=f"u2-analysis-{owner_id}@example.test",
            password_hash="test-only",
        )
        job = AnalysisJob(
            id=uuid4(),
            user_id=owner_id,
            client_request_id=request_id,
            request_hash="a" * 64,
            input_type="text",
            input_ciphertext=b"encrypted-test-payload",
            input_key_version=1,
            input_expires_at=now + timedelta(hours=1),
            status="succeeded",
            provider="test-provider",
            model="test-model",
            prompt_version="food-extraction-v1",
            result_schema_version="draft-v1",
            completed_at=now,
        )
        draft = AnalysisDraft(
            id=uuid4(),
            job_id=job.id,
            user_id=owner_id,
            status="confirmed",
            log_date=date(2026, 9, 8),
            result_schema_version="draft-v1",
            expires_at=now + timedelta(hours=1),
        )
        entity = AnalysisEntity(
            id=uuid4(),
            draft_id=draft.id,
            position=0,
            raw_name="一杯无糖美式",
            normalized_name="美式咖啡",
            amount=Decimal("1.000"),
            unit="cup",
            meal_type="drink",
            confidence=Decimal("0.9500"),
            needs_review=False,
            catalog_revision="catalog-v1",
            candidates=[{"name": "美式咖啡", "score": 0.95}],
        )
        confirmation = AnalysisConfirmation(
            id=uuid4(),
            user_id=owner_id,
            draft_id=draft.id,
            client_confirmation_id=uuid4(),
            request_hash="b" * 64,
            confirmed_draft_version=1,
            log_ids=[{"entity_id": str(entity.id), "log_id": str(uuid4())}],
            result_snapshot={"entity_count": 1},
        )
        correction = AnalysisCorrection(
            id=uuid4(),
            confirmation_id=confirmation.id,
            entity_id=entity.id,
            field_name="name",
            before_value="无糖美式",
            after_value="美式咖啡",
        )
        session.add(owner)
        await session.flush()
        session.add(job)
        await session.flush()
        session.add(draft)
        await session.flush()
        session.add(entity)
        await session.flush()
        session.add(confirmation)
        await session.flush()
        session.add(correction)
        await session.flush()

        assert (
            await session.get(AnalysisJob, job.id)
        ).input_ciphertext == b"encrypted-test-payload"
        assert (await session.get(AnalysisEntity, entity.id)).candidates[0]["score"] == 0.95
        assert await session.get(AnalysisCorrection, correction.id) is not None

        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(
                    AnalysisJob(
                        user_id=owner_id,
                        client_request_id=request_id,
                        request_hash="c" * 64,
                        input_type="text",
                        input_ciphertext=b"duplicate",
                        input_key_version=1,
                        input_expires_at=now + timedelta(hours=1),
                        status="queued",
                        provider="test-provider",
                        model="test-model",
                        prompt_version="food-extraction-v1",
                        result_schema_version="draft-v1",
                    )
                )
                await session.flush()

        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(
                    AnalysisJob(
                        user_id=owner_id,
                        client_request_id=uuid4(),
                        request_hash="d" * 64,
                        input_type="text",
                        input_ciphertext=b"invalid-status",
                        input_key_version=1,
                        input_expires_at=now + timedelta(hours=1),
                        status="not-a-real-status",
                        provider="test-provider",
                        model="test-model",
                        prompt_version="food-extraction-v1",
                        result_schema_version="draft-v1",
                    )
                )
                await session.flush()

        await transaction.rollback()
