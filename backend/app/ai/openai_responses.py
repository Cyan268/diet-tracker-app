import json
from typing import Final

import httpx2
from pydantic import ValidationError

from app.ai.provider import ProviderError, ProviderResult
from app.schemas.ai import FoodEntityExtraction, FoodTextAnalyzeRequest

RESPONSES_PATH: Final = "/responses"
RETRYABLE_STATUS_CODES: Final = {408, 409, 429}
FOOD_TEXT_PROMPT_VERSION: Final = "food-text-v1.0.0"

DEVELOPER_PROMPT: Final = """You extract food log entities from Simplified Chinese text.

Success criteria:
- Return every explicitly mentioned food as one entity.
- Extract amount, unit, and meal type only from the user's text.
- Do not calculate calories or nutrition.
- Use a concise Chinese normalized_name. Prefer common catalog names when clear.
- If quantity is missing, use amount 1 with the most natural serving unit.
  Set needs_review true and lower confidence.
- Set needs_review true for ambiguous names, quantities, units, or meal types.
- evidence must briefly explain what text supported the extraction.
- Return an empty entities array when no food can be identified.
"""


def _output_text(payload: dict[str, object]) -> str:
    output = payload.get("output")
    if not isinstance(output, list):
        raise ProviderError("invalid_response", "response output is missing", retryable=False)
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str) and text:
                    return text
    raise ProviderError("empty_response", "model returned no output text", retryable=False)


class OpenAIResponsesFoodTextProvider:
    name = "openai_responses"
    prompt_version = FOOD_TEXT_PROMPT_VERSION

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = client

    def _request_body(self, request: FoodTextAnalyzeRequest) -> dict[str, object]:
        schema = FoodEntityExtraction.model_json_schema()
        return {
            "model": self.model,
            "reasoning": {"effort": "none"},
            "store": False,
            "max_output_tokens": 1200,
            "input": [
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": DEVELOPER_PROMPT}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                f"日期：{request.log_date.isoformat()}\n"
                                f"餐次提示：{request.meal_type_hint or '无'}\n"
                                f"饮食描述：{request.text}"
                            ),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "food_entity_extraction",
                    "strict": True,
                    "schema": schema,
                }
            },
        }

    async def _post(self, request: FoodTextAnalyzeRequest) -> httpx2.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = self._request_body(request)
        if self.client is not None:
            return await self.client.post(RESPONSES_PATH, headers=headers, json=body)
        timeout = httpx2.Timeout(self.timeout_seconds)
        async with httpx2.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
            return await client.post(RESPONSES_PATH, headers=headers, json=body)

    async def extract(self, request: FoodTextAnalyzeRequest) -> ProviderResult:
        try:
            response = await self._post(request)
        except httpx2.TimeoutException as error:
            raise ProviderError("timeout", "OpenAI request timed out", retryable=True) from error
        except httpx2.RequestError as error:
            raise ProviderError("network_error", "OpenAI request failed", retryable=True) from error

        if response.status_code >= 400:
            retryable = (
                response.status_code in RETRYABLE_STATUS_CODES or response.status_code >= 500
            )
            raise ProviderError(
                f"http_{response.status_code}",
                "OpenAI returned an error response",
                retryable=retryable,
            )

        try:
            payload = response.json()
            parsed = FoodEntityExtraction.model_validate_json(_output_text(payload))
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
            raise ProviderError(
                "schema_validation_failed",
                "OpenAI output failed schema validation",
                retryable=False,
            ) from error

        usage = payload.get("usage") if isinstance(payload, dict) else None
        input_tokens = usage.get("input_tokens", 0) if isinstance(usage, dict) else 0
        output_tokens = usage.get("output_tokens", 0) if isinstance(usage, dict) else 0
        response_model = payload.get("model") if isinstance(payload, dict) else None
        return ProviderResult(
            entities=parsed.entities,
            model=response_model if isinstance(response_model, str) else self.model,
            input_tokens=input_tokens if isinstance(input_tokens, int) else 0,
            output_tokens=output_tokens if isinstance(output_tokens, int) else 0,
        )
