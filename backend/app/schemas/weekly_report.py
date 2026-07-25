from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai import AiUsage
from app.schemas.profile import DailyTargetsResponse


class WeeklyReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    end_date: date
    locale: Literal["zh-CN"] = "zh-CN"


class WeeklyPeriodSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    days_with_records: int = Field(ge=0, le=7)
    coverage_ratio: float = Field(ge=0, le=1)
    total_kcal: float = Field(ge=0)
    average_kcal: float = Field(ge=0)
    average_protein: float = Field(ge=0)
    average_fat: float = Field(ge=0)
    average_carbs: float = Field(ge=0)
    average_sugar: float = Field(ge=0)
    average_sodium: float = Field(ge=0)
    average_caffeine: float = Field(ge=0)


class WeeklyMetricChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    average_kcal_percent: float | None
    average_protein_percent: float | None
    average_fat_percent: float | None
    average_carbs_percent: float | None
    average_sugar_percent: float | None
    average_sodium_percent: float | None
    average_caffeine_percent: float | None


class WeeklyReportFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: WeeklyPeriodSummary
    previous: WeeklyPeriodSummary
    targets: DailyTargetsResponse | None
    comparison_available: bool
    changes: WeeklyMetricChanges


class WeeklyReportNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=2, max_length=80)
    summary: str = Field(min_length=5, max_length=500)
    highlights: list[str] = Field(min_length=1, max_length=3)
    actions: list[str] = Field(min_length=1, max_length=3)


class WeeklyReportResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    provider: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=120)
    prompt_version: str = Field(min_length=1, max_length=80)
    fallback_used: bool
    latency_ms: int = Field(ge=0)
    trace_id: UUID | None = None
    usage: AiUsage
    data_fingerprint: str = Field(min_length=64, max_length=64)
    facts: WeeklyReportFacts
    narrative: WeeklyReportNarrative
    warnings: list[str] = Field(default_factory=list, max_length=10)
    disclaimer: str = "仅用于日常饮食记录参考，不构成医疗或营养诊断。"
