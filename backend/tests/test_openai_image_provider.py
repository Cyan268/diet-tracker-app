import base64
import json
from datetime import date

import httpx2
import pytest

from app.ai.openai_image_responses import OpenAIResponsesFoodImageProvider
from app.schemas.analysis import AnalysisImageWorkerRequest


def request() -> AnalysisImageWorkerRequest:
    return AnalysisImageWorkerRequest(
        upload_id="00000000-0000-0000-0000-000000000001",
        log_date=date(2026, 9, 16),
        meal_type_hint="lunch",
    )


@pytest.mark.asyncio
async def test_image_provider_sends_private_bytes_and_parses_strict_result() -> None:
    captured: dict[str, object] = {}
    output = {
        "entities": [
            {
                "raw_name": "一碗米饭",
                "normalized_name": "米饭",
                "amount": 1,
                "unit": "碗",
                "meal_type": "lunch",
                "confidence": 0.72,
                "needs_review": True,
                "evidence": "图片中可见一碗米饭，但没有可靠比例尺",
            }
        ]
    }

    async def handler(http_request: httpx2.Request) -> httpx2.Response:
        captured.update(json.loads(http_request.content))
        return httpx2.Response(
            200,
            json={
                "id": "resp_image_1",
                "model": "test-image-model",
                "usage": {"input_tokens": 30, "output_tokens": 20},
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(output)}],
                    }
                ],
            },
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler), base_url="https://test")
    provider = OpenAIResponsesFoodImageProvider(
        api_key="sk-test",
        model="test-image-model",
        base_url="https://test",
        timeout_seconds=5,
        client=client,
    )
    image = b"normalized-private-png"
    result = await provider.extract(request(), image, "image/png")
    await client.aclose()

    user_content = captured["input"][1]["content"]  # type: ignore[index]
    image_part = next(part for part in user_content if part["type"] == "input_image")
    assert image_part["image_url"] == (
        "data:image/png;base64," + base64.b64encode(image).decode("ascii")
    )
    assert captured["store"] is False
    assert captured["text"]["format"]["strict"] is True  # type: ignore[index]
    assert result.entities[0].normalized_name == "米饭"
    assert result.entities[0].needs_review is True
    assert result.provider_request_id == "resp_image_1"
