import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from time import perf_counter
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import ProviderError
from app.ai.weekly_report import WeeklyReportProvider, WeeklyReportProviderResult
from app.repositories.diet import get_profile
from app.schemas.ai import AiUsage
from app.schemas.assistant import DailyNutritionPoint
from app.schemas.weekly_report import (
    WeeklyMetricChanges,
    WeeklyPeriodSummary,
    WeeklyReportFacts,
    WeeklyReportRequest,
    WeeklyReportResponse,
)
from app.services.ai import AiCallTelemetry, estimate_cost
from app.services.assistant_tools import get_nutrition_points
from app.services.diet import calculate_daily_targets

Sleep = Callable[[float], Awaitable[None]]
METRICS = ("kcal", "protein", "fat", "carbs", "sugar", "sodium", "caffeine")


@dataclass(frozen=True)
class WeeklyReportExecution:
    response: WeeklyReportResponse
    telemetry: AiCallTelemetry


def _period_summary(
    start_date: date,
    end_date: date,
    points: list[DailyNutritionPoint],
    recorded_days: int,
) -> WeeklyPeriodSummary:
    averages = {
        metric: round(sum(getattr(point, metric) for point in points) / 7, 2) for metric in METRICS
    }
    return WeeklyPeriodSummary(
        start_date=start_date,
        end_date=end_date,
        days_with_records=recorded_days,
        coverage_ratio=round(recorded_days / 7, 4),
        total_kcal=round(sum(point.kcal for point in points), 2),
        average_kcal=averages["kcal"],
        average_protein=averages["protein"],
        average_fat=averages["fat"],
        average_carbs=averages["carbs"],
        average_sugar=averages["sugar"],
        average_sodium=averages["sodium"],
        average_caffeine=averages["caffeine"],
    )


def _percent_change(current: float, previous: float, available: bool) -> float | None:
    if not available or previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


async def build_weekly_report_facts(
    session: AsyncSession,
    user_id: UUID,
    end_date: date,
) -> WeeklyReportFacts:
    current_start = end_date - timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    current_points, current_recorded = await get_nutrition_points(
        session, user_id, current_start, end_date
    )
    previous_points, previous_recorded = await get_nutrition_points(
        session, user_id, previous_start, previous_end
    )
    current = _period_summary(current_start, end_date, current_points, current_recorded)
    previous = _period_summary(previous_start, previous_end, previous_points, previous_recorded)
    comparison_available = current_recorded >= 4 and previous_recorded >= 4
    changes = WeeklyMetricChanges(
        **{
            f"average_{metric}_percent": _percent_change(
                getattr(current, f"average_{metric}"),
                getattr(previous, f"average_{metric}"),
                comparison_available,
            )
            for metric in METRICS
        }
    )
    profile = await get_profile(session, user_id)
    targets = calculate_daily_targets(profile) if profile is not None else None
    return WeeklyReportFacts(
        current=current,
        previous=previous,
        targets=targets,
        comparison_available=comparison_available,
        changes=changes,
    )


def _fingerprint(facts: WeeklyReportFacts) -> str:
    canonical = json.dumps(
        facts.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fallback_warning(error: ProviderError | None) -> str:
    if error and error.code in {"http_401", "http_403"}:
        return "模型凭证无效或缺少权限，本次已使用本地周报；请检查 AI 服务设置。"
    if error and error.code == "http_429":
        return "模型服务当前限流，本次已使用本地周报；请稍后重试并检查额度。"
    return "真实模型暂时不可用，本次已使用本地周报，文字结论按固定规则生成。"


def _data_warnings(facts: WeeklyReportFacts) -> list[str]:
    warnings: list[str] = []
    if facts.current.days_with_records < 4:
        warnings.append("本周有效记录少于 4 天，不展示周环比，统计可能低估实际摄入。")
    elif facts.current.days_with_records < 7:
        warnings.append("本周记录不完整，日均值按完整 7 天计算，可能低估实际摄入。")
    if facts.previous.days_with_records < 4:
        warnings.append("上周有效记录少于 4 天，暂不生成周环比。")
    if facts.targets is None:
        warnings.append("尚未设置个人资料，本周报不会判断是否达到个性化目标。")
    return warnings


async def generate_weekly_report(
    session: AsyncSession,
    user_id: UUID,
    request: WeeklyReportRequest,
    primary: WeeklyReportProvider,
    *,
    fallback: WeeklyReportProvider | None = None,
    max_attempts: int = 2,
    retry_delay_seconds: float = 0.15,
    input_price_per_million: Decimal | None = None,
    output_price_per_million: Decimal | None = None,
    sleep: Sleep = asyncio.sleep,
) -> WeeklyReportExecution:
    facts = await build_weekly_report_facts(session, user_id, request.end_date)
    started_at = perf_counter()
    attempts = 0
    primary_error: ProviderError | None = None
    result: WeeklyReportProviderResult | None = None
    used_provider = primary
    fallback_used = False

    for attempt in range(max_attempts):
        attempts += 1
        try:
            result = await primary.generate(facts)
            break
        except ProviderError as error:
            primary_error = error
            if not error.retryable or attempt + 1 >= max_attempts:
                break
            await sleep(retry_delay_seconds * (2**attempt))

    if result is None and fallback is not None:
        attempts += 1
        fallback_used = True
        used_provider = fallback
        result = await fallback.generate(facts)
    if result is None:
        if primary_error is not None:
            raise primary_error
        raise ProviderError("provider_failed", "weekly report returned no result", retryable=False)

    latency_ms = max(round((perf_counter() - started_at) * 1000), 0)
    total_tokens = result.input_tokens + result.output_tokens
    cost = estimate_cost(
        result.input_tokens,
        result.output_tokens,
        input_price_per_million,
        output_price_per_million,
    )
    warnings = _data_warnings(facts)
    if fallback_used:
        warnings.insert(0, _fallback_warning(primary_error))
    response = WeeklyReportResponse(
        provider=used_provider.name,
        model=result.model,
        prompt_version=used_provider.prompt_version,
        fallback_used=fallback_used,
        latency_ms=latency_ms,
        usage=AiUsage(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
        ),
        data_fingerprint=_fingerprint(facts),
        facts=facts,
        narrative=result.narrative,
        warnings=warnings,
    )
    telemetry = AiCallTelemetry(
        provider=used_provider.name,
        model=result.model,
        status="fallback" if fallback_used else "success",
        fallback_used=fallback_used,
        latency_ms=latency_ms,
        attempt_count=attempts,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        error_code=primary_error.code if fallback_used and primary_error else None,
    )
    return WeeklyReportExecution(response=response, telemetry=telemetry)
