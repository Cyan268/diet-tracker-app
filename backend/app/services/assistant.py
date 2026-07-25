import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import AssistantProvider, AssistantProviderResult, ProviderError
from app.schemas.ai import AiUsage
from app.schemas.assistant import (
    AssistantAnswerResponse,
    AssistantContextMessage,
    AssistantQuestionRequest,
)
from app.services.ai import AiCallTelemetry, estimate_cost
from app.services.assistant_tools import ToolExecutionResult, execute_assistant_tool

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class AssistantExecution:
    response: AssistantAnswerResponse
    telemetry: AiCallTelemetry


def _fallback_warning(error: ProviderError | None) -> str:
    if error and error.code in {"http_401", "http_403"}:
        return "模型凭证无效或缺少权限，本次已使用本地只读助手；请检查 AI 服务设置。"
    if error and error.code == "http_429":
        return "模型服务当前限流，本次已使用本地只读助手；请稍后重试并检查额度。"
    return "真实模型暂时不可用，本次已使用本地只读助手，结论仅按固定规则生成。"


async def answer_assistant_question(
    session: AsyncSession,
    user_id: UUID,
    request: AssistantQuestionRequest,
    primary: AssistantProvider,
    *,
    fallback: AssistantProvider | None = None,
    max_attempts: int = 2,
    retry_delay_seconds: float = 0.15,
    input_price_per_million: Decimal | None = None,
    output_price_per_million: Decimal | None = None,
    history: list[AssistantContextMessage] | None = None,
    sleep: Sleep = asyncio.sleep,
) -> AssistantExecution:
    async def run_tool(
        tool_name: str,
        arguments: dict[str, Any],
        _: str,
    ) -> ToolExecutionResult:
        return await execute_assistant_tool(
            session,
            user_id,
            tool_name,
            arguments,
            request.reference_date,
        )

    started_at = perf_counter()
    attempts = 0
    primary_error: ProviderError | None = None
    result: AssistantProviderResult | None = None
    used_provider = primary
    fallback_used = False

    for attempt in range(max_attempts):
        attempts += 1
        try:
            result = await primary.answer(request, run_tool, history)
            break
        except ProviderError as error:
            primary_error = error
            if not error.retryable or attempt + 1 >= max_attempts:
                break
            await sleep(retry_delay_seconds * (2**attempt))

    if result is None and fallback is not None:
        attempts += 1
        fallback_used = True
        used_provider = fallback
        result = await fallback.answer(request, run_tool, history)

    if result is None:
        if primary_error is not None:
            raise primary_error
        raise ProviderError("provider_failed", "assistant returned no result", retryable=False)

    latency_ms = max(round((perf_counter() - started_at) * 1000), 0)
    total_tokens = result.input_tokens + result.output_tokens
    estimated_cost = estimate_cost(
        result.input_tokens,
        result.output_tokens,
        input_price_per_million,
        output_price_per_million,
    )
    usage = AiUsage(
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost,
    )
    warnings = [_fallback_warning(primary_error)] if fallback_used else []
    response = AssistantAnswerResponse(
        answer=result.answer,
        provider=used_provider.name,
        model=result.model,
        prompt_version=used_provider.prompt_version,
        fallback_used=fallback_used,
        latency_ms=latency_ms,
        usage=usage,
        evidence=result.evidence,
        warnings=warnings,
    )
    telemetry = AiCallTelemetry(
        provider=used_provider.name,
        model=result.model,
        status="fallback" if fallback_used else "success",
        fallback_used=fallback_used,
        latency_ms=latency_ms,
        attempt_count=attempts,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost,
        error_code=primary_error.code if fallback_used and primary_error else None,
    )
    return AssistantExecution(response=response, telemetry=telemetry)
