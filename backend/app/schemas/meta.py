from pydantic import BaseModel


class PublicRuntimeConfigResponse(BaseModel):
    registration_enabled: bool
