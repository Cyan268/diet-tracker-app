from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import ProviderResult
from app.models import AnalysisDraft, AnalysisEntity
from app.repositories.analysis_jobs import database_now, lock_valid_lease
from app.schemas.ai import FoodTextAnalyzeRequest
from app.services.ai import estimate_cost
from app.services.food_matching import match_visible_foods


def _candidate_payload(candidate) -> dict[str, object]:
    payload = asdict(candidate)
    payload["food_item_id"] = str(candidate.food_item_id)
    return payload


async def complete_job_success(
    session: AsyncSession,
    *,
    job_id: UUID,
    lease_token: UUID,
    request: FoodTextAnalyzeRequest,
    result: ProviderResult,
    draft_ttl_minutes: int,
    input_price_per_million: Decimal | None = None,
    output_price_per_million: Decimal | None = None,
) -> AnalysisDraft | None:
    locked = await lock_valid_lease(session, job_id, lease_token)
    if locked is None:
        return None
    job, attempt = locked
    current_time = await database_now(session)
    draft = AnalysisDraft(
        job_id=job.id,
        user_id=job.user_id,
        status="review",
        version=1,
        log_date=request.log_date,
        result_schema_version=job.result_schema_version,
        expires_at=current_time + timedelta(minutes=draft_ttl_minutes),
    )
    session.add(draft)
    await session.flush()

    for position, parsed in enumerate(result.entities):
        decision = await match_visible_foods(
            session,
            job.user_id,
            parsed.normalized_name,
        )
        selected = next(
            (
                candidate
                for candidate in decision.candidates
                if candidate.food_item_id == decision.preselected_food_item_id
            ),
            None,
        )
        session.add(
            AnalysisEntity(
                draft_id=draft.id,
                position=position,
                raw_name=parsed.raw_name,
                normalized_name=parsed.normalized_name,
                amount=Decimal(str(parsed.amount)),
                unit=parsed.unit,
                meal_type=parsed.meal_type.value,
                confidence=Decimal(str(parsed.confidence)),
                needs_review=parsed.needs_review or decision.status != "review",
                matched_food_id=selected.food_item_id if selected else None,
                catalog_revision=selected.catalog_revision if selected else None,
                candidates=[_candidate_payload(candidate) for candidate in decision.candidates],
            )
        )

    total_tokens = result.input_tokens + result.output_tokens
    attempt.phase = "finished"
    attempt.status = "succeeded"
    attempt.response_received_at = attempt.response_received_at or current_time
    attempt.completed_at = current_time
    attempt.input_tokens = result.input_tokens
    attempt.output_tokens = result.output_tokens
    attempt.total_tokens = total_tokens
    attempt.token_usage_source = "provider"
    attempt.provider_request_id = result.provider_request_id
    attempt.estimated_cost_usd = estimate_cost(
        result.input_tokens,
        result.output_tokens,
        input_price_per_million,
        output_price_per_million,
    )
    attempt.cost_status = "estimated" if attempt.estimated_cost_usd is not None else "unknown"
    job.status = "succeeded"
    job.completed_at = current_time
    job.failure_code = None
    job.lease_token = None
    job.lease_expires_at = None
    await session.flush()
    return draft


async def complete_job_failure(
    session: AsyncSession,
    *,
    job_id: UUID,
    lease_token: UUID,
    error_code: str,
    retryable: bool,
    outcome_unknown: bool,
    max_attempts: int,
    retry_delay_seconds: float,
) -> str | None:
    locked = await lock_valid_lease(session, job_id, lease_token)
    if locked is None:
        return None
    job, attempt = locked
    current_time = await database_now(session)
    can_retry = (
        retryable
        and not outcome_unknown
        and job.attempt_count < max_attempts
        and job.input_expires_at > current_time
    )
    if outcome_unknown:
        status = "unknown"
    elif can_retry:
        status = "retry_wait"
    else:
        status = "failed"

    attempt.phase = "finished"
    attempt.status = status
    attempt.error_code = error_code
    attempt.retryable = can_retry
    attempt.completed_at = current_time
    job.status = status
    job.failure_code = error_code
    job.next_attempt_at = (
        current_time + timedelta(seconds=retry_delay_seconds) if can_retry else None
    )
    job.completed_at = current_time if status in {"unknown", "failed"} else None
    job.lease_token = None
    job.lease_expires_at = None
    await session.flush()
    return status
