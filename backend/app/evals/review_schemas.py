from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evals.schemas import ExpectedFoodEntity
from app.schemas.diet import MealType


class BlindReviewCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    text: str = Field(min_length=2, max_length=1000)
    meal_type_hint: MealType | None = None
    status: Literal["pending", "completed", "uncertain"] = "pending"
    proposed_expected: list[ExpectedFoodEntity] | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def completed_cases_require_labels(self) -> "BlindReviewCase":
        if self.status == "pending" and self.proposed_expected is not None:
            raise ValueError("pending review case must not contain proposed labels")
        if self.status == "completed" and self.proposed_expected is None:
            raise ValueError("completed review case requires proposed labels")
        if self.status == "uncertain" and not self.notes:
            raise ValueError("uncertain review case requires notes")
        return self


class BlindReviewBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_schema_version: Literal["1.0"] = "1.0"
    dataset_version: str
    dataset_fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,80}$")
    blind: Literal[True] = True
    created_at: datetime
    instructions: str
    cases: list[BlindReviewCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_must_be_unique(self) -> "BlindReviewBundle":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("review case ids must be unique")
        return self


class AnnotationReviewReport(BaseModel):
    report_schema_version: Literal["1.0"] = "1.0"
    dataset_version: str
    dataset_fingerprint_sha256: str
    reviewer_id: str
    sample_count: int = Field(ge=1)
    completed_count: int = Field(ge=0)
    uncertain_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    review_coverage_rate: float = Field(ge=0, le=1)
    exact_agreement_rate: float | None = Field(default=None, ge=0, le=1)
    disagreement_case_ids: list[str]
    uncertain_case_ids: list[str]
    pending_case_ids: list[str]
