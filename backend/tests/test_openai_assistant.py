import json
from datetime import date

import httpx2

from app.ai import OpenAIResponsesAssistantProvider
from app.schemas.assistant import AssistantContextMessage, AssistantQuestionRequest
from app.services.assistant_tools import ToolExecutionResult


async def test_responses_assistant_executes_strict_tool_loop() -> None:
    request_count = 0

    async def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal request_count
        request_count += 1
        body = json.loads(request.content)
        assert body["model"] == "gpt-5.6-luna"
        assert body["store"] is False
        assert body["parallel_tool_calls"] is False
        assert all(tool["strict"] is True for tool in body["tools"])
        assert all(tool["parameters"]["additionalProperties"] is False for tool in body["tools"])
        if request_count == 1:
            assert body["tool_choice"] == "required"
            assert body["input"][0] == {
                "role": "user",
                "content": "参考日期：2026-07-18\n用户问题：我昨天怎么样？",
            }
            assert body["input"][1] == {
                "role": "assistant",
                "content": "昨天记录不完整。",
            }
            return httpx2.Response(
                200,
                json={
                    "model": "gpt-5.6-luna-2026-07-01",
                    "output": [
                        {
                            "type": "function_call",
                            "id": "fc_1",
                            "call_id": "call_1",
                            "name": "get_today_summary",
                            "arguments": json.dumps({"date": None}),
                        }
                    ],
                    "usage": {"input_tokens": 50, "output_tokens": 10},
                },
            )
        assert body["tool_choice"] == "auto"
        tool_output = next(
            item for item in body["input"] if item.get("type") == "function_call_output"
        )
        assert tool_output["call_id"] == "call_1"
        assert json.loads(tool_output["output"])["summary"]["kcal"] == 520
        return httpx2.Response(
            200,
            json={
                "model": "gpt-5.6-luna-2026-07-01",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "今天已记录 520 kcal。"}],
                    }
                ],
                "usage": {"input_tokens": 80, "output_tokens": 20},
            },
        )

    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    )
    provider = OpenAIResponsesAssistantProvider(
        api_key="test-key",
        model="gpt-5.6-luna",
        base_url="https://api.openai.com/v1",
        timeout_seconds=8,
        client=client,
    )

    async def run_tool(name, arguments, call_id):
        assert name == "get_today_summary"
        assert arguments == {"date": None}
        assert call_id == "call_1"
        return ToolExecutionResult(
            tool_name="get_today_summary",
            payload={"summary": {"kcal": 520}},
            summary="2026-07-19 已记录 520 kcal。",
        )

    result = await provider.answer(
        AssistantQuestionRequest(
            question="我今天吃得怎么样？",
            reference_date=date(2026, 7, 19),
        ),
        run_tool,
        [
            AssistantContextMessage(
                role="user",
                content="我昨天怎么样？",
                reference_date=date(2026, 7, 18),
            ),
            AssistantContextMessage(role="assistant", content="昨天记录不完整。"),
        ],
    )

    assert request_count == 2
    assert result.answer == "今天已记录 520 kcal。"
    assert result.model == "gpt-5.6-luna-2026-07-01"
    assert result.input_tokens == 130
    assert result.output_tokens == 30
    assert result.evidence[0].call_id == "call_1"
    assert result.evidence[0].tool_name == "get_today_summary"
