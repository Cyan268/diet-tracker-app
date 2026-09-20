from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.ai import ParsedFoodEntity
from app.schemas.diet import MealType


class ExpectedFoodEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_name: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=100000)
    unit: str = Field(min_length=1, max_length=30)
    meal_type: MealType
    acceptable_amount_min: float | None = Field(default=None, gt=0, le=100000)
    acceptable_amount_max: float | None = Field(default=None, gt=0, le=100000)

    @model_validator(mode="after")
    def acceptable_amount_range_is_complete(self) -> "ExpectedFoodEntity":
        if (self.acceptable_amount_min is None) != (self.acceptable_amount_max is None):
            raise ValueError("acceptable amount range requires both minimum and maximum")
        if self.acceptable_amount_min is not None:
            if self.acceptable_amount_min > self.acceptable_amount_max:
                raise ValueError("acceptable amount minimum must not exceed maximum")
            if not self.acceptable_amount_min <= self.amount <= self.acceptable_amount_max:
                raise ValueError("expected amount must be inside its acceptable range")
        return self


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    group_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    text: str = Field(min_length=2, max_length=1000)
    meal_type_hint: MealType | None = None
    tags: list[str] = Field(default_factory=list, max_length=12)
    expected: list[ExpectedFoodEntity] = Field(max_length=20)

    @model_validator(mode="after")
    def expected_names_must_be_unique(self) -> "EvaluationCase":
        names = [entity.normalized_name.strip().casefold() for entity in self.expected]
        if len(names) != len(set(names)):
            raise ValueError("expected normalized_name values must be unique within a case")
        return self


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_schema_version: Literal["2.0"]
    dataset_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,80}$")
    description: str = Field(min_length=1, max_length=500)
    split: Literal["development", "test"]
    frozen: bool
    source: str = Field(min_length=1, max_length=200)
    authorization: str = Field(min_length=1, max_length=300)
    annotators: list[str] = Field(min_length=1, max_length=20)
    annotation_protocol: str = Field(min_length=1, max_length=500)
    contains_personal_data: bool
    grouping_policy: str = Field(min_length=1, max_length=300)
    evaluation_date: date
    locale: str = "zh-CN"
    amount_absolute_tolerance: float = Field(default=1e-6, ge=0, le=1000)
    cases: list[EvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_must_be_unique(self) -> "EvaluationDataset":
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case ids must be unique")
        return self


class FieldMatch(BaseModel):
    normalized_name: str
    amount: bool
    unit: bool
    meal_type: bool


class EvaluationCaseResult(BaseModel):
    case_id: str
    text: str
    success: bool
    schema_valid: bool | None
    model: str | None
    latency_ms: float = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    expected: list[ExpectedFoodEntity]
    actual: list[ParsedFoodEntity]
    matched_fields: list[FieldMatch]
    false_positive_names: list[str]
    false_negative_names: list[str]
    exact_match: bool
    error_code: str | None = None


class EvaluationMetrics(BaseModel):
    sample_count: int = Field(ge=1)
    successful_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    request_success_rate: float = Field(ge=0, le=1)
    schema_evaluated_cases: int = Field(ge=0)
    schema_validity_rate: float | None = Field(default=None, ge=0, le=1)
    true_positive_entities: int = Field(ge=0)
    false_positive_entities: int = Field(ge=0)
    false_negative_entities: int = Field(ge=0)
    entity_precision: float = Field(ge=0, le=1)
    entity_recall: float = Field(ge=0, le=1)
    entity_f1: float = Field(ge=0, le=1)
    amount_accuracy: float | None = Field(default=None, ge=0, le=1)
    unit_accuracy: float | None = Field(default=None, ge=0, le=1)
    meal_type_accuracy: float | None = Field(default=None, ge=0, le=1)
    case_exact_match_rate: float = Field(ge=0, le=1)
    p50_latency_ms: float = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    average_tokens_per_case: float = Field(ge=0)
    estimated_total_cost_usd: Decimal | None = Field(default=None, ge=0)
    estimated_average_cost_usd: Decimal | None = Field(default=None, ge=0)
    cost_status: Literal["known", "unknown"]


class EvaluationSliceMetrics(BaseModel):
    sample_count: int = Field(ge=1)
    successful_cases: int = Field(ge=0)
    request_success_rate: float = Field(ge=0, le=1)
    case_exact_match_rate: float = Field(ge=0, le=1)


class EvaluationReport(BaseModel):
    report_schema_version: Literal["2.0"] = "2.0"
    dataset_schema_version: Literal["2.0"]
    dataset_version: str
    dataset_split: Literal["development", "test"]
    dataset_fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    code_revision: str = Field(min_length=1, max_length=100)
    provider: str
    model: str
    prompt_version: str
    generated_at: datetime
    evaluation_config: dict[str, object]
    metrics: EvaluationMetrics
    tag_metrics: dict[str, EvaluationSliceMetrics]
    failure_counts: dict[str, int]
    cases: list[EvaluationCaseResult]
