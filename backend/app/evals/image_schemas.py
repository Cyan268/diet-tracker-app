from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExpectedImageFood(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_name: str = Field(min_length=1, max_length=200)
    must_identify: bool = True
    amount: float | None = Field(default=None, gt=0, le=100000)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    amount_basis: Literal["weighed", "package_label", "natural_serving", "unknown"]
    basis_reference: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def amount_requires_a_real_basis(self) -> "ExpectedImageFood":
        if (self.amount is None) != (self.unit is None):
            raise ValueError("image amount and unit must be supplied together")
        if self.amount_basis == "unknown":
            if self.amount is not None or self.basis_reference is not None:
                raise ValueError("unknown amount basis must not contain an amount or reference")
            return self
        if self.amount is None:
            raise ValueError("known amount basis requires amount and unit")
        if self.amount_basis in {"weighed", "package_label"} and not self.basis_reference:
            raise ValueError("measured amount requires a scale or package evidence reference")
        return self


class ImageEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    group_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    asset_reference: str = Field(min_length=1, max_length=500)
    asset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_type: Literal["self_captured", "participant_consent", "licensed_dataset"]
    authorization_reference: str = Field(min_length=3, max_length=500)
    contains_personal_data: Literal[False]
    captured_on: date
    annotated_on: date
    scene_tags: list[str] = Field(min_length=1, max_length=12)
    annotators: list[str] = Field(min_length=1, max_length=20)
    expected_outcome: Literal["recognition", "refusal", "review_required"]
    expected_foods: list[ExpectedImageFood] = Field(max_length=20)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def outcome_matches_expected_foods(self) -> "ImageEvaluationCase":
        if self.expected_outcome == "recognition" and not self.expected_foods:
            raise ValueError("recognition case requires at least one expected food")
        if self.expected_outcome == "refusal" and self.expected_foods:
            raise ValueError("refusal case must not contain expected foods")
        if len(self.annotators) != len(set(self.annotators)):
            raise ValueError("image case annotators must be unique")
        names = [food.normalized_name.strip().casefold() for food in self.expected_foods]
        if len(names) != len(set(names)):
            raise ValueError("expected image food names must be unique within a case")
        return self


class ImageEvaluationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_schema_version: Literal["1.0"]
    dataset_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,80}$")
    description: str = Field(min_length=1, max_length=500)
    split: Literal["development", "test"]
    frozen: bool
    source: str = Field(min_length=1, max_length=300)
    authorization: str = Field(min_length=1, max_length=500)
    contains_personal_data: Literal[False]
    grouping_policy: str = Field(min_length=1, max_length=300)
    cases: list[ImageEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def manifest_is_internally_consistent(self) -> "ImageEvaluationManifest":
        if self.split == "development" and self.frozen:
            raise ValueError("development image manifest must not be frozen")
        if self.split == "test" and not self.frozen:
            raise ValueError("test image manifest must be frozen")
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("image evaluation case ids must be unique")
        asset_hashes = [case.asset_sha256 for case in self.cases]
        if len(asset_hashes) != len(set(asset_hashes)):
            raise ValueError("image assets must be unique within a manifest")
        if self.frozen:
            incomplete = [case.id for case in self.cases if len(case.annotators) < 2]
            if incomplete:
                raise ValueError(
                    "frozen image cases require at least two annotators: " + ", ".join(incomplete)
                )
        return self
