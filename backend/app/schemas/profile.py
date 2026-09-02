from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"


class ActivityLevel(StrEnum):
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"


class Goal(StrEnum):
    LOSE = "lose"
    MAINTAIN = "maintain"
    GAIN = "gain"


class ProfileUpsertRequest(BaseModel):
    gender: Gender
    age: int = Field(ge=13, le=120)
    height_cm: float = Field(ge=80, le=250)
    weight_kg: float = Field(ge=20, le=400)
    activity_level: ActivityLevel
    goal: Goal


class DailyTargetsResponse(BaseModel):
    kcal: int
    protein: int
    fat: int
    carbs: int
    sugar: int = 50
    sodium: int = 2300
    caffeine: int = 400


class ProfileResponse(ProfileUpsertRequest):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime
    daily_targets: DailyTargetsResponse
