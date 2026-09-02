from pathlib import Path

from app.ai import ProviderError, ProviderResult, RuleBasedFoodTextProvider
from app.evals.runner import evaluate_dataset, load_dataset
from app.evals.schemas import EvaluationCase, EvaluationDataset, ExpectedFoodEntity
from app.schemas.ai import ParsedFoodEntity

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASET_PATH = BACKEND_DIR / "evals" / "food_text_v1.json"


async def test_rule_provider_matches_committed_quality_baseline() -> None:
    dataset = load_dataset(DATASET_PATH)

    report = await evaluate_dataset(dataset, RuleBasedFoodTextProvider())

    assert report.dataset_version == "food-text-zh-cn-v1.0.0"
    assert report.provider == "rule_based_v1"
    assert report.model == "rule-based-v1"
    assert report.prompt_version == "rule-food-text-v1.0.0"
    assert report.metrics.sample_count == 26
    assert report.metrics.schema_validity_rate == 1
    assert report.metrics.true_positive_entities == 26
    assert report.metrics.false_positive_entities == 6
    assert report.metrics.false_negative_entities == 6
    assert report.metrics.entity_precision == 0.8125
    assert report.metrics.entity_recall == 0.8125
    assert report.metrics.entity_f1 == 0.8125
    assert report.metrics.case_exact_match_rate == 0.6538
    assert report.metrics.amount_accuracy == 1
    assert report.metrics.unit_accuracy == 1
    assert report.metrics.meal_type_accuracy == 1


class OutcomeProvider:
    name = "outcome_provider"
    prompt_version = "test-prompt-v1"
    model = "test-model"

    async def extract(self, request):
        if request.text == "schema failure":
            raise ProviderError("schema_validation_failed", "invalid", retryable=False)
        if request.text == "network failure":
            raise ProviderError("network_error", "offline", retryable=True)
        return ProviderResult(
            entities=[
                ParsedFoodEntity(
                    raw_name="苹果",
                    normalized_name="苹果",
                    amount=1,
                    unit="个",
                    meal_type="snack",
                    confidence=0.9,
                    needs_review=False,
                    evidence="测试样本包含苹果",
                )
            ],
            model=self.model,
            input_tokens=10,
            output_tokens=5,
        )


def small_dataset() -> EvaluationDataset:
    expected = [
        ExpectedFoodEntity(
            normalized_name="苹果",
            amount=1,
            unit="个",
            meal_type="snack",
        )
    ]
    return EvaluationDataset(
        dataset_version="test-v1",
        description="验证 Schema 错误和传输错误使用不同的统计分母",
        evaluation_date="2026-07-19",
        cases=[
            EvaluationCase(id="success_case", text="success apple", expected=expected),
            EvaluationCase(id="schema_case", text="schema failure", expected=expected),
            EvaluationCase(id="network_case", text="network failure", expected=expected),
        ],
    )


async def test_schema_validity_excludes_transport_failures() -> None:
    report = await evaluate_dataset(small_dataset(), OutcomeProvider())

    assert report.metrics.successful_cases == 1
    assert report.metrics.failed_cases == 2
    assert report.metrics.request_success_rate == 0.3333
    assert report.metrics.schema_evaluated_cases == 2
    assert report.metrics.schema_validity_rate == 0.5
    assert report.metrics.total_input_tokens == 10
    assert report.metrics.total_output_tokens == 5
    assert report.cases[1].schema_valid is False
    assert report.cases[2].schema_valid is None
