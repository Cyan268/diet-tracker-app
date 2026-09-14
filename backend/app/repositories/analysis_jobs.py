from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisAttempt, AnalysisJob


@dataclass(frozen=True)
class ClaimedAnalysisJob:
    job: AnalysisJob
    attempt: AnalysisAttempt


async def database_now(session: AsyncSession) -> datetime:
    return await session.scalar(select(func.clock_timestamp()))


async def claim_next_job(
    session: AsyncSession,
    *,
    lease_seconds: int,
    max_attempts: int,
    global_concurrency: int = 32,
) -> ClaimedAnalysisJob | None:
    # Serialize only the short claim transaction. The non-blocking advisory lock
    # keeps multiple Worker processes from racing past the global quota.
    claim_lock_acquired = await session.scalar(select(func.pg_try_advisory_xact_lock(704_201)))
    if not claim_lock_acquired:
        return None
    now = func.clock_timestamp()
    running = await session.scalar(
        select(func.count())
        .select_from(AnalysisJob)
        .where(
            AnalysisJob.status == "running",
            AnalysisJob.lease_expires_at > now,
        )
    )
    if (running or 0) >= global_concurrency:
        return None
    job = await session.scalar(
        select(AnalysisJob)
        .where(
            or_(
                AnalysisJob.status == "queued",
                (AnalysisJob.status == "retry_wait")
                & (AnalysisJob.next_attempt_at.is_(None) | (AnalysisJob.next_attempt_at <= now)),
            ),
            AnalysisJob.input_expires_at > now,
            AnalysisJob.attempt_count < max_attempts,
        )
        .order_by(
            func.coalesce(AnalysisJob.next_attempt_at, AnalysisJob.created_at),
            AnalysisJob.created_at,
            AnalysisJob.id,
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None

    lease_token = uuid4()
    current_time = await database_now(session)
    job.status = "running"
    job.attempt_count += 1
    job.next_attempt_at = None
    job.lease_token = lease_token
    job.lease_expires_at = current_time + timedelta(seconds=lease_seconds)
    job.failure_code = None
    attempt = AnalysisAttempt(
        job_id=job.id,
        attempt_number=job.attempt_count,
        lease_token=lease_token,
        phase="claimed",
        status="running",
        provider=job.provider,
        model=job.model,
        cost_status="unknown",
    )
    session.add(attempt)
    await session.flush()
    return ClaimedAnalysisJob(job=job, attempt=attempt)


async def lock_valid_lease(
    session: AsyncSession,
    job_id: UUID,
    lease_token: UUID,
) -> tuple[AnalysisJob, AnalysisAttempt] | None:
    job = await session.scalar(
        select(AnalysisJob)
        .where(
            AnalysisJob.id == job_id,
            AnalysisJob.status == "running",
            AnalysisJob.lease_token == lease_token,
            AnalysisJob.lease_expires_at > func.clock_timestamp(),
        )
        .with_for_update()
    )
    if job is None:
        return None
    attempt = await session.scalar(
        select(AnalysisAttempt).where(
            AnalysisAttempt.job_id == job_id,
            AnalysisAttempt.lease_token == lease_token,
            AnalysisAttempt.status == "running",
        )
    )
    if attempt is None:
        return None
    return job, attempt


async def mark_dispatch_started(
    session: AsyncSession,
    job_id: UUID,
    lease_token: UUID,
) -> bool:
    locked = await lock_valid_lease(session, job_id, lease_token)
    if locked is None:
        return False
    _, attempt = locked
    attempt.phase = "dispatching"
    attempt.dispatch_started_at = await database_now(session)
    await session.flush()
    return True


async def mark_response_received(
    session: AsyncSession,
    job_id: UUID,
    lease_token: UUID,
) -> bool:
    locked = await lock_valid_lease(session, job_id, lease_token)
    if locked is None:
        return False
    _, attempt = locked
    attempt.phase = "response_received"
    attempt.response_received_at = await database_now(session)
    await session.flush()
    return True


async def renew_lease(
    session: AsyncSession,
    job_id: UUID,
    lease_token: UUID,
    *,
    lease_seconds: int,
) -> bool:
    current_time = await database_now(session)
    result = await session.execute(
        update(AnalysisJob)
        .where(
            AnalysisJob.id == job_id,
            AnalysisJob.status == "running",
            AnalysisJob.lease_token == lease_token,
            AnalysisJob.lease_expires_at > func.clock_timestamp(),
        )
        .values(lease_expires_at=current_time + timedelta(seconds=lease_seconds))
    )
    return result.rowcount == 1


async def recover_expired_jobs(
    session: AsyncSession,
    *,
    max_attempts: int,
    limit: int = 100,
) -> dict[str, int]:
    current_time = await database_now(session)
    unclaimable = (
        await session.scalars(
            select(AnalysisJob)
            .where(
                AnalysisJob.status.in_(("queued", "retry_wait")),
                or_(
                    AnalysisJob.input_expires_at <= func.clock_timestamp(),
                    AnalysisJob.attempt_count >= max_attempts,
                ),
            )
            .order_by(AnalysisJob.created_at, AnalysisJob.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    result = {"retry_wait": 0, "failed": 0, "unknown": 0}
    for job in unclaimable:
        job.status = "failed"
        job.failure_code = (
            "analysis_input_expired"
            if job.input_expires_at <= current_time
            else "analysis_attempts_exhausted"
        )
        job.next_attempt_at = None
        job.completed_at = current_time
        result["failed"] += 1

    jobs = (
        await session.scalars(
            select(AnalysisJob)
            .where(
                AnalysisJob.status == "running",
                AnalysisJob.lease_expires_at <= func.clock_timestamp(),
            )
            .order_by(AnalysisJob.lease_expires_at, AnalysisJob.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for job in jobs:
        attempt = await session.scalar(
            select(AnalysisAttempt).where(
                AnalysisAttempt.job_id == job.id,
                AnalysisAttempt.lease_token == job.lease_token,
            )
        )
        if attempt is None:
            job.status = "unknown"
            job.failure_code = "attempt_record_missing"
            result["unknown"] += 1
        elif attempt.phase == "claimed":
            can_retry = job.attempt_count < max_attempts and job.input_expires_at > current_time
            job.status = "retry_wait" if can_retry else "failed"
            job.failure_code = "worker_lost_before_dispatch"
            job.next_attempt_at = current_time if can_retry else None
            attempt.status = job.status
            attempt.phase = "finished"
            attempt.error_code = job.failure_code
            attempt.retryable = can_retry
            attempt.completed_at = current_time
            result[job.status] += 1
        else:
            job.status = "unknown"
            job.failure_code = "worker_lost_after_dispatch"
            attempt.status = "unknown"
            attempt.phase = "finished"
            attempt.error_code = job.failure_code
            attempt.retryable = False
            attempt.completed_at = current_time
            result["unknown"] += 1
        job.lease_token = None
        job.lease_expires_at = None
    await session.flush()
    return result


async def cancel_job(
    session: AsyncSession,
    job_id: UUID,
    user_id: UUID,
) -> bool:
    job = await session.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.id == job_id, AnalysisJob.user_id == user_id)
        .with_for_update()
    )
    if job is None or job.status in {"succeeded", "failed", "unknown", "cancelled"}:
        return False
    current_time = await database_now(session)
    if job.lease_token is not None:
        attempt = await session.scalar(
            select(AnalysisAttempt).where(
                AnalysisAttempt.job_id == job.id,
                AnalysisAttempt.lease_token == job.lease_token,
                AnalysisAttempt.status == "running",
            )
        )
        if attempt is not None:
            attempt.phase = "finished"
            attempt.status = "cancelled"
            attempt.error_code = "cancelled_by_user"
            attempt.retryable = False
            attempt.completed_at = current_time
    job.status = "cancelled"
    job.failure_code = "cancelled_by_user"
    job.completed_at = current_time
    job.next_attempt_at = None
    job.lease_token = None
    job.lease_expires_at = None
    await session.flush()
    return True
