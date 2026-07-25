from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.schemas.diet import MealType


class FoodTextAnalyzeRequest(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    log_date: date
    meal_type_hint: MealType | None = None
    locale: Literal["zh-CN"] = "zh-CN"


class ParsedFoodEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_name: str = Field(min_length=1, max_length=200)
    normalized_name: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=100000)
    unit: str = Field(min_length=1, max_length=30)
    meal_type: MealType
    confidence: float = Field(ge=0, le=1)
    needs_review: bool
    evidence: str = Field(min_length=1, max_length=300)


class FoodEntityExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[ParsedFoodEntity] = Field(max_length=20)


class AiUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)


class FoodTextAnalyzeResponse(BaseModel):
    provider: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=120)
    schema_version: Literal["1.0"] = "1.0"
    requires_confirmation: Literal[True] = True
    fallback_used: bool
    latency_ms: int = Field(ge=0)
    trace_id: UUID | None = None
    usage: AiUsage
    entities: list[ParsedFoodEntity] = Field(max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class AiMetricsResponse(BaseModel):
    total_calls: int = Field(ge=0)
    successful_calls: int = Field(ge=0)
    fallback_calls: int = Field(ge=0)
    failed_calls: int = Field(ge=0)
    average_latency_ms: float = Field(ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(ge=0)
    unpriced_calls: int = Field(ge=0)


class AiCredentialUpsertRequest(BaseModel):
    api_key: SecretStr = Field(min_length=20, max_length=500)

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_have_surrounding_whitespace(cls, value: SecretStr) -> SecretStr:
        raw_value = value.get_secret_value()
        if raw_value != raw_value.strip():
            raise ValueError("api_key must not contain surrounding whitespace")
        return value


class AiCredentialStatusResponse(BaseModel):
    configured: bool
    provider: Literal["openai"] = "openai"
    key_hint: str | None = None
    updated_at: datetime | None = None
