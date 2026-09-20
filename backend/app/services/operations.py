import json
import stat
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.runtime_metrics import runtime_metrics
from app.models import AiCallLog, AnalysisAttempt, AnalysisJob
from app.schemas.operations import HostSnapshot, OperationalAlert, OperationalMetricsResponse

MAX_HOST_SNAPSHOT_BYTES = 64 * 1024


def read_host_snapshot(path: Path | None) -> tuple[HostSnapshot | None, str | None]:
    if path is None:
        return None, "not_configured"
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return None, "unsafe_file_type"
        if metadata.st_size > MAX_HOST_SNAPSHOT_BYTES:
            return None, "file_too_large"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return HostSnapshot.model_validate(payload), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError, TypeError):
        return None, "invalid"


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _alert(
    *,
    code: str,
    firing: bool | None,
    severity: str,
    observed: int | float | Decimal | None,
    threshold: str,
    duration: str,
    minimum_samples: int,
    recovery_condition: str,
) -> OperationalAlert:
    return OperationalAlert(
        code=code,
        state="unknown" if firing is None else ("firing" if firing else "ok"),
        severity=severity,
        observed=observed,
        threshold=threshold,
        duration=duration,
        minimum_samples=minimum_samples,
        route="operator",
        runbook=f"docs/upgrade/runbooks/{code}.md",
        recovery_condition=recovery_condition,
    )


async def collect_operational_metrics(
    session: AsyncSession,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> OperationalMetricsResponse:
    current_time = now or datetime.now(UTC)
    recent_start = current_time - timedelta(minutes=15)
    month_start = _month_start(current_time)
    host_snapshot, host_snapshot_error = read_host_snapshot(settings.operations_host_snapshot_path)

    status_rows = (
        await session.execute(
            select(AnalysisJob.status, func.count(AnalysisJob.id)).group_by(AnalysisJob.status)
        )
    ).all()
    job_counts = {status: int(count) for status, count in status_rows}
    oldest_created = await session.scalar(
        select(func.min(AnalysisJob.created_at)).where(
            AnalysisJob.status.in_(("queued", "retry_wait"))
        )
    )
    oldest_age_seconds = (
        max(int((current_time - _utc(oldest_created)).total_seconds()), 0)
        if oldest_created is not None
        else 0
    )

    attempts = (
        await session.scalars(
            select(AnalysisAttempt).where(AnalysisAttempt.started_at >= recent_start)
        )
    ).all()
    completed_attempts = [item for item in attempts if item.completed_at is not None]
    durations_ms = [
        max(int((_utc(item.completed_at) - _utc(item.started_at)).total_seconds() * 1000), 0)
        for item in completed_attempts
    ]
    error_counts: dict[str, int] = {}
    for attempt in attempts:
        if attempt.error_code:
            error_counts[attempt.error_code] = error_counts.get(attempt.error_code, 0) + 1
    failed_attempts = sum(item.status in {"failed", "unknown"} for item in attempts)
    unknown_results = job_counts.get("unknown", 0)
    lease_recoveries = sum(
        count
        for code, count in error_counts.items()
        if code in {"worker_lost_before_dispatch", "worker_lost_after_dispatch"}
    )

    direct_ai_row = (
        await session.execute(
            select(
                func.count(AiCallLog.id),
                func.coalesce(func.sum(AiCallLog.total_tokens), 0),
                func.coalesce(func.sum(AiCallLog.estimated_cost_usd), 0),
                func.coalesce(func.sum(case((AiCallLog.fallback_used.is_(True), 1), else_=0)), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (AiCallLog.total_tokens > 0)
                                & (AiCallLog.estimated_cost_usd.is_(None)),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(AiCallLog.created_at >= month_start)
        )
    ).one()
    worker_ai_row = (
        await session.execute(
            select(
                func.count(AnalysisAttempt.id),
                func.coalesce(func.sum(AnalysisAttempt.total_tokens), 0),
                func.coalesce(func.sum(AnalysisAttempt.estimated_cost_usd), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (AnalysisAttempt.total_tokens > 0)
                                & (AnalysisAttempt.estimated_cost_usd.is_(None)),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(AnalysisAttempt.started_at >= month_start)
        )
    ).one()
    grouped_ai = (
        await session.execute(
            select(
                AnalysisJob.provider,
                AnalysisJob.model,
                AnalysisJob.prompt_version,
                AnalysisAttempt.status,
                func.count(AnalysisAttempt.id),
            )
            .join(AnalysisAttempt, AnalysisAttempt.job_id == AnalysisJob.id)
            .where(AnalysisAttempt.started_at >= recent_start)
            .group_by(
                AnalysisJob.provider,
                AnalysisJob.model,
                AnalysisJob.prompt_version,
                AnalysisAttempt.status,
            )
        )
    ).all()
    grouped_direct_ai = (
        await session.execute(
            select(
                AiCallLog.provider,
                AiCallLog.model,
                AiCallLog.operation,
                AiCallLog.status,
                func.count(AiCallLog.id),
            )
            .where(AiCallLog.created_at >= recent_start)
            .group_by(
                AiCallLog.provider,
                AiCallLog.model,
                AiCallLog.operation,
                AiCallLog.status,
            )
        )
    ).all()
    direct_user_costs = (
        await session.execute(
            select(AiCallLog.user_id, func.coalesce(func.sum(AiCallLog.estimated_cost_usd), 0))
            .where(AiCallLog.created_at >= month_start)
            .group_by(AiCallLog.user_id)
        )
    ).all()
    worker_user_costs = (
        await session.execute(
            select(
                AnalysisJob.user_id,
                func.coalesce(func.sum(AnalysisAttempt.estimated_cost_usd), 0),
            )
            .join(AnalysisAttempt, AnalysisAttempt.job_id == AnalysisJob.id)
            .where(AnalysisAttempt.started_at >= month_start)
            .group_by(AnalysisJob.user_id)
        )
    ).all()
    per_user_costs: dict[object, Decimal] = {}
    for user_id, cost in [*direct_user_costs, *worker_user_costs]:
        per_user_costs[user_id] = per_user_costs.get(user_id, Decimal(0)) + Decimal(str(cost))
    per_user_budget = settings.ai_per_user_monthly_budget_usd
    users_over_budget = (
        sum(cost >= per_user_budget for cost in per_user_costs.values())
        if per_user_budget is not None
        else None
    )
    maximum_user_budget_ratio = (
        max((cost / per_user_budget for cost in per_user_costs.values()), default=Decimal(0))
        if per_user_budget is not None
        else None
    )
    host_age_seconds: int | None = None
    memory_used_ratio: float | None = None
    disk_used_ratio: float | None = None
    unhealthy_containers: int | None = None
    backup_age_seconds: int | None = None
    if host_snapshot is not None:
        host_age_seconds = max(
            int((current_time - host_snapshot.generated_at.astimezone(UTC)).total_seconds()), 0
        )
        memory_used_ratio = round(
            1 - host_snapshot.memory_available_bytes / host_snapshot.memory_total_bytes, 4
        )
        disk_used_ratio = round(
            1 - host_snapshot.disk_free_bytes / host_snapshot.disk_total_bytes, 4
        )
        unhealthy_containers = sum(
            not item.running or item.health == "unhealthy" for item in host_snapshot.containers
        )
        if host_snapshot.backup.last_success_at is not None:
            backup_age_seconds = max(
                int(
                    (
                        current_time - host_snapshot.backup.last_success_at.astimezone(UTC)
                    ).total_seconds()
                ),
                0,
            )
    total_tokens = int(direct_ai_row[1]) + int(worker_ai_row[1])
    estimated_cost = Decimal(str(direct_ai_row[2])) + Decimal(str(worker_ai_row[2]))
    unpriced_calls = int(direct_ai_row[4]) + int(worker_ai_row[3])
    schema_failures = sum(
        count for code, count in error_counts.items() if "schema" in code or "validation" in code
    )

    alerts = [
        _alert(
            code="worker-queue-oldest",
            firing=oldest_age_seconds > 300,
            severity="warning",
            observed=oldest_age_seconds,
            threshold="> 300 seconds",
            duration="5 minutes",
            minimum_samples=1,
            recovery_condition="oldest queued job remains at or below 120 seconds for 5 minutes",
        ),
        _alert(
            code="worker-unknown-result",
            firing=unknown_results > 0,
            severity="critical",
            observed=unknown_results,
            threshold="> 0 jobs",
            duration="immediate",
            minimum_samples=1,
            recovery_condition="all unknown jobs are reconciled and the count returns to zero",
        ),
        _alert(
            code="worker-failure-rate",
            firing=(failed_attempts / len(attempts) > 0.2) if len(attempts) >= 5 else None,
            severity="warning",
            observed=round(failed_attempts / len(attempts), 4) if attempts else 0,
            threshold="> 20%",
            duration="15 minutes",
            minimum_samples=5,
            recovery_condition="failure rate is at or below 10% for 15 minutes",
        ),
        _alert(
            code="ai-unpriced-usage",
            firing=unpriced_calls > 0,
            severity="warning",
            observed=unpriced_calls,
            threshold="> 0 token-bearing calls without a configured price",
            duration="current calendar month",
            minimum_samples=1,
            recovery_condition="prices are configured or all token-bearing calls have a cost",
        ),
        _alert(
            code="ai-global-budget-warning",
            firing=(estimated_cost >= settings.ai_global_monthly_budget_usd * Decimal("0.8"))
            if settings.ai_global_monthly_budget_usd is not None
            else None,
            severity="warning",
            observed=estimated_cost,
            threshold=(
                f">= 80% of ${settings.ai_global_monthly_budget_usd} estimated monthly budget"
                if settings.ai_global_monthly_budget_usd is not None
                else "budget not configured"
            ),
            duration="current calendar month",
            minimum_samples=1,
            recovery_condition="estimated cost falls below 80% after period reset or review",
        ),
        _alert(
            code="ai-global-budget",
            firing=(estimated_cost >= settings.ai_global_monthly_budget_usd)
            if settings.ai_global_monthly_budget_usd is not None
            else None,
            severity="critical",
            observed=estimated_cost,
            threshold=(
                f">= ${settings.ai_global_monthly_budget_usd} estimated monthly cost"
                if settings.ai_global_monthly_budget_usd is not None
                else "budget not configured"
            ),
            duration="current calendar month",
            minimum_samples=1,
            recovery_condition=(
                "estimated cost is below the configured budget after period reset or review"
            ),
        ),
        _alert(
            code="ai-per-user-budget",
            firing=(users_over_budget or 0) > 0 if users_over_budget is not None else None,
            severity="warning",
            observed=users_over_budget,
            threshold=(
                f">= ${per_user_budget} estimated monthly cost for any user"
                if per_user_budget is not None
                else "budget not configured"
            ),
            duration="current calendar month",
            minimum_samples=1,
            recovery_condition="no user remains at or above the configured estimate",
        ),
        _alert(
            code="host-snapshot-stale",
            firing=(host_snapshot_error is not None or (host_age_seconds or 0) > 600)
            if settings.operations_host_snapshot_path is not None
            else None,
            severity="critical",
            observed=host_age_seconds,
            threshold="snapshot missing, invalid, or older than 600 seconds",
            duration="10 minutes",
            minimum_samples=1,
            recovery_condition="a valid snapshot remains at most 300 seconds old",
        ),
        _alert(
            code="host-memory-pressure",
            firing=host_snapshot.memory_pressure_active if host_snapshot is not None else None,
            severity="warning",
            observed=memory_used_ratio,
            threshold=">= 85% memory used",
            duration="confirm on two consecutive 5-minute snapshots",
            minimum_samples=2,
            recovery_condition="memory used remains below 75% for two snapshots",
        ),
        _alert(
            code="host-disk-pressure",
            firing=disk_used_ratio >= 0.9 if disk_used_ratio is not None else None,
            severity="critical",
            observed=disk_used_ratio,
            threshold=">= 90% disk used",
            duration="immediate",
            minimum_samples=1,
            recovery_condition="disk used is below 80%",
        ),
        _alert(
            code="container-unhealthy",
            firing=host_snapshot.container_unhealthy_active if host_snapshot is not None else None,
            severity="critical",
            observed=unhealthy_containers,
            threshold="> 0 stopped or unhealthy required containers",
            duration="two consecutive collection cycles",
            minimum_samples=2,
            recovery_condition="all required containers are running and not unhealthy",
        ),
        _alert(
            code="backup-stale",
            firing=(
                host_snapshot.backup.status != "verified"
                or backup_age_seconds is None
                or backup_age_seconds > 129600
            )
            if host_snapshot is not None
            else None,
            severity="critical",
            observed=backup_age_seconds,
            threshold="no verified backup within 36 hours",
            duration="36 hours",
            minimum_samples=1,
            recovery_condition="a new verified backup is recorded",
        ),
    ]

    return OperationalMetricsResponse(
        generated_at=current_time,
        privacy_contract={
            "contains_user_ids": False,
            "contains_request_ids": False,
            "contains_raw_urls": False,
            "contains_food_text": False,
            "contains_credentials": False,
            "bounded_labels": [
                "method",
                "endpoint_function",
                "status_code",
                "provider",
                "model",
                "prompt_version",
                "job_status",
                "error_code",
            ],
        },
        runtime=runtime_metrics.snapshot(),
        worker={
            "window_minutes": 15,
            "jobs_by_status": job_counts,
            "oldest_queued_age_seconds": oldest_age_seconds,
            "attempts": len(attempts),
            "completed_attempts": len(completed_attempts),
            "average_execution_ms": (
                round(sum(durations_ms) / len(durations_ms), 2) if durations_ms else 0
            ),
            "lease_recoveries": lease_recoveries,
            "unknown_results": unknown_results,
            "errors_by_code": dict(sorted(error_counts.items())),
        },
        host={
            "configured": settings.operations_host_snapshot_path is not None,
            "snapshot_status": "ok" if host_snapshot is not None else host_snapshot_error,
            "snapshot_age_seconds": host_age_seconds,
            "memory_used_ratio": memory_used_ratio,
            "disk_used_ratio": disk_used_ratio,
            "memory_pressure_active": (
                host_snapshot.memory_pressure_active if host_snapshot is not None else None
            ),
            "consecutive_memory_pressure_samples": (
                host_snapshot.consecutive_memory_pressure_samples
                if host_snapshot is not None
                else None
            ),
            "consecutive_memory_recovery_samples": (
                host_snapshot.consecutive_memory_recovery_samples
                if host_snapshot is not None
                else None
            ),
            "container_unhealthy_active": (
                host_snapshot.container_unhealthy_active if host_snapshot is not None else None
            ),
            "consecutive_container_unhealthy_samples": (
                host_snapshot.consecutive_container_unhealthy_samples
                if host_snapshot is not None
                else None
            ),
            "consecutive_container_recovery_samples": (
                host_snapshot.consecutive_container_recovery_samples
                if host_snapshot is not None
                else None
            ),
            "containers": (
                [item.model_dump(mode="json") for item in host_snapshot.containers]
                if host_snapshot is not None
                else []
            ),
            "backup_status": (
                host_snapshot.backup.model_dump(mode="json") if host_snapshot is not None else None
            ),
            "backup_age_seconds": backup_age_seconds,
            "collector_errors": (
                host_snapshot.collector_errors if host_snapshot is not None else []
            ),
        },
        ai={
            "window_minutes": 15,
            "calls_by_provider_model_prompt_status": [
                {
                    "provider": provider,
                    "model": model,
                    "prompt_version": prompt_version,
                    "status": status,
                    "count": int(count),
                }
                for provider, model, prompt_version, status, count in grouped_ai
            ],
            "direct_calls_by_provider_model_operation_status": [
                {
                    "provider": provider,
                    "model": model,
                    "operation": operation,
                    "status": status,
                    "count": int(count),
                }
                for provider, model, operation, status, count in grouped_direct_ai
            ],
            "schema_failures": schema_failures,
            "fallback_calls_month": int(direct_ai_row[3]),
            "tokens_month": total_tokens,
            "estimated_cost_usd_month": estimated_cost,
            "unpriced_calls_month": unpriced_calls,
            "global_budget_usd": settings.ai_global_monthly_budget_usd,
            "per_user_budget_usd": settings.ai_per_user_monthly_budget_usd,
            "users_at_or_over_budget": users_over_budget,
            "maximum_user_budget_ratio": maximum_user_budget_ratio,
            "cost_is_estimate": True,
        },
        alerts=alerts,
        limitations=[
            "Runtime request and pool-wait metrics cover only the current API process since start.",
            (
                "Estimated AI cost is not a strict financial ceiling; provider-side budgets "
                "remain required."
            ),
            "Host metrics depend on a separately scheduled, atomic snapshot collector.",
            (
                "Sync cursor expiry is not emitted because the current ordered cursor protocol "
                "does not expire cursors."
            ),
        ],
    )
