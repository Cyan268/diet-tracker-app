from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NutritionValues(BaseModel):
    kcal: float = Field(ge=0, le=100000)
    protein: float = Field(ge=0, le=10000)
    fat: float = Field(ge=0, le=10000)
    carbs: float = Field(ge=0, le=10000)
    sugar: float = Field(default=0, ge=0, le=10000)
    sodium: float = Field(default=0, ge=0, le=1000000)
    caffeine: float = Field(default=0, ge=0, le=100000)


class FoodCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    serving_unit: str | None = Field(default=None, min_length=1, max_length=30)
    serving_weight_g: float | None = Field(default=None, gt=0, le=100000)
    kcal_per_100g: float = Field(ge=0, le=100000)
    protein_per_100g: float = Field(ge=0, le=10000)
    fat_per_100g: float = Field(ge=0, le=10000)
    carbs_per_100g: float = Field(ge=0, le=10000)
    sugar_per_100g: float = Field(default=0, ge=0, le=10000)
    sodium_per_100g: float = Field(default=0, ge=0, le=1000000)
    caffeine_per_100g: float = Field(default=0, ge=0, le=100000)


class FoodResponse(FoodCreateRequest):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    created_at: datetime
    updated_at: datetime


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    DRINK = "drink"


class LogContent(BaseModel):
    log_date: date
    meal_type: MealType
    food_item_id: UUID | None = None
    custom_name: str | None = Field(default=None, min_length=1, max_length=200)
    amount: float = Field(gt=0, le=100000)
    unit: str = Field(min_length=1, max_length=30)
    nutrition: NutritionValues | None = None
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_source(self) -> "LogContent":
        if (self.food_item_id is None) == (self.custom_name is None):
            raise ValueError("provide exactly one of food_item_id or custom_name")
        if self.food_item_id is not None and self.nutrition is not None:
            raise ValueError("nutrition is calculated by the server for catalog foods")
        if self.custom_name is not None and self.nutrition is None:
            raise ValueError("nutrition is required for a custom food")
        return self


class LogCreateRequest(LogContent):
    client_id: UUID


class LogUpdateRequest(LogContent):
    expected_version: int = Field(ge=1)


class LogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    log_date: date
    meal_type: MealType
    food_item_id: UUID | None
    custom_name: str | None
    amount: float
    unit: str
    kcal: float
    protein: float
    fat: float
    carbs: float
    sugar: float
    sodium: float
    caffeine: float
    note: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class SyncChangeResponse(BaseModel):
    cursor: int
    operation: Literal["upsert", "delete"]
    server_id: UUID
    client_id: UUID
    version: int
    log: LogResponse | None


class SyncPageResponse(BaseModel):
    changes: list[SyncChangeResponse]
    next_cursor: int
    has_more: bool


class MealBreakdown(BaseModel):
    breakfast: float = 0
    lunch: float = 0
    dinner: float = 0
    snack: float = 0
    drink: float = 0


class DailySummaryResponse(BaseModel):
    date: date
    total_kcal: float
    total_protein: float
    total_fat: float
    total_carbs: float
    total_sugar: float
    total_sodium: float
    total_caffeine: float
    meal_breakdown: MealBreakdown
