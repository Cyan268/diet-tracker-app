import base64
import json
from typing import Final

import httpx2
from pydantic import ValidationError

from app.ai.openai_responses import RESPONSES_PATH, RETRYABLE_STATUS_CODES, _output_text
from app.ai.provider import ProviderError, ProviderResult
from app.schemas.ai import FoodEntityExtraction
from app.schemas.analysis import AnalysisImageWorkerRequest

FOOD_IMAGE_PROMPT_VERSION: Final = "food-image-v1.0.0"

IMAGE_DEVELOPER_PROMPT: Final = """You extract visible food log entities from one meal image.

Safety and quality rules:
- Return only food or drink that is visibly supported by the image.
- Do not calculate calories or nutrition.
- Use concise Simplified Chinese names suitable for catalog matching.
- Without a reliable scale reference, use amount 1 and a natural serving unit
  such as 份, 碗, 杯, 个.
- Mark needs_review true for estimated quantity, mixed dishes, occlusion, or ambiguous identity.
- Use lower confidence for uncertain items; never invent hidden ingredients.
- evidence must briefly describe the visible evidence and uncertainty.
- Return an empty entities array when no food can be identified.
"""


class OpenAIResponsesFoodImageProvider:
    name = "openai_image_responses"
    prompt_version = FOOD_IMAGE_PROMPT_VERSION

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

    def _request_body(
        self,
        request: AnalysisImageWorkerRequest,
        image_bytes: bytes,
        content_type: str,
    ) -> dict[str, object]:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return {
            "model": self.model,
            "reasoning": {"effort": "none"},
            "store": False,
            "max_output_tokens": 1200,
            "input": [
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": IMAGE_DEVELOPER_PROMPT}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                f"日期：{request.log_date.isoformat()}\n"
                                f"餐次提示：{request.meal_type_hint or '无'}\n"
                                "请识别图片中可见的食品。"
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{content_type};base64,{encoded}",
                            "detail": "auto",
                        },
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "food_entity_extraction",
                    "strict": True,
                    "schema": FoodEntityExtraction.model_json_schema(),
                }
            },
        }

    async def extract(
        self,
        request: AnalysisImageWorkerRequest,
        image_bytes: bytes,
        content_type: str,
    ) -> ProviderResult:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = self._request_body(request, image_bytes, content_type)
        try:
            if self.client is not None:
                response = await self.client.post(RESPONSES_PATH, headers=headers, json=body)
            else:
                timeout = httpx2.Timeout(self.timeout_seconds)
                async with httpx2.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
                    response = await client.post(RESPONSES_PATH, headers=headers, json=body)
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
        response_id = payload.get("id") if isinstance(payload, dict) else None
        return ProviderResult(
            entities=parsed.entities,
            model=response_model if isinstance(response_model, str) else self.model,
            input_tokens=input_tokens if isinstance(input_tokens, int) else 0,
            output_tokens=output_tokens if isinstance(output_tokens, int) else 0,
            provider_request_id=response_id if isinstance(response_id, str) else None,
        )
