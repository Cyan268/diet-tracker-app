import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter

from app.ai.provider import FoodTextProvider, ProviderError, ProviderResult
from app.schemas.ai import AiUsage, FoodTextAnalyzeRequest, FoodTextAnalyzeResponse

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class AiCallTelemetry:
    provider: str
    model: str
    status: str
    fallback_used: bool
    latency_ms: int
    attempt_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal | None
    error_code: str | None


@dataclass(frozen=True)
class AnalysisExecution:
    response: FoodTextAnalyzeResponse
    telemetry: AiCallTelemetry


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_million: Decimal | None,
    output_price_per_million: Decimal | None,
) -> Decimal | None:
    if input_tokens == 0 and output_tokens == 0:
        return None
    if input_price_per_million is None or output_price_per_million is None:
        return None
    million = Decimal(1_000_000)
    return (
        Decimal(input_tokens) * input_price_per_million / million
        + Decimal(output_tokens) * output_price_per_million / million
    ).quantize(Decimal("0.00000001"))


def _warnings(
    result: ProviderResult,
    fallback_used: bool,
    primary_error: ProviderError | None,
) -> list[str]:
    warnings: list[str] = []
    if fallback_used:
        if primary_error and primary_error.code in {"http_401", "http_403"}:
            warnings.append("模型凭证无效或缺少权限，本次已使用规则降级；请检查 AI 服务设置。")
        elif primary_error and primary_error.code == "http_429":
            warnings.append("模型服务当前限流，本次已使用规则降级；请稍后重试并检查用量额度。")
        else:
            warnings.append("真实模型暂时不可用，本次已使用规则降级；请重点核对识别结果。")
    if not result.entities:
        warnings.append("没有识别到支持的食物，请补充食物名称和数量或改用手动记录。")
    if any(entity.needs_review for entity in result.entities):
        warnings.append("部分食物缺少明确数量或存在歧义，保存前请确认。")
    return warnings


async def analyze_food_text(
    request: FoodTextAnalyzeRequest,
    primary: FoodTextProvider,
    *,
    fallback: FoodTextProvider | None = None,
    max_attempts: int = 2,
    retry_delay_seconds: float = 0.15,
    input_price_per_million: Decimal | None = None,
    output_price_per_million: Decimal | None = None,
    sleep: Sleep = asyncio.sleep,
) -> AnalysisExecution:
    started = perf_counter()
    attempts = 0
    primary_error: ProviderError | None = None
    result: ProviderResult | None = None
    used_provider = primary
    fallback_used = False

    for attempt in range(max_attempts):
        attempts += 1
        try:
            result = await primary.extract(request)
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
        result = await fallback.extract(request)

    if result is None:
        if primary_error is not None:
            raise primary_error
        raise ProviderError("provider_failed", "provider returned no result", retryable=False)

    latency_ms = max(round((perf_counter() - started) * 1000), 0)
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
    response = FoodTextAnalyzeResponse(
        provider=used_provider.name,
        model=result.model,
        fallback_used=fallback_used,
        latency_ms=latency_ms,
        usage=usage,
        entities=result.entities,
        warnings=_warnings(result, fallback_used, primary_error),
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
    return AnalysisExecution(response=response, telemetry=telemetry)
