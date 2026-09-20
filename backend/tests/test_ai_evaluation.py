from pathlib import Path

from app.ai import ProviderError, ProviderResult, RuleBasedFoodTextProvider
from app.evals.runner import evaluate_dataset, load_dataset, validate_dataset_partition
from app.evals.schemas import EvaluationCase, EvaluationDataset, ExpectedFoodEntity
from app.schemas.ai import ParsedFoodEntity

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASET_PATH = BACKEND_DIR / "evals" / "food_text_v1.json"
DEVELOPMENT_DATASET_PATH = BACKEND_DIR / "evals" / "food_text_dev_v1.json"


async def test_rule_provider_matches_committed_quality_baseline() -> None:
    dataset = load_dataset(DATASET_PATH)

    report = await evaluate_dataset(dataset, RuleBasedFoodTextProvider())

    assert report.report_schema_version == "2.0"
    assert report.dataset_schema_version == "2.0"
    assert report.dataset_version == "food-text-zh-cn-v1.2.0"
    assert report.dataset_split == "test"
    assert len(report.dataset_fingerprint_sha256) == 64
    assert report.code_revision == "unknown"
    assert report.provider == "rule_based_v1"
    assert report.model == "rule-based-v1"
    assert report.prompt_version == "rule-food-text-v1.0.0"
    assert report.metrics.sample_count == 40
    assert report.metrics.schema_validity_rate == 1
    assert report.metrics.true_positive_entities == 37
    assert report.metrics.false_positive_entities == 12
    assert report.metrics.false_negative_entities == 8
    assert report.metrics.entity_precision == 0.7551
    assert report.metrics.entity_recall == 0.8222
    assert report.metrics.entity_f1 == 0.7872
    assert report.metrics.case_exact_match_rate == 0.5
    assert report.metrics.amount_accuracy == 0.9189
    assert report.metrics.unit_accuracy == 0.973
    assert report.metrics.meal_type_accuracy == 0.973
    assert report.metrics.cost_status == "unknown"
    assert report.tag_metrics["multi_entity"].sample_count > 0
    assert report.failure_counts == {}


def test_development_and_test_datasets_are_safely_partitioned() -> None:
    development = load_dataset(DEVELOPMENT_DATASET_PATH)
    test = load_dataset(DATASET_PATH)

    validate_dataset_partition(development, test)

    assert development.split == "development"
    assert development.frozen is False
    assert test.split == "test"
    assert test.frozen is True
    assert development.contains_personal_data is False
    assert test.contains_personal_data is False
    assert len(development.cases) == 60
    assert len(test.cases) == 40


def test_semantic_group_leakage_is_rejected() -> None:
    development = load_dataset(DEVELOPMENT_DATASET_PATH)
    test = load_dataset(DATASET_PATH)
    leaked_case = development.cases[0].model_copy(
        update={"group_id": test.cases[0].group_id or test.cases[0].id}
    )
    unsafe_development = development.model_copy(
        update={"cases": [leaked_case, *development.cases[1:]]}
    )

    try:
        validate_dataset_partition(unsafe_development, test)
    except ValueError as error:
        assert "must not cross" in str(error)
    else:  # pragma: no cover - makes the failure message explicit
        raise AssertionError("expected cross-split semantic group leakage to be rejected")


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
        dataset_schema_version="2.0",
        dataset_version="test-v1",
        description="验证 Schema 错误和传输错误使用不同的统计分母",
        split="development",
        frozen=False,
        source="测试代码人工构造",
        authorization="项目自有测试数据",
        annotators=["test_fixture_author"],
        annotation_protocol="测试夹具直接给出预期实体",
        contains_personal_data=False,
        grouping_policy="每条测试夹具为独立组",
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
    assert report.metrics.cost_status == "unknown"
    assert report.failure_counts == {"network_error": 1, "schema_validation_failed": 1}
    assert report.cases[1].schema_valid is False
    assert report.cases[2].schema_valid is None


async def test_explicit_amount_range_is_used_instead_of_fake_exactness() -> None:
    expected = ExpectedFoodEntity(
        normalized_name="苹果",
        amount=100,
        unit="g",
        meal_type="snack",
        acceptable_amount_min=90,
        acceptable_amount_max=110,
    )
    dataset = small_dataset().model_copy(
        update={
            "cases": [
                EvaluationCase(
                    id="amount_range",
                    text="苹果大约100克",
                    expected=[expected],
                )
            ]
        }
    )

    class RangeProvider:
        name = "range_provider"
        prompt_version = "range-v1"
        model = "range-model"

        async def extract(self, request):
            del request
            return ProviderResult(
                entities=[
                    ParsedFoodEntity(
                        raw_name="苹果",
                        normalized_name="苹果",
                        amount=105,
                        unit="g",
                        meal_type="snack",
                        confidence=0.7,
                        needs_review=True,
                        evidence="估算",
                    )
                ],
                model=self.model,
            )

    report = await evaluate_dataset(dataset, RangeProvider())

    assert report.metrics.amount_accuracy == 1
    assert report.metrics.case_exact_match_rate == 1
