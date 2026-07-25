from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FoodLog
from app.repositories.diet import get_profile, search_visible_foods
from app.schemas.assistant import (
    AssistantToolName,
    DailyNutritionPoint,
    FoodSearchToolItem,
    FoodSearchToolResult,
    GetTodaySummaryArguments,
    GetWeeklyTrendArguments,
    SearchFoodArguments,
    TodaySummaryToolResult,
    WeeklyTrendToolResult,
)
from app.services.diet import calculate_daily_targets


class AssistantToolError(ValueError):
    pass


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: AssistantToolName
    payload: dict[str, Any]
    summary: str


async def get_nutrition_points(
    session: AsyncSession,
    user_id: UUID,
    date_from: date,
    date_to: date,
) -> tuple[list[DailyNutritionPoint], int]:
    rows = (
        await session.execute(
            select(
                FoodLog.log_date,
                func.coalesce(func.sum(FoodLog.kcal), 0),
                func.coalesce(func.sum(FoodLog.protein), 0),
                func.coalesce(func.sum(FoodLog.fat), 0),
                func.coalesce(func.sum(FoodLog.carbs), 0),
                func.coalesce(func.sum(FoodLog.sugar), 0),
                func.coalesce(func.sum(FoodLog.sodium), 0),
                func.coalesce(func.sum(FoodLog.caffeine), 0),
            )
            .where(
                FoodLog.user_id == user_id,
                FoodLog.log_date >= date_from,
                FoodLog.log_date <= date_to,
            )
            .group_by(FoodLog.log_date)
            .order_by(FoodLog.log_date)
        )
    ).all()
    by_date = {
        row[0]: DailyNutritionPoint(
            date=row[0],
            kcal=float(row[1]),
            protein=float(row[2]),
            fat=float(row[3]),
            carbs=float(row[4]),
            sugar=float(row[5]),
            sodium=float(row[6]),
            caffeine=float(row[7]),
        )
        for row in rows
    }
    points: list[DailyNutritionPoint] = []
    for offset in range((date_to - date_from).days + 1):
        current_date = date_from + timedelta(days=offset)
        points.append(
            by_date.get(
                current_date,
                DailyNutritionPoint(
                    date=current_date,
                    kcal=0,
                    protein=0,
                    fat=0,
                    carbs=0,
                    sugar=0,
                    sodium=0,
                    caffeine=0,
                ),
            )
        )
    return points, len(rows)


async def _today_summary(
    session: AsyncSession,
    user_id: UUID,
    summary_date: date,
) -> ToolExecutionResult:
    points, _ = await get_nutrition_points(session, user_id, summary_date, summary_date)
    point = points[0]
    profile = await get_profile(session, user_id)
    targets = calculate_daily_targets(profile) if profile is not None else None
    remaining = max(targets.kcal - point.kcal, 0) if targets is not None else None
    result = TodaySummaryToolResult(summary=point, targets=targets, remaining_kcal=remaining)
    target_text = (
        f"，目标 {targets.kcal} kcal，剩余约 {remaining:.0f} kcal"
        if targets is not None and remaining is not None
        else "，尚未设置个性化目标"
    )
    summary = (
        f"{summary_date.isoformat()} 已记录 {point.kcal:.0f} kcal，蛋白质 "
        f"{point.protein:.1f} g，脂肪 {point.fat:.1f} g，碳水 {point.carbs:.1f} g{target_text}。"
    )
    return ToolExecutionResult(
        tool_name="get_today_summary",
        payload=result.model_dump(mode="json"),
        summary=summary,
    )


async def _weekly_trend(
    session: AsyncSession,
    user_id: UUID,
    end_date: date,
) -> ToolExecutionResult:
    start_date = end_date - timedelta(days=6)
    points, recorded_days = await get_nutrition_points(session, user_id, start_date, end_date)
    profile = await get_profile(session, user_id)
    targets = calculate_daily_targets(profile) if profile is not None else None
    total = sum(point.kcal for point in points)
    result = WeeklyTrendToolResult(
        start_date=start_date,
        end_date=end_date,
        days=points,
        total_kcal=round(total, 2),
        average_kcal=round(total / 7, 2),
        days_with_records=recorded_days,
        targets=targets,
    )
    summary = (
        f"{start_date.isoformat()} 至 {end_date.isoformat()} 共记录 {recorded_days}/7 天，"
        f"总计 {total:.0f} kcal，按完整 7 天平均 {total / 7:.0f} kcal/天。"
    )
    return ToolExecutionResult(
        tool_name="get_weekly_trend",
        payload=result.model_dump(mode="json"),
        summary=summary,
    )


async def _search_food(
    session: AsyncSession,
    user_id: UUID,
    query: str,
    limit: int,
) -> ToolExecutionResult:
    foods = await search_visible_foods(session, user_id, query.strip(), limit)
    result = FoodSearchToolResult(
        query=query.strip(),
        foods=[FoodSearchToolItem.model_validate(food, from_attributes=True) for food in foods],
    )
    if foods:
        names = "、".join(food.name for food in foods)
        summary = f"食品库搜索“{query.strip()}”找到 {len(foods)} 项：{names}。"
    else:
        summary = f"食品库搜索“{query.strip()}”未找到可见条目。"
    return ToolExecutionResult(
        tool_name="search_food",
        payload=result.model_dump(mode="json"),
        summary=summary,
    )


async def execute_assistant_tool(
    session: AsyncSession,
    user_id: UUID,
    tool_name: str,
    arguments: dict[str, Any],
    reference_date: date,
) -> ToolExecutionResult:
    try:
        if tool_name == "get_today_summary":
            parsed = GetTodaySummaryArguments.model_validate(arguments)
            return await _today_summary(session, user_id, parsed.date or reference_date)
        if tool_name == "get_weekly_trend":
            parsed = GetWeeklyTrendArguments.model_validate(arguments)
            return await _weekly_trend(session, user_id, parsed.end_date or reference_date)
        if tool_name == "search_food":
            parsed = SearchFoodArguments.model_validate(arguments)
            return await _search_food(session, user_id, parsed.query, parsed.limit)
    except ValidationError as error:
        raise AssistantToolError("tool arguments failed validation") from error
    raise AssistantToolError(f"unknown assistant tool: {tool_name}")
