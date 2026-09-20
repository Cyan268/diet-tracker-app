from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

UploadContentType = Literal["image/jpeg", "image/png", "image/webp"]


class UploadPresignRequest(BaseModel):
    content_type: UploadContentType
    size: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("sha256 must be lowercase hexadecimal")
        return normalized


class UploadPresignResponse(BaseModel):
    upload_id: UUID
    status: Literal["pending"]
    upload_url: str
    method: Literal["PUT"] = "PUT"
    required_content_type: UploadContentType
    required_size: int
    upload_url_expires_at: datetime
    upload_expires_at: datetime


class UploadResponse(BaseModel):
    id: UUID
    status: Literal["pending", "ready", "failed", "delete_pending", "deleted"]
    content_type: UploadContentType
    declared_size: int
    verified_size: int | None
    sha256: str | None
    width: int | None
    height: int | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
