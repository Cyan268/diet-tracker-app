from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update

from app.ai.openai_image_responses import OpenAIResponsesFoodImageProvider
from app.ai.provider import ProviderError, ProviderResult
from app.core.config import Settings
from app.models import (
    AiCredential,
    AnalysisAttempt,
    AnalysisDraft,
    AnalysisEntity,
    AnalysisJob,
    Upload,
    User,
)
from app.repositories.analysis_jobs import (
    cancel_job,
    claim_next_job,
    mark_dispatch_started,
    recover_expired_jobs,
    renew_lease,
)
from app.schemas.ai import FoodTextAnalyzeRequest, ParsedFoodEntity
from app.schemas.analysis import AnalysisImageCreateRequest
from app.schemas.diet import MealType
from app.services.analysis import create_image_analysis_job
from app.services.analysis_input_encryption import encrypt_analysis_input
from app.services.analysis_worker import complete_job_failure, complete_job_success
from app.services.analysis_worker_runtime import process_claimed_job
from app.services.catalog_seed import seed_global_catalog
from app.services.credential_encryption import encrypt_api_key
from app.services.upload_storage import LocalPrivateUploadStore


async def create_job(pg_session_factory, *, label: str) -> UUID:
    user_id = uuid4()
    async with pg_session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=f"worker-{label}-{user_id}@example.test",
                password_hash="test-only",
            )
        )
        await session.flush()
        job = AnalysisJob(
            user_id=user_id,
            client_request_id=uuid4(),
            request_hash=uuid4().hex + uuid4().hex,
            input_type="text",
            input_ciphertext=b"encrypted-test-input",
            input_key_version=1,
            input_expires_at=datetime.now(UTC) + timedelta(minutes=10),
            status="queued",
            provider="rule_based",
            model="rule-based-v1",
            prompt_version="rule-food-text-v1.0.0",
            result_schema_version="draft-v1",
        )
        session.add(job)
        await session.commit()
        return job.id


async def claim(pg_session_factory, job_id: UUID):
    async with pg_session_factory() as session:
        claimed = await claim_next_job(session, lease_seconds=120, max_attempts=3)
        assert claimed is not None and claimed.job.id == job_id
        await session.commit()
        return claimed


def apple_result(*, two_entities: bool = False) -> ProviderResult:
    entities = [
        ParsedFoodEntity(
            raw_name="苹果",
            normalized_name="苹果",
            amount=1,
            unit="个",
            meal_type=MealType.SNACK,
            confidence=0.98,
            needs_review=False,
            evidence="测试输入包含苹果",
        )
    ]
    if two_entities:
        entities.append(
            ParsedFoodEntity(
                raw_name="香蕉",
                normalized_name="香蕉",
                amount=1,
                unit="根",
                meal_type=MealType.SNACK,
                confidence=0.97,
                needs_review=False,
                evidence="测试输入包含香蕉",
            )
        )
    return ProviderResult(
        entities=entities,
        model="rule-based-v1",
        input_tokens=10,
        output_tokens=20,
    )


def request() -> FoodTextAnalyzeRequest:
    return FoodTextAnalyzeRequest(
        text="我吃了一个苹果",
        log_date=date(2026, 9, 9),
        meal_type_hint=MealType.SNACK,
    )


async def test_skip_locked_allows_only_one_worker_to_claim(pg_session_factory) -> None:
    job_id = await create_job(pg_session_factory, label="claim")
    async with pg_session_factory() as first, pg_session_factory() as second:
        await first.begin()
        first_claim = await claim_next_job(first, lease_seconds=120, max_attempts=3)
        assert first_claim is not None and first_claim.job.id == job_id

        await second.begin()
        second_claim = await claim_next_job(second, lease_seconds=120, max_attempts=3)
        assert second_claim is None
        await first.commit()
        await second.rollback()

    async with pg_session_factory() as session:
        attempts = await session.scalar(
            select(func.count())
            .select_from(AnalysisAttempt)
            .where(AnalysisAttempt.job_id == job_id)
        )
        assert attempts == 1


async def test_expired_pre_dispatch_lease_retries_and_fences_old_worker(
    pg_session_factory,
) -> None:
    job_id = await create_job(pg_session_factory, label="reclaim")
    first_claim = await claim(pg_session_factory, job_id)
    first_token = first_claim.attempt.lease_token

    async with pg_session_factory() as session:
        await session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
        recovered = await recover_expired_jobs(session, max_attempts=3)
        await session.commit()
        assert recovered == {"retry_wait": 1, "failed": 0, "unknown": 0}

    async with pg_session_factory() as session:
        stale_result = await complete_job_success(
            session,
            job_id=job_id,
            lease_token=first_token,
            request=request(),
            result=apple_result(),
            draft_ttl_minutes=60,
        )
        assert stale_result is None
        await session.rollback()

    second_claim = await claim(pg_session_factory, job_id)
    assert second_claim.attempt.lease_token != first_token
    async with pg_session_factory() as session:
        assert await cancel_job(session, job_id, second_claim.job.user_id) is True
        await session.commit()
    async with pg_session_factory() as session:
        assert (
            await complete_job_success(
                session,
                job_id=job_id,
                lease_token=second_claim.attempt.lease_token,
                request=request(),
                result=apple_result(),
                draft_ttl_minutes=60,
            )
            is None
        )


async def test_expired_post_dispatch_lease_becomes_unknown(pg_session_factory) -> None:
    job_id = await create_job(pg_session_factory, label="unknown")
    claimed = await claim(pg_session_factory, job_id)
    async with pg_session_factory() as session:
        assert await mark_dispatch_started(session, job_id, claimed.attempt.lease_token)
        await session.commit()
    async with pg_session_factory() as session:
        await session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
        recovered = await recover_expired_jobs(session, max_attempts=3)
        await session.commit()
        assert recovered == {"retry_wait": 0, "failed": 0, "unknown": 1}
    async with pg_session_factory() as session:
        job = await session.get(AnalysisJob, job_id)
        assert job is not None
        assert job.status == "unknown"
        assert job.failure_code == "worker_lost_after_dispatch"


async def test_heartbeat_renews_only_the_current_lease(pg_session_factory) -> None:
    job_id = await create_job(pg_session_factory, label="heartbeat")
    claimed = await claim(pg_session_factory, job_id)
    previous_expiry = claimed.job.lease_expires_at

    async with pg_session_factory() as session:
        assert await renew_lease(
            session,
            job_id,
            claimed.attempt.lease_token,
            lease_seconds=240,
        )
        await session.commit()
    async with pg_session_factory() as session:
        job = await session.get(AnalysisJob, job_id)
        assert job is not None and job.lease_expires_at > previous_expiry
        assert not await renew_lease(
            session,
            job_id,
            uuid4(),
            lease_seconds=240,
        )


async def test_success_persists_draft_entities_and_attempt_atomically(
    pg_session_factory,
) -> None:
    async with pg_session_factory() as session:
        await seed_global_catalog(session)
    job_id = await create_job(pg_session_factory, label="success")
    claimed = await claim(pg_session_factory, job_id)

    async with pg_session_factory() as session:
        assert await mark_dispatch_started(session, job_id, claimed.attempt.lease_token)
        await session.commit()
    async with pg_session_factory() as session:
        draft = await complete_job_success(
            session,
            job_id=job_id,
            lease_token=claimed.attempt.lease_token,
            request=request(),
            result=apple_result(),
            draft_ttl_minutes=60,
        )
        assert draft is not None
        await session.commit()

    async with pg_session_factory() as session:
        job = await session.get(AnalysisJob, job_id)
        attempt = await session.scalar(
            select(AnalysisAttempt).where(AnalysisAttempt.job_id == job_id)
        )
        draft = await session.scalar(select(AnalysisDraft).where(AnalysisDraft.job_id == job_id))
        entity = await session.scalar(
            select(AnalysisEntity).where(AnalysisEntity.draft_id == draft.id)
        )
        assert job is not None and job.status == "succeeded" and job.lease_token is None
        assert attempt is not None and attempt.status == "succeeded"
        assert attempt.total_tokens == 30 and attempt.cost_status == "unknown"
        assert draft is not None and draft.status == "review"
        assert entity is not None and entity.matched_food_id is not None
        assert entity.candidates[0]["reason"] == "canonical_exact"


async def test_result_database_failure_leaves_no_partial_draft(
    pg_session_factory,
    monkeypatch,
) -> None:
    import app.services.analysis_worker as worker_service

    async with pg_session_factory() as session:
        await seed_global_catalog(session)
    job_id = await create_job(pg_session_factory, label="rollback")
    claimed = await claim(pg_session_factory, job_id)
    original_match = worker_service.match_visible_foods
    calls = 0

    async def fail_second_match(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected result persistence failure")
        return await original_match(*args, **kwargs)

    monkeypatch.setattr(worker_service, "match_visible_foods", fail_second_match)
    async with pg_session_factory() as session:
        with pytest.raises(RuntimeError, match="injected result persistence failure"):
            await complete_job_success(
                session,
                job_id=job_id,
                lease_token=claimed.attempt.lease_token,
                request=request(),
                result=apple_result(two_entities=True),
                draft_ttl_minutes=60,
            )
        await session.rollback()

    async with pg_session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AnalysisDraft)
                .where(AnalysisDraft.job_id == job_id)
            )
            == 0
        )
        job = await session.get(AnalysisJob, job_id)
        assert job is not None and job.status == "running"


async def test_failure_classification_retries_only_known_safe_failures(
    pg_session_factory,
) -> None:
    retry_job = await create_job(pg_session_factory, label="retry")
    retry_claim = await claim(pg_session_factory, retry_job)
    async with pg_session_factory() as session:
        status = await complete_job_failure(
            session,
            job_id=retry_job,
            lease_token=retry_claim.attempt.lease_token,
            error_code="local_pre_dispatch_failure",
            retryable=True,
            outcome_unknown=False,
            max_attempts=3,
            retry_delay_seconds=1,
        )
        await session.commit()
        assert status == "retry_wait"

    unknown_job = await create_job(pg_session_factory, label="provider-timeout")
    unknown_claim = await claim(pg_session_factory, unknown_job)
    async with pg_session_factory() as session:
        status = await complete_job_failure(
            session,
            job_id=unknown_job,
            lease_token=unknown_claim.attempt.lease_token,
            error_code="provider_timeout",
            retryable=True,
            outcome_unknown=True,
            max_attempts=3,
            retry_delay_seconds=1,
        )
        await session.commit()
        assert status == "unknown"


async def test_runtime_decrypts_dispatches_and_persists_without_plaintext(
    pg_session_factory,
) -> None:
    settings = Settings(
        _env_file=None,
        credential_encryption_key="worker-test-encryption-secret-at-least-32-bytes",
    )
    user_id = uuid4()
    job_id = uuid4()
    analysis_request = request()
    encrypted = encrypt_analysis_input(
        analysis_request.model_dump(mode="json"),
        user_id,
        job_id,
        settings.credential_encryption_key.get_secret_value(),
    )
    async with pg_session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=f"worker-runtime-{user_id}@example.test",
                password_hash="test-only",
            )
        )
        await session.flush()
        session.add(
            AnalysisJob(
                id=job_id,
                user_id=user_id,
                client_request_id=uuid4(),
                request_hash=uuid4().hex + uuid4().hex,
                input_type="text",
                input_ciphertext=encrypted,
                input_key_version=1,
                input_expires_at=datetime.now(UTC) + timedelta(minutes=10),
                status="queued",
                provider="rule_based",
                model="rule-based-v1",
                prompt_version="rule-food-text-v1.0.0",
                result_schema_version="draft-v1",
            )
        )
        await session.commit()

    claimed = await claim(pg_session_factory, job_id)
    assert await process_claimed_job(pg_session_factory, settings, claimed) == "succeeded"

    async with pg_session_factory() as session:
        stored_job = await session.get(AnalysisJob, job_id)
        stored_draft = await session.scalar(
            select(AnalysisDraft).where(AnalysisDraft.job_id == job_id)
        )
        assert stored_job is not None and stored_job.status == "succeeded"
        assert stored_job.input_ciphertext == encrypted
        assert analysis_request.text.encode() not in encrypted
        assert stored_draft is not None


async def test_runtime_does_not_retry_uncertain_external_dispatch(
    pg_session_factory,
) -> None:
    settings = Settings(
        _env_file=None,
        credential_encryption_key="worker-test-encryption-secret-at-least-32-bytes",
    )
    user_id = uuid4()
    job_id = uuid4()
    encrypted = encrypt_analysis_input(
        request().model_dump(mode="json"),
        user_id,
        job_id,
        settings.credential_encryption_key.get_secret_value(),
    )
    async with pg_session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=f"worker-uncertain-{user_id}@example.test",
                password_hash="test-only",
            )
        )
        await session.flush()
        session.add(
            AnalysisJob(
                id=job_id,
                user_id=user_id,
                client_request_id=uuid4(),
                request_hash=uuid4().hex + uuid4().hex,
                input_type="text",
                input_ciphertext=encrypted,
                input_key_version=1,
                input_expires_at=datetime.now(UTC) + timedelta(minutes=10),
                status="queued",
                provider="openai_responses",
                model="test-model",
                prompt_version="food-text-v1.0.0",
                result_schema_version="draft-v1",
            )
        )
        await session.commit()

    dispatch_calls = 0

    class UncertainProvider:
        name = "openai_responses"

        async def extract(self, analysis_request):
            nonlocal dispatch_calls
            dispatch_calls += 1
            del analysis_request
            raise ProviderError("network_error", "connection lost", retryable=True)

    provider_calls = 0

    async def provider_factory(claimed_job, analysis_request):
        nonlocal provider_calls
        del claimed_job, analysis_request
        provider_calls += 1
        return UncertainProvider()

    claimed = await claim(pg_session_factory, job_id)
    assert (
        await process_claimed_job(
            pg_session_factory,
            settings,
            claimed,
            provider_factory=provider_factory,
        )
        == "unknown"
    )
    assert provider_calls == 1
    assert dispatch_calls == 1
    async with pg_session_factory() as session:
        stored_job = await session.get(AnalysisJob, job_id)
        attempt = await session.scalar(
            select(AnalysisAttempt).where(AnalysisAttempt.job_id == job_id)
        )
        assert stored_job is not None and stored_job.status == "unknown"
        assert attempt is not None and attempt.error_code == "network_error"


async def test_image_runtime_reads_verified_private_object_and_reuses_draft_pipeline(
    pg_session_factory,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        credential_encryption_key="worker-image-encryption-secret-at-least-32-bytes",
        upload_root=tmp_path,
    )
    user_id = uuid4()
    upload_id = uuid4()
    sealed_key = f"sealed/{user_id}/{upload_id}/normalized.png"
    normalized_image = b"verified-normalized-image-bytes"
    await LocalPrivateUploadStore(tmp_path).seal(sealed_key, normalized_image)
    async with pg_session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=f"worker-image-{user_id}@example.test",
                password_hash="test-only",
            )
        )
        await session.flush()
        session.add(
            Upload(
                id=upload_id,
                user_id=user_id,
                object_key=f"staging/{user_id}/{upload_id}/source.upload",
                status="ready",
                declared_size=100,
                declared_sha256="a" * 64,
                verified_size=100,
                content_type="image/png",
                sha256="a" * 64,
                width=20,
                height=10,
                sealed_object_key=sealed_key,
                sealed_object_version="b" * 64,
                upload_url_expires_at=datetime.now(UTC) + timedelta(minutes=10),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.add(
            AiCredential(
                user_id=user_id,
                provider="openai",
                encrypted_api_key=encrypt_api_key(
                    "sk-worker-image-test-key-123456",
                    user_id,
                    settings.credential_encryption_key.get_secret_value(),
                ),
                key_last_four="3456",
            )
        )
        await session.commit()
        job, _ = await create_image_analysis_job(
            session,
            user_id=user_id,
            request=AnalysisImageCreateRequest(
                client_request_id=uuid4(),
                upload_id=upload_id,
                log_date=date(2026, 9, 16),
                meal_type_hint=MealType.LUNCH,
                consent_to_provider=True,
            ),
            master_secret=settings.credential_encryption_key.get_secret_value(),
            openai_model="test-image-model",
            input_ttl_minutes=10,
            max_pending_per_user=3,
        )
        job_id = job.id

    captured: dict[str, object] = {}

    async def extract_image(_self, analysis_request, image_bytes, content_type):
        captured.update(
            request=analysis_request,
            image_bytes=image_bytes,
            content_type=content_type,
        )
        return apple_result()

    monkeypatch.setattr(OpenAIResponsesFoodImageProvider, "extract", extract_image)
    claimed = await claim(pg_session_factory, job_id)
    assert await process_claimed_job(pg_session_factory, settings, claimed) == "succeeded"
    assert captured["image_bytes"] == normalized_image
    assert captured["content_type"] == "image/png"

    async with pg_session_factory() as session:
        stored_job = await session.get(AnalysisJob, job_id)
        draft = await session.scalar(select(AnalysisDraft).where(AnalysisDraft.job_id == job_id))
        assert draft is not None
        entity = await session.scalar(
            select(AnalysisEntity).where(AnalysisEntity.draft_id == draft.id)
        )
        assert stored_job is not None and stored_job.status == "succeeded"
        assert draft.log_date == date(2026, 9, 16)
        assert entity is not None and entity.normalized_name == "苹果"
