import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai import (
    OpenAIResponsesFoodImageProvider,
    OpenAIResponsesFoodTextProvider,
    ProviderError,
    RuleBasedFoodTextProvider,
)
from app.ai.provider import FoodTextProvider, ProviderResult
from app.core.config import Settings
from app.models import AiCredential, Upload, User
from app.repositories.analysis_jobs import (
    ClaimedAnalysisJob,
    claim_next_job,
    mark_dispatch_started,
    mark_response_received,
    recover_expired_jobs,
    renew_lease,
)
from app.schemas.ai import FoodTextAnalyzeRequest
from app.schemas.analysis import AnalysisImageWorkerRequest
from app.services.analysis_input_encryption import (
    AnalysisInputDecryptionError,
    decrypt_analysis_input,
)
from app.services.analysis_worker import complete_job_failure, complete_job_success
from app.services.credential_encryption import CredentialDecryptionError, decrypt_api_key
from app.services.upload_storage import LocalPrivateUploadStore
from app.services.uploads import cleanup_expired_uploads

logger = logging.getLogger("nutripilot.analysis_worker")


class ProviderFactory(Protocol):
    async def __call__(
        self, claimed: ClaimedAnalysisJob, request: FoodTextAnalyzeRequest
    ) -> FoodTextProvider: ...


class WorkerPreparationError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class WorkerCycleResult:
    claimed: bool
    job_id: str | None = None
    outcome: str | None = None


WorkerRequest = FoodTextAnalyzeRequest | AnalysisImageWorkerRequest


def _decode_request(claimed: ClaimedAnalysisJob, settings: Settings) -> WorkerRequest:
    if claimed.job.input_type not in {"text", "image"} or claimed.job.input_key_version != 1:
        raise WorkerPreparationError("unsupported_analysis_input")
    try:
        payload = decrypt_analysis_input(
            claimed.job.input_ciphertext,
            claimed.job.user_id,
            claimed.job.id,
            settings.credential_encryption_key.get_secret_value(),
        )
        model = (
            FoodTextAnalyzeRequest
            if claimed.job.input_type == "text"
            else AnalysisImageWorkerRequest
        )
        return model.model_validate(payload)
    except (AnalysisInputDecryptionError, ValidationError) as error:
        raise WorkerPreparationError("invalid_analysis_input") from error


async def _default_provider_factory(
    claimed: ClaimedAnalysisJob,
    request: FoodTextAnalyzeRequest,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> FoodTextProvider:
    del request
    if claimed.job.provider in {"rule_based", "rule_based_v1"}:
        provider = RuleBasedFoodTextProvider()
        if (
            claimed.job.model != provider.model
            or claimed.job.prompt_version != provider.prompt_version
        ):
            raise WorkerPreparationError("provider_snapshot_unavailable")
        return provider
    if claimed.job.provider not in {"openai", "openai_responses"}:
        raise WorkerPreparationError("provider_not_supported")

    async with session_factory() as session:
        user = await session.get(User, claimed.job.user_id)
        credential = await session.get(AiCredential, claimed.job.user_id)
    if user is None or user.is_demo:
        raise WorkerPreparationError("openai_not_allowed")
    api_key: str | None = None
    if credential is not None:
        try:
            api_key = decrypt_api_key(
                credential.encrypted_api_key,
                claimed.job.user_id,
                settings.credential_encryption_key.get_secret_value(),
            )
        except CredentialDecryptionError as error:
            raise WorkerPreparationError("credential_decryption_failed") from error
    elif settings.ai_provider == "openai" and settings.openai_api_key is not None:
        api_key = settings.openai_api_key.get_secret_value()
    if not api_key:
        raise WorkerPreparationError("credential_missing")
    provider = OpenAIResponsesFoodTextProvider(
        api_key=api_key,
        model=claimed.job.model,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
    )
    if claimed.job.prompt_version != provider.prompt_version:
        raise WorkerPreparationError("provider_snapshot_unavailable")
    return provider


async def _api_key_for_job(
    claimed: ClaimedAnalysisJob,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> str:
    async with session_factory() as session:
        user = await session.get(User, claimed.job.user_id)
        credential = await session.get(AiCredential, claimed.job.user_id)
    if user is None or user.is_demo:
        raise WorkerPreparationError("openai_not_allowed")
    if credential is not None:
        try:
            return decrypt_api_key(
                credential.encrypted_api_key,
                claimed.job.user_id,
                settings.credential_encryption_key.get_secret_value(),
            )
        except CredentialDecryptionError as error:
            raise WorkerPreparationError("credential_decryption_failed") from error
    if settings.ai_provider == "openai" and settings.openai_api_key is not None:
        return settings.openai_api_key.get_secret_value()
    raise WorkerPreparationError("credential_missing")


async def _prepare_image_provider(
    claimed: ClaimedAnalysisJob,
    request: AnalysisImageWorkerRequest,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> tuple[OpenAIResponsesFoodImageProvider, bytes, str]:
    if (
        claimed.job.provider != OpenAIResponsesFoodImageProvider.name
        or claimed.job.prompt_version != OpenAIResponsesFoodImageProvider.prompt_version
        or claimed.job.upload_id != request.upload_id
    ):
        raise WorkerPreparationError("provider_snapshot_unavailable")
    async with session_factory() as session:
        upload = await session.get(Upload, request.upload_id)
    if (
        upload is None
        or upload.user_id != claimed.job.user_id
        or upload.status != "ready"
        or upload.sealed_object_key is None
    ):
        raise WorkerPreparationError("verified_upload_unavailable")
    try:
        image_bytes = await LocalPrivateUploadStore(settings.upload_root).read(
            upload.sealed_object_key
        )
    except Exception as error:
        raise WorkerPreparationError("verified_upload_unavailable", retryable=True) from error
    provider = OpenAIResponsesFoodImageProvider(
        api_key=await _api_key_for_job(claimed, session_factory=session_factory, settings=settings),
        model=claimed.job.model,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
    )
    return provider, image_bytes, upload.content_type


async def _record_failure(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    claimed: ClaimedAnalysisJob,
    *,
    error_code: str,
    retryable: bool,
    outcome_unknown: bool,
) -> str | None:
    async with session_factory() as session, session.begin():
        return await complete_job_failure(
            session,
            job_id=claimed.job.id,
            lease_token=claimed.attempt.lease_token,
            error_code=error_code,
            retryable=retryable,
            outcome_unknown=outcome_unknown,
            max_attempts=settings.analysis_max_attempts,
            retry_delay_seconds=settings.ai_retry_delay_seconds
            * (2 ** max(claimed.job.attempt_count - 1, 0)),
        )


async def _heartbeat(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    claimed: ClaimedAnalysisJob,
    stop: asyncio.Event,
    lease_lost: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.analysis_heartbeat_seconds)
            return
        except TimeoutError:
            pass
        try:
            async with session_factory() as session, session.begin():
                renewed = await renew_lease(
                    session,
                    claimed.job.id,
                    claimed.attempt.lease_token,
                    lease_seconds=settings.analysis_lease_seconds,
                )
            if not renewed:
                lease_lost.set()
                return
        except Exception:
            logger.exception(
                "analysis_worker_heartbeat_failed",
                extra={
                    "event": "analysis_worker.heartbeat_failed",
                    "job_id": str(claimed.job.id),
                },
            )


async def _persist_result(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    claimed: ClaimedAnalysisJob,
    request: WorkerRequest,
    result: ProviderResult,
) -> bool:
    # Retry only the database write with the in-memory provider result. Never
    # dispatch a second paid request because a commit outcome was uncertain.
    for persistence_attempt in range(3):
        try:
            async with session_factory() as session, session.begin():
                draft = await complete_job_success(
                    session,
                    job_id=claimed.job.id,
                    lease_token=claimed.attempt.lease_token,
                    request=request,
                    result=result,
                    draft_ttl_minutes=settings.analysis_draft_ttl_minutes,
                    input_price_per_million=settings.ai_input_price_per_million_usd,
                    output_price_per_million=settings.ai_output_price_per_million_usd,
                )
            return draft is not None
        except SQLAlchemyError:
            logger.exception(
                "analysis_worker_result_persistence_failed",
                extra={
                    "event": "analysis_worker.result_persistence_failed",
                    "job_id": str(claimed.job.id),
                    "attempt_number": persistence_attempt + 1,
                    "error_code": "database_write_failed",
                },
            )
            if persistence_attempt < 2:
                await asyncio.sleep(0.1 * (2**persistence_attempt))
    return False


async def process_claimed_job(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    claimed: ClaimedAnalysisJob,
    *,
    provider_factory: ProviderFactory | None = None,
) -> str | None:
    try:
        request = _decode_request(claimed, settings)
        provider = None
        image_context = None
        if isinstance(request, FoodTextAnalyzeRequest):
            provider = (
                await provider_factory(claimed, request)
                if provider_factory is not None
                else await _default_provider_factory(
                    claimed,
                    request,
                    session_factory=session_factory,
                    settings=settings,
                )
            )
        else:
            image_context = await _prepare_image_provider(
                claimed,
                request,
                session_factory=session_factory,
                settings=settings,
            )
    except WorkerPreparationError as error:
        return await _record_failure(
            session_factory,
            settings,
            claimed,
            error_code=error.code,
            retryable=error.retryable,
            outcome_unknown=False,
        )

    async with session_factory() as session, session.begin():
        dispatched = await mark_dispatch_started(
            session, claimed.job.id, claimed.attempt.lease_token
        )
    if not dispatched:
        return None

    stop = asyncio.Event()
    lease_lost = asyncio.Event()
    heartbeat = asyncio.create_task(
        _heartbeat(session_factory, settings, claimed, stop, lease_lost)
    )
    try:
        try:
            async with asyncio.timeout(settings.ai_timeout_seconds):
                result = (
                    await provider.extract(request)
                    if provider is not None and isinstance(request, FoodTextAnalyzeRequest)
                    else await image_context[0].extract(
                        request,
                        image_context[1],
                        image_context[2],
                    )
                )
        except TimeoutError:
            return await _record_failure(
                session_factory,
                settings,
                claimed,
                error_code="provider_timeout",
                retryable=provider is not None and provider.name == "rule_based_v1",
                outcome_unknown=provider is None or provider.name != "rule_based_v1",
            )
        except ProviderError as error:
            return await _record_failure(
                session_factory,
                settings,
                claimed,
                error_code=error.code,
                retryable=(
                    error.retryable and provider is not None and provider.name == "rule_based_v1"
                ),
                outcome_unknown=(
                    (provider is None or provider.name != "rule_based_v1") and error.retryable
                ),
            )
        except Exception:
            logger.exception(
                "analysis_worker_provider_failed",
                extra={
                    "event": "analysis_worker.provider_failed",
                    "job_id": str(claimed.job.id),
                    "error_code": "provider_unexpected_error",
                },
            )
            return await _record_failure(
                session_factory,
                settings,
                claimed,
                error_code="provider_unexpected_error",
                retryable=provider is not None and provider.name == "rule_based_v1",
                outcome_unknown=provider is None or provider.name != "rule_based_v1",
            )
        if lease_lost.is_set():
            return None
        async with session_factory() as session, session.begin():
            received = await mark_response_received(
                session, claimed.job.id, claimed.attempt.lease_token
            )
        if not received:
            return None
        return (
            "succeeded"
            if await _persist_result(session_factory, settings, claimed, request, result)
            else None
        )
    finally:
        stop.set()
        await heartbeat


async def run_worker_cycle(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    provider_factory: ProviderFactory | None = None,
) -> WorkerCycleResult:
    async with session_factory() as session, session.begin():
        await recover_expired_jobs(session, max_attempts=settings.analysis_max_attempts)
        claimed = await claim_next_job(
            session,
            lease_seconds=settings.analysis_lease_seconds,
            max_attempts=settings.analysis_max_attempts,
            global_concurrency=settings.analysis_global_concurrency,
        )
    if claimed is None:
        return WorkerCycleResult(claimed=False)
    outcome = await process_claimed_job(
        session_factory,
        settings,
        claimed,
        provider_factory=provider_factory,
    )
    return WorkerCycleResult(claimed=True, job_id=str(claimed.job.id), outcome=outcome)


async def run_worker_forever(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    stop_event: asyncio.Event | None = None,
) -> None:
    if not settings.analysis_worker_enabled:
        raise RuntimeError("analysis Worker is disabled by configuration")
    stop = stop_event or asyncio.Event()
    upload_store = LocalPrivateUploadStore(settings.upload_root)
    next_upload_cleanup = 0.0
    logger.info("analysis_worker_started")
    while not stop.is_set():
        try:
            loop_time = asyncio.get_running_loop().time()
            if loop_time >= next_upload_cleanup:
                async with session_factory() as session:
                    cleanup = await cleanup_expired_uploads(session, upload_store)
                logger.info(
                    "upload_cleanup_cycle selected=%s deleted=%s failed=%s",
                    cleanup.selected,
                    cleanup.deleted,
                    cleanup.failed,
                )
                next_upload_cleanup = loop_time + settings.upload_cleanup_interval_seconds
            cycle = await run_worker_cycle(session_factory, settings)
            if not cycle.claimed:
                try:
                    await asyncio.wait_for(
                        stop.wait(), timeout=settings.analysis_worker_poll_seconds
                    )
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("analysis_worker_cycle_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.analysis_worker_poll_seconds)
            except TimeoutError:
                pass
    logger.info("analysis_worker_stopped")
