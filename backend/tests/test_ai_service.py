from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

from app.ai import ProviderError, ProviderResult
from app.schemas.ai import FoodTextAnalyzeRequest, ParsedFoodEntity
from app.services.ai import analyze_food_text, estimate_cost


class FakeProvider:
    def __init__(self, name: str, outcomes: list[ProviderResult | ProviderError]) -> None:
        self.name = name
        self.outcomes = outcomes
        self.calls = 0

    async def extract(self, _: FoodTextAnalyzeRequest) -> ProviderResult:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome


def request() -> FoodTextAnalyzeRequest:
    return FoodTextAnalyzeRequest(text="午餐鸡胸肉", log_date=date(2026, 7, 17))


def success() -> ProviderResult:
    return ProviderResult(
        entities=[
            ParsedFoodEntity(
                raw_name="鸡胸肉",
                normalized_name="鸡胸肉（水煮）",
                amount=1,
                unit="份",
                meal_type="lunch",
                confidence=0.8,
                needs_review=True,
                evidence="识别到鸡胸肉",
            )
        ],
        model="test-model",
        input_tokens=100,
        output_tokens=20,
    )


async def test_retryable_failure_is_retried_before_success() -> None:
    provider = FakeProvider(
        "openai_responses",
        [ProviderError("timeout", "timeout", retryable=True), success()],
    )
    sleep = AsyncMock()

    execution = await analyze_food_text(request(), provider, sleep=sleep)

    assert provider.calls == 2
    sleep.assert_awaited_once_with(0.15)
    assert execution.telemetry.status == "success"
    assert execution.telemetry.attempt_count == 2
    assert execution.response.usage.total_tokens == 120


async def test_exhausted_retryable_failure_uses_rule_fallback() -> None:
    primary = FakeProvider(
        "openai_responses",
        [
            ProviderError("http_429", "rate limited", retryable=True),
            ProviderError("http_429", "rate limited", retryable=True),
        ],
    )
    fallback = FakeProvider("rule_based_v1", [success()])

    execution = await analyze_food_text(request(), primary, fallback=fallback, sleep=AsyncMock())

    assert primary.calls == 2
    assert fallback.calls == 1
    assert execution.response.fallback_used is True
    assert execution.telemetry.status == "fallback"
    assert execution.telemetry.attempt_count == 3
    assert execution.telemetry.error_code == "http_429"
    assert execution.response.warnings


async def test_non_retryable_failure_skips_retry_and_uses_fallback() -> None:
    primary = FakeProvider(
        "openai_responses",
        [ProviderError("schema_validation_failed", "invalid", retryable=False)],
    )
    fallback = FakeProvider("rule_based_v1", [success()])
    sleep = AsyncMock()

    execution = await analyze_food_text(request(), primary, fallback=fallback, sleep=sleep)

    assert primary.calls == 1
    assert fallback.calls == 1
    sleep.assert_not_awaited()
    assert execution.telemetry.attempt_count == 2


async def test_invalid_credential_fallback_explains_how_to_recover() -> None:
    primary = FakeProvider(
        "openai_responses",
        [ProviderError("http_401", "invalid key", retryable=False)],
    )
    fallback = FakeProvider("rule_based_v1", [success()])

    execution = await analyze_food_text(request(), primary, fallback=fallback)

    assert "凭证无效" in execution.response.warnings[0]
    assert "AI 服务设置" in execution.response.warnings[0]


def test_cost_is_only_calculated_with_explicit_prices() -> None:
    assert estimate_cost(1000, 500, None, None) is None
    assert estimate_cost(1000, 500, Decimal("2"), Decimal("8")) == Decimal("0.00600000")
