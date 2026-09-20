from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.diet import FoodMatchCandidateResponse, LogResponse, MealType

AnalysisJobStatus = Literal[
    "queued",
    "running",
    "retry_wait",
    "succeeded",
    "failed",
    "unknown",
    "cancelled",
]


class AnalysisCreateRequest(BaseModel):
    client_request_id: UUID
    text: str = Field(min_length=2, max_length=1000)
    log_date: date
    meal_type_hint: MealType | None = None
    locale: Literal["zh-CN"] = "zh-CN"


class AnalysisImageCreateRequest(BaseModel):
    client_request_id: UUID
    upload_id: UUID
    log_date: date
    meal_type_hint: MealType | None = None
    locale: Literal["zh-CN"] = "zh-CN"
    consent_to_provider: Literal[True]


class AnalysisImageWorkerRequest(BaseModel):
    upload_id: UUID
    log_date: date
    meal_type_hint: MealType | None = None
    locale: Literal["zh-CN"] = "zh-CN"


class AnalysisAcceptedResponse(BaseModel):
    job_id: UUID
    status: AnalysisJobStatus
    status_url: str
    created_at: datetime


class AnalysisStatusResponse(BaseModel):
    job_id: UUID
    status: AnalysisJobStatus
    retryable: bool
    attempt_count: int
    draft_id: UUID | None
    failure_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class AnalysisDraftEntityResponse(BaseModel):
    id: UUID
    position: int
    raw_name: str
    normalized_name: str
    amount: float
    unit: str
    meal_type: MealType
    confidence: float | None
    needs_review: bool
    matched_food_id: UUID | None
    catalog_revision: str | None
    candidates: list[FoodMatchCandidateResponse]


class AnalysisDraftResponse(BaseModel):
    id: UUID
    job_id: UUID
    status: Literal["review", "confirmed", "expired", "cancelled"]
    version: int
    log_date: date
    result_schema_version: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    entities: list[AnalysisDraftEntityResponse]


class AnalysisDraftEntityUpdate(BaseModel):
    entity_id: UUID
    normalized_name: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=100000)
    unit: str = Field(min_length=1, max_length=30)
    meal_type: MealType
    matched_food_id: UUID | None
    catalog_revision: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def catalog_identity_is_complete(self) -> "AnalysisDraftEntityUpdate":
        if (self.matched_food_id is None) != (self.catalog_revision is None):
            raise ValueError("matched_food_id and catalog_revision must be provided together")
        return self


class AnalysisDraftUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    log_date: date
    entities: list[AnalysisDraftEntityUpdate] = Field(min_length=1, max_length=20)


class AnalysisConfirmationEntity(BaseModel):
    source_entity_id: UUID | None = None
    client_id: UUID
    food_item_id: UUID
    catalog_revision: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0, le=100000)
    unit: str = Field(min_length=1, max_length=30)
    meal_type: MealType


class AnalysisConfirmRequest(BaseModel):
    client_confirmation_id: UUID
    expected_draft_version: int = Field(ge=1)
    entities: list[AnalysisConfirmationEntity] = Field(min_length=1, max_length=20)


class AnalysisLogIdentity(BaseModel):
    entity_id: UUID | None
    client_id: UUID
    log_id: UUID


class AnalysisConfirmationResponse(BaseModel):
    confirmation_id: UUID
    draft_id: UUID
    confirmed_draft_version: int
    created_at: datetime
    log_identities: list[AnalysisLogIdentity]
    logs: list[LogResponse]
