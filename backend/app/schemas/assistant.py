from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ai import AiUsage
from app.schemas.profile import DailyTargetsResponse

AssistantToolName = Literal["get_today_summary", "get_weekly_trend", "search_food"]


class AssistantQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=500)
    reference_date: date
    locale: Literal["zh-CN"] = "zh-CN"

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("question must contain at least two visible characters")
        return stripped


class AssistantContextMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)
    reference_date: date | None = None


class AssistantToolEvidence(BaseModel):
    call_id: str = Field(min_length=1, max_length=200)
    tool_name: AssistantToolName
    summary: str = Field(min_length=1, max_length=500)


class AssistantAnswerResponse(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    provider: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=120)
    prompt_version: str = Field(min_length=1, max_length=80)
    fallback_used: bool
    latency_ms: int = Field(ge=0)
    trace_id: UUID | None = None
    usage: AiUsage
    evidence: list[AssistantToolEvidence] = Field(max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=10)
    disclaimer: str = "仅用于日常饮食记录参考，不构成医疗或营养诊断。"


class AssistantConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must contain visible characters")
        return stripped


class AssistantConversationMessageCreateRequest(AssistantQuestionRequest):
    client_message_id: UUID


class AssistantConversationSummaryResponse(BaseModel):
    id: UUID
    title: str
    message_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class AssistantConversationMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_message_id: UUID | None
    role: Literal["user", "assistant"]
    content: str
    sequence: int = Field(ge=1)
    reference_date: date | None
    provider: str | None
    model: str | None
    prompt_version: str | None
    fallback_used: bool | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    trace_id: UUID | None
    evidence: list[AssistantToolEvidence]
    warnings: list[str]
    disclaimer: str | None
    created_at: datetime


class AssistantConversationDetailResponse(AssistantConversationSummaryResponse):
    messages: list[AssistantConversationMessageResponse]


class AssistantConversationTurnResponse(BaseModel):
    conversation: AssistantConversationDetailResponse
    replayed: bool = False


class GetTodaySummaryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date | None


class GetWeeklyTrendArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    end_date: date | None


class SearchFoodArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=100)
    limit: int = Field(ge=1, le=10)


class DailyNutritionPoint(BaseModel):
    date: date
    kcal: float = Field(ge=0)
    protein: float = Field(ge=0)
    fat: float = Field(ge=0)
    carbs: float = Field(ge=0)
    sugar: float = Field(ge=0)
    sodium: float = Field(ge=0)
    caffeine: float = Field(ge=0)


class TodaySummaryToolResult(BaseModel):
    summary: DailyNutritionPoint
    targets: DailyTargetsResponse | None
    remaining_kcal: float | None


class WeeklyTrendToolResult(BaseModel):
    start_date: date
    end_date: date
    days: list[DailyNutritionPoint] = Field(min_length=7, max_length=7)
    total_kcal: float = Field(ge=0)
    average_kcal: float = Field(ge=0)
    days_with_records: int = Field(ge=0, le=7)
    targets: DailyTargetsResponse | None


class FoodSearchToolItem(BaseModel):
    id: UUID
    name: str
    brand: str | None
    serving_unit: str | None
    serving_weight_g: float | None
    kcal_per_100g: float
    protein_per_100g: float
    fat_per_100g: float
    carbs_per_100g: float
    source: str


class FoodSearchToolResult(BaseModel):
    query: str
    foods: list[FoodSearchToolItem] = Field(max_length=10)
