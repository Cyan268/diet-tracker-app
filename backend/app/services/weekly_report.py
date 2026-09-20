import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from time import perf_counter
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import ProviderError
from app.ai.weekly_report import WeeklyReportProvider, WeeklyReportProviderResult
from app.models import FoodLog
from app.repositories.diet import get_profile
from app.schemas.ai import AiUsage
from app.schemas.assistant import DailyNutritionPoint
from app.schemas.diet import MealType
from app.schemas.weekly_report import (
    WeeklyFactReference,
    WeeklyMealStructureItem,
    WeeklyMetricChanges,
    WeeklyPeriodSummary,
    WeeklyReportFacts,
    WeeklyReportNarrative,
    WeeklyReportRequest,
    WeeklyReportResponse,
    WeeklyTargetAdherence,
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
    totals = {metric: sum(getattr(point, metric) for point in points) for metric in METRICS}
    averages = {metric: round(totals[metric] / 7, 2) for metric in METRICS}
    recorded_day_averages = {
        metric: round(totals[metric] / recorded_days, 2) if recorded_days else 0
        for metric in METRICS
    }
    return WeeklyPeriodSummary(
        start_date=start_date,
        end_date=end_date,
        days_with_records=recorded_days,
        coverage_ratio=round(recorded_days / 7, 4),
        total_kcal=round(totals["kcal"], 2),
        average_kcal=averages["kcal"],
        average_protein=averages["protein"],
        average_fat=averages["fat"],
        average_carbs=averages["carbs"],
        average_sugar=averages["sugar"],
        average_sodium=averages["sodium"],
        average_caffeine=averages["caffeine"],
        recorded_day_average_kcal=recorded_day_averages["kcal"],
        recorded_day_average_protein=recorded_day_averages["protein"],
        recorded_day_average_fat=recorded_day_averages["fat"],
        recorded_day_average_carbs=recorded_day_averages["carbs"],
        recorded_day_average_sugar=recorded_day_averages["sugar"],
        recorded_day_average_sodium=recorded_day_averages["sodium"],
        recorded_day_average_caffeine=recorded_day_averages["caffeine"],
    )


def _percent_change(current: float, previous: float, available: bool) -> float | None:
    if not available or previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


async def _meal_structure(
    session: AsyncSession,
    user_id: UUID,
    start_date: date,
    end_date: date,
) -> list[WeeklyMealStructureItem]:
    rows = (
        await session.execute(
            select(
                FoodLog.meal_type,
                func.count(FoodLog.id),
                func.coalesce(func.sum(FoodLog.kcal), 0),
            )
            .where(
                FoodLog.user_id == user_id,
                FoodLog.log_date >= start_date,
                FoodLog.log_date <= end_date,
            )
            .group_by(FoodLog.meal_type)
        )
    ).all()
    by_meal = {str(row[0]): (int(row[1]), float(row[2])) for row in rows}
    total_kcal = sum(kcal for _, kcal in by_meal.values())
    return [
        WeeklyMealStructureItem(
            meal_type=meal_type,
            log_count=by_meal.get(meal_type.value, (0, 0))[0],
            total_kcal=round(by_meal.get(meal_type.value, (0, 0))[1], 2),
            kcal_ratio=(
                round(by_meal.get(meal_type.value, (0, 0))[1] / total_kcal, 4) if total_kcal else 0
            ),
        )
        for meal_type in MealType
    ]


def _target_adherence(
    points: list[DailyNutritionPoint],
    recorded_days: int,
    target_kcal: int | None,
) -> WeeklyTargetAdherence:
    available = target_kcal is not None and recorded_days >= 4
    if not available or target_kcal is None:
        return WeeklyTargetAdherence(
            available=False,
            assessment_days=recorded_days,
            kcal_within_target_days=None,
        )
    lower = target_kcal * 0.9
    upper = target_kcal * 1.1
    recorded_points = [point for point in points if point.has_records]
    return WeeklyTargetAdherence(
        available=True,
        assessment_days=recorded_days,
        kcal_within_target_days=sum(lower <= point.kcal <= upper for point in recorded_points),
    )


def _fact_references(
    current: WeeklyPeriodSummary,
    previous: WeeklyPeriodSummary,
    changes: WeeklyMetricChanges,
    targets: object | None,
    meal_structure: list[WeeklyMealStructureItem],
    target_adherence: WeeklyTargetAdherence,
) -> list[WeeklyFactReference]:
    references = [
        WeeklyFactReference(
            id="current.days_with_records",
            label="本周有效记录天数",
            display_value=f"{current.days_with_records}/7 天",
            source="derived",
            calculation="存在至少一条 food_logs 快照的业务日期数 / 固定 7 个自然日",
        ),
        WeeklyFactReference(
            id="current.coverage_ratio",
            label="本周记录覆盖率",
            display_value=f"{current.coverage_ratio * 100:.1f}%",
            source="derived",
            calculation="本周有效记录天数 / 7，显示时保留 1 位小数",
        ),
        WeeklyFactReference(
            id="current.total_kcal",
            label="本周已记录总热量",
            display_value=f"{current.total_kcal:.2f} kcal",
            source="food_log_snapshots",
            calculation="本周 log_date 范围内 food_logs.kcal 快照求和",
        ),
        WeeklyFactReference(
            id="current.average_kcal",
            label="本周自然日日均热量",
            display_value=f"{current.average_kcal:.2f} kcal/自然日",
            source="derived",
            calculation="本周已记录总热量 / 固定 7 个自然日，保留 2 位小数",
        ),
        WeeklyFactReference(
            id="current.recorded_day_average_kcal",
            label="本周记录日日均热量",
            display_value=f"{current.recorded_day_average_kcal:.2f} kcal/记录日",
            source="derived",
            calculation="本周已记录总热量 / 有效记录天数；无记录时为 0",
        ),
    ]
    units = {
        "protein": "g/自然日",
        "fat": "g/自然日",
        "carbs": "g/自然日",
        "sugar": "g/自然日",
        "sodium": "mg/自然日",
        "caffeine": "mg/自然日",
    }
    labels = {
        "protein": "蛋白质",
        "fat": "脂肪",
        "carbs": "碳水",
        "sugar": "糖",
        "sodium": "钠",
        "caffeine": "咖啡因",
    }
    for metric in METRICS[1:]:
        references.append(
            WeeklyFactReference(
                id=f"current.average_{metric}",
                label=f"本周自然日日均{labels[metric]}",
                display_value=f"{getattr(current, f'average_{metric}'):.2f} {units[metric]}",
                source="derived",
                calculation=f"本周 {metric} 快照求和 / 固定 7 个自然日，保留 2 位小数",
            )
        )
    references.extend(
        [
            WeeklyFactReference(
                id="previous.days_with_records",
                label="上周有效记录天数",
                display_value=f"{previous.days_with_records}/7 天",
                source="derived",
                calculation="上周存在至少一条 food_logs 快照的业务日期数 / 7",
            ),
            WeeklyFactReference(
                id="previous.average_kcal",
                label="上周自然日日均热量",
                display_value=f"{previous.average_kcal:.2f} kcal/自然日",
                source="derived",
                calculation="上周已记录总热量 / 固定 7 个自然日，保留 2 位小数",
            ),
        ]
    )
    if changes.average_kcal_percent is not None:
        direction = (
            "基本持平"
            if abs(changes.average_kcal_percent) < 5
            else ("增加" if changes.average_kcal_percent >= 0 else "减少")
        )
        references.append(
            WeeklyFactReference(
                id="changes.average_kcal_percent",
                label="自然日日均热量周环比",
                display_value=f"{direction} {abs(changes.average_kcal_percent):.1f}%",
                source="derived",
                calculation="(本周自然日日均 - 上周自然日日均) / 上周自然日日均 × 100",
            )
        )
    if targets is not None:
        references.append(
            WeeklyFactReference(
                id="targets.profile_available",
                label="个性化目标状态",
                display_value="已设置",
                source="user_profile",
                calculation="由当前用户资料确定性计算，未用于记录不足时的达标判断",
            )
        )
    for item in meal_structure:
        references.append(
            WeeklyFactReference(
                id=f"structure.{item.meal_type.value}.kcal_ratio",
                label=f"本周 {item.meal_type.value} 热量占比",
                display_value=f"{item.kcal_ratio * 100:.1f}%",
                source="derived",
                calculation="该餐次 food_logs.kcal 快照和 / 本周全部 food_logs.kcal 快照和",
            )
        )
    if target_adherence.available:
        references.append(
            WeeklyFactReference(
                id="target.kcal_within_range_days",
                label="本周热量目标范围内记录天数",
                display_value=(
                    f"{target_adherence.kcal_within_target_days}/"
                    f"{target_adherence.assessment_days} 记录日"
                ),
                source="derived",
                calculation="仅记录日；每日 kcal 位于当前估算目标 ±10%，且本周至少记录 4 天",
            )
        )
    return references


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
    meal_structure = await _meal_structure(session, user_id, current_start, end_date)
    target_adherence = _target_adherence(
        current_points,
        current_recorded,
        targets.kcal if targets is not None else None,
    )
    return WeeklyReportFacts(
        current=current,
        previous=previous,
        targets=targets,
        comparison_available=comparison_available,
        changes=changes,
        meal_structure=meal_structure,
        target_adherence=target_adherence,
        fact_references=_fact_references(
            current,
            previous,
            changes,
            targets,
            meal_structure,
            target_adherence,
        ),
    )


NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _number_variants(display_value: str) -> set[str]:
    variants: set[str] = set()
    for token in NUMBER_PATTERN.findall(display_value):
        value = Decimal(token)
        variants.add(str(value.normalize()))
        variants.update(format(value, f".{places}f") for places in range(3))
    return variants


def _narrative_text(narrative: WeeklyReportNarrative, path: str) -> str:
    if path == "headline":
        return narrative.headline
    if path == "summary":
        return narrative.summary
    index = int(path.rsplit(".", 1)[1])
    return narrative.highlights[index]


def validate_narrative_facts(facts: WeeklyReportFacts, result: WeeklyReportProviderResult) -> None:
    references = {reference.id: reference for reference in facts.fact_references}
    for citation in result.narrative.citations:
        missing = sorted(set(citation.fact_ids) - references.keys())
        if missing:
            raise ProviderError(
                "fact_validation_failed",
                f"weekly narrative cited unknown facts: {', '.join(missing)}",
                retryable=False,
            )
        supported_numbers = {
            number
            for fact_id in citation.fact_ids
            for number in _number_variants(references[fact_id].display_value)
        }
        claimed_numbers = {
            str(Decimal(token).normalize())
            for token in NUMBER_PATTERN.findall(_narrative_text(result.narrative, citation.path))
        }
        if claimed_numbers - supported_numbers:
            raise ProviderError(
                "fact_validation_failed",
                f"weekly narrative numbers are not supported at {citation.path}",
                retryable=False,
            )
        text = _narrative_text(result.narrative, citation.path)
        for fact_id in citation.fact_ids:
            display_value = references[fact_id].display_value
            expected_direction = next(
                (direction for direction in ("增加", "减少") if direction in display_value),
                None,
            )
            if expected_direction is not None:
                opposite = "减少" if expected_direction == "增加" else "增加"
                if expected_direction not in text or opposite in text:
                    raise ProviderError(
                        "fact_validation_failed",
                        f"weekly narrative direction is not supported at {citation.path}",
                        retryable=False,
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
    if error and error.code == "fact_validation_failed":
        return "模型叙事未通过事实引用校验，本次已使用可追溯的本地规则周报。"
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
            candidate = await primary.generate(facts)
            validate_narrative_facts(facts, candidate)
            result = candidate
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
        validate_narrative_facts(facts, result)
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
