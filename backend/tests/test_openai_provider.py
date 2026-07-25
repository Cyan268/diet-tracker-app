import json
from datetime import date

import httpx2
import pytest

from app.ai import OpenAIResponsesFoodTextProvider, ProviderError
from app.schemas.ai import FoodTextAnalyzeRequest


def make_provider(handler: httpx2.MockTransport) -> OpenAIResponsesFoodTextProvider:
    client = httpx2.AsyncClient(
        transport=handler,
        base_url="https://api.openai.com/v1",
    )
    return OpenAIResponsesFoodTextProvider(
        api_key="test-key",
        model="gpt-5.6-luna",
        base_url="https://api.openai.com/v1",
        timeout_seconds=8,
        client=client,
    )


def analyze_request() -> FoodTextAnalyzeRequest:
    return FoodTextAnalyzeRequest(
        text="午餐吃了200克鸡胸肉",
        log_date=date(2026, 7, 17),
    )


async def test_responses_provider_uses_strict_schema_and_parses_usage() -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/responses"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "gpt-5.6-luna"
        assert body["reasoning"] == {"effort": "none"}
        assert body["store"] is False
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["schema"]["additionalProperties"] is False

        extraction = {
            "entities": [
                {
                    "raw_name": "鸡胸肉",
                    "normalized_name": "鸡胸肉（水煮）",
                    "amount": 200,
                    "unit": "g",
                    "meal_type": "lunch",
                    "confidence": 0.96,
                    "needs_review": False,
                    "evidence": "文本明确包含200克鸡胸肉",
                }
            ]
        }
        return httpx2.Response(
            200,
            json={
                "model": "gpt-5.6-luna-2026-07-01",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(extraction)}],
                    }
                ],
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 40,
                    "total_tokens": 160,
                },
            },
        )

    provider = make_provider(httpx2.MockTransport(handler))
    assert provider.prompt_version == "food-text-v1.0.0"
    result = await provider.extract(analyze_request())

    assert result.model == "gpt-5.6-luna-2026-07-01"
    assert result.input_tokens == 120
    assert result.output_tokens == 40
    assert result.entities[0].normalized_name == "鸡胸肉（水煮）"


async def test_responses_provider_marks_rate_limit_as_retryable() -> None:
    async def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(429, json={"error": {"message": "rate limited"}})

    provider = make_provider(httpx2.MockTransport(handler))

    with pytest.raises(ProviderError) as caught:
        await provider.extract(analyze_request())

    assert caught.value.code == "http_429"
    assert caught.value.retryable is True


async def test_responses_provider_rejects_output_outside_schema() -> None:
    async def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "model": "gpt-5.6-luna",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps({"entities": [{"name": "鸡胸肉"}]}),
                            }
                        ],
                    }
                ],
            },
        )

    provider = make_provider(httpx2.MockTransport(handler))

    with pytest.raises(ProviderError) as caught:
        await provider.extract(analyze_request())

    assert caught.value.code == "schema_validation_failed"
    assert caught.value.retryable is False
