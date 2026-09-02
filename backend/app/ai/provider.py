from dataclasses import dataclass
from typing import Protocol

from app.schemas.ai import FoodTextAnalyzeRequest, ParsedFoodEntity


@dataclass(frozen=True)
class ProviderResult:
    entities: list[ParsedFoodEntity]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class FoodTextProvider(Protocol):
    name: str
    prompt_version: str

    async def extract(self, request: FoodTextAnalyzeRequest) -> ProviderResult: ...
