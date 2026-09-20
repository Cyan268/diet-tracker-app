from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.ai import AiUsage
from app.schemas.diet import MealType
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
    calendar_days: Literal[7] = 7
    average_basis: Literal["calendar_days"] = "calendar_days"
    total_kcal: float = Field(ge=0)
    average_kcal: float = Field(ge=0)
    average_protein: float = Field(ge=0)
    average_fat: float = Field(ge=0)
    average_carbs: float = Field(ge=0)
    average_sugar: float = Field(ge=0)
    average_sodium: float = Field(ge=0)
    average_caffeine: float = Field(ge=0)
    recorded_day_average_kcal: float = Field(ge=0)
    recorded_day_average_protein: float = Field(ge=0)
    recorded_day_average_fat: float = Field(ge=0)
    recorded_day_average_carbs: float = Field(ge=0)
    recorded_day_average_sugar: float = Field(ge=0)
    recorded_day_average_sodium: float = Field(ge=0)
    recorded_day_average_caffeine: float = Field(ge=0)


class WeeklyMetricChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    average_kcal_percent: float | None
    average_protein_percent: float | None
    average_fat_percent: float | None
    average_carbs_percent: float | None
    average_sugar_percent: float | None
    average_sodium_percent: float | None
    average_caffeine_percent: float | None


class WeeklyMealStructureItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meal_type: MealType
    log_count: int = Field(ge=0)
    total_kcal: float = Field(ge=0)
    kcal_ratio: float = Field(ge=0, le=1)


class WeeklyTargetAdherence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    assessment_days: int = Field(ge=0, le=7)
    kcal_within_target_days: int | None = Field(default=None, ge=0, le=7)
    tolerance_percent: Literal[10] = 10
    rule: Literal["recorded_day_kcal_within_target_plus_or_minus_10_percent"] = (
        "recorded_day_kcal_within_target_plus_or_minus_10_percent"
    )


class WeeklyReportFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: WeeklyPeriodSummary
    previous: WeeklyPeriodSummary
    targets: DailyTargetsResponse | None
    comparison_available: bool
    changes: WeeklyMetricChanges
    meal_structure: list[WeeklyMealStructureItem] = Field(min_length=5, max_length=5)
    target_adherence: WeeklyTargetAdherence
    business_date_basis: Literal["user_supplied_log_date"] = "user_supplied_log_date"
    rounding_policy: Literal["python_round_half_even_2dp"] = "python_round_half_even_2dp"
    completeness_threshold_days: Literal[4] = 4
    fact_references: list["WeeklyFactReference"] = Field(min_length=1, max_length=100)


class WeeklyFactReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,100}$")
    label: str = Field(min_length=1, max_length=120)
    display_value: str = Field(min_length=1, max_length=120)
    source: Literal["food_log_snapshots", "user_profile", "derived"]
    calculation: str = Field(min_length=1, max_length=300)


class WeeklyNarrativeCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Literal[
        "headline",
        "summary",
        "highlights.0",
        "highlights.1",
        "highlights.2",
    ]
    fact_ids: list[str] = Field(min_length=1, max_length=12)


class WeeklyReportNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=2, max_length=80)
    summary: str = Field(min_length=5, max_length=500)
    highlights: list[str] = Field(min_length=1, max_length=3)
    actions: list[str] = Field(min_length=1, max_length=3)
    citations: list[WeeklyNarrativeCitation] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def factual_fields_must_have_unique_citations(self) -> "WeeklyReportNarrative":
        paths = [citation.path for citation in self.citations]
        required = {"headline", "summary"} | {
            f"highlights.{index}" for index in range(len(self.highlights))
        }
        if len(paths) != len(set(paths)):
            raise ValueError("weekly narrative citation paths must be unique")
        if set(paths) != required:
            raise ValueError("headline, summary, and every highlight require exactly one citation")
        return self


class WeeklyReportResponse(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
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
