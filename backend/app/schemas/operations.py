from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HostContainerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    running: bool
    health: Literal["healthy", "unhealthy", "starting", "none"]
    restart_count: int = Field(ge=0)


class HostBackupSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["verified", "missing", "failed"]
    last_success_at: datetime | None = None

    @field_validator("last_success_at")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("last_success_at must include a timezone")
        return value


class HostSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    generated_at: datetime
    memory_total_bytes: int = Field(gt=0)
    memory_available_bytes: int = Field(ge=0)
    disk_total_bytes: int = Field(gt=0)
    disk_free_bytes: int = Field(ge=0)
    memory_pressure_active: bool
    consecutive_memory_pressure_samples: int = Field(ge=0)
    consecutive_memory_recovery_samples: int = Field(ge=0)
    container_unhealthy_active: bool
    consecutive_container_unhealthy_samples: int = Field(ge=0)
    consecutive_container_recovery_samples: int = Field(ge=0)
    containers: list[HostContainerSnapshot] = Field(max_length=32)
    backup: HostBackupSnapshot
    collector_errors: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generated_at must include a timezone")
        return value

    @field_validator("collector_errors")
    @classmethod
    def errors_are_stable_codes(cls, values: list[str]) -> list[str]:
        if any(
            not value or len(value) > 80 or not value.replace("_", "").isalnum() for value in values
        ):
            raise ValueError("collector errors must be bounded stable codes")
        return values

    @model_validator(mode="after")
    def available_capacity_cannot_exceed_total(self) -> "HostSnapshot":
        if self.memory_available_bytes > self.memory_total_bytes:
            raise ValueError("available memory cannot exceed total memory")
        if self.disk_free_bytes > self.disk_total_bytes:
            raise ValueError("free disk cannot exceed total disk")
        return self


class OperationalAlert(BaseModel):
    code: str
    state: Literal["firing", "ok", "unknown"]
    severity: Literal["warning", "critical"]
    observed: int | float | Decimal | None
    threshold: str
    duration: str
    minimum_samples: int = Field(ge=0)
    route: str
    runbook: str
    recovery_condition: str


class OperationalMetricsResponse(BaseModel):
    generated_at: datetime
    privacy_contract: dict[str, object]
    runtime: dict[str, object]
    worker: dict[str, object]
    host: dict[str, object]
    ai: dict[str, object]
    alerts: list[OperationalAlert]
    limitations: list[str]
