import hashlib
import json
import math
import time
import unicodedata
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.ai.provider import FoodTextProvider, ProviderError
from app.evals.schemas import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationMetrics,
    EvaluationReport,
    EvaluationSliceMetrics,
    FieldMatch,
)
from app.schemas.ai import FoodTextAnalyzeRequest, ParsedFoodEntity

SCHEMA_ERROR_CODES = {"schema_validation_failed", "empty_response", "invalid_response"}


def load_dataset(path: Path) -> EvaluationDataset:
    return EvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))


def dataset_fingerprint(dataset: EvaluationDataset) -> str:
    canonical = json.dumps(
        dataset.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_dataset_partition(
    development: EvaluationDataset,
    test: EvaluationDataset,
) -> None:
    """Reject unsafe development/test layouts before an evaluation is trusted."""
    if development.split != "development" or development.frozen:
        raise ValueError("development dataset must use split=development and frozen=false")
    if test.split != "test" or not test.frozen:
        raise ValueError("test dataset must use split=test and frozen=true")
    if development.contains_personal_data or test.contains_personal_data:
        raise ValueError("evaluation datasets must not contain personal data")

    development_groups = {case.group_id or case.id for case in development.cases}
    test_groups = {case.group_id or case.id for case in test.cases}
    leaked_groups = sorted(development_groups & test_groups)
    if leaked_groups:
        raise ValueError(
            "semantic groups must not cross development/test splits: " + ", ".join(leaked_groups)
        )


def _normalized_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(normalized.split()).casefold()


def _ratio(numerator: int, denominator: int, *, empty_value: float = 0.0) -> float:
    if denominator == 0:
        return empty_value
    return round(numerator / denominator, 4)


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return round(ordered[rank - 1], 2)


def _match_case(
    case: EvaluationCase,
    actual: list[ParsedFoodEntity],
    *,
    amount_absolute_tolerance: float,
) -> tuple[list[FieldMatch], list[str], list[str], bool]:
    unmatched_actual = set(range(len(actual)))
    matches: list[FieldMatch] = []
    false_negative_names: list[str] = []

    for expected in case.expected:
        expected_name = _normalized_name(expected.normalized_name)
        matched_index = next(
            (
                index
                for index in unmatched_actual
                if _normalized_name(actual[index].normalized_name) == expected_name
            ),
            None,
        )
        if matched_index is None:
            false_negative_names.append(expected.normalized_name)
            continue
        unmatched_actual.remove(matched_index)
        prediction = actual[matched_index]
        amount_matches = (
            expected.acceptable_amount_min <= prediction.amount <= expected.acceptable_amount_max
            if expected.acceptable_amount_min is not None
            and expected.acceptable_amount_max is not None
            else math.isclose(
                prediction.amount,
                expected.amount,
                rel_tol=0,
                abs_tol=amount_absolute_tolerance,
            )
        )
        matches.append(
            FieldMatch(
                normalized_name=expected.normalized_name,
                amount=amount_matches,
                unit=_normalized_name(prediction.unit) == _normalized_name(expected.unit),
                meal_type=prediction.meal_type == expected.meal_type,
            )
        )

    false_positive_names = [actual[index].normalized_name for index in sorted(unmatched_actual)]
    exact_match = (
        not false_positive_names
        and not false_negative_names
        and all(match.amount and match.unit and match.meal_type for match in matches)
    )
    return matches, false_positive_names, false_negative_names, exact_match


async def _evaluate_case(
    case: EvaluationCase,
    dataset: EvaluationDataset,
    provider: FoodTextProvider,
) -> EvaluationCaseResult:
    request = FoodTextAnalyzeRequest(
        text=case.text,
        log_date=dataset.evaluation_date,
        meal_type_hint=case.meal_type_hint,
        locale="zh-CN",
    )
    started_at = time.perf_counter()
    try:
        result = await provider.extract(request)
    except ProviderError as error:
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        schema_valid = False if error.code in SCHEMA_ERROR_CODES else None
        return EvaluationCaseResult(
            case_id=case.id,
            text=case.text,
            success=False,
            schema_valid=schema_valid,
            model=None,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            expected=case.expected,
            actual=[],
            matched_fields=[],
            false_positive_names=[],
            false_negative_names=[entity.normalized_name for entity in case.expected],
            exact_match=False,
            error_code=error.code,
        )
    except Exception as error:  # pragma: no cover - defensive boundary for external providers
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        return EvaluationCaseResult(
            case_id=case.id,
            text=case.text,
            success=False,
            schema_valid=None,
            model=None,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            expected=case.expected,
            actual=[],
            matched_fields=[],
            false_positive_names=[],
            false_negative_names=[entity.normalized_name for entity in case.expected],
            exact_match=False,
            error_code=f"unexpected_{type(error).__name__}",
        )

    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    matches, false_positives, false_negatives, exact_match = _match_case(
        case,
        result.entities,
        amount_absolute_tolerance=dataset.amount_absolute_tolerance,
    )
    return EvaluationCaseResult(
        case_id=case.id,
        text=case.text,
        success=True,
        schema_valid=True,
        model=result.model,
        latency_ms=latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        expected=case.expected,
        actual=result.entities,
        matched_fields=matches,
        false_positive_names=false_positives,
        false_negative_names=false_negatives,
        exact_match=exact_match,
    )


def _metrics(
    results: list[EvaluationCaseResult],
    *,
    input_price_per_million_usd: Decimal | None,
    output_price_per_million_usd: Decimal | None,
) -> EvaluationMetrics:
    sample_count = len(results)
    successful_cases = sum(result.success for result in results)
    schema_results = [result.schema_valid for result in results if result.schema_valid is not None]
    true_positives = sum(len(result.matched_fields) for result in results)
    false_positives = sum(len(result.false_positive_names) for result in results)
    false_negatives = sum(len(result.false_negative_names) for result in results)
    precision = _ratio(true_positives, true_positives + false_positives, empty_value=1.0)
    recall = _ratio(true_positives, true_positives + false_negatives, empty_value=1.0)
    f1 = 0.0 if precision + recall == 0 else round(2 * precision * recall / (precision + recall), 4)
    matches = [match for result in results for match in result.matched_fields]
    total_input_tokens = sum(result.input_tokens for result in results)
    total_output_tokens = sum(result.output_tokens for result in results)

    total_cost: Decimal | None = None
    average_cost: Decimal | None = None
    if input_price_per_million_usd is not None and output_price_per_million_usd is not None:
        total_cost = (
            Decimal(total_input_tokens) * input_price_per_million_usd
            + Decimal(total_output_tokens) * output_price_per_million_usd
        ) / Decimal(1_000_000)
        total_cost = total_cost.quantize(Decimal("0.00000001"))
        average_cost = (total_cost / Decimal(sample_count)).quantize(Decimal("0.00000001"))

    return EvaluationMetrics(
        sample_count=sample_count,
        successful_cases=successful_cases,
        failed_cases=sample_count - successful_cases,
        request_success_rate=_ratio(successful_cases, sample_count),
        schema_evaluated_cases=len(schema_results),
        schema_validity_rate=(
            _ratio(sum(value is True for value in schema_results), len(schema_results))
            if schema_results
            else None
        ),
        true_positive_entities=true_positives,
        false_positive_entities=false_positives,
        false_negative_entities=false_negatives,
        entity_precision=precision,
        entity_recall=recall,
        entity_f1=f1,
        amount_accuracy=(
            _ratio(sum(match.amount for match in matches), len(matches)) if matches else None
        ),
        unit_accuracy=(
            _ratio(sum(match.unit for match in matches), len(matches)) if matches else None
        ),
        meal_type_accuracy=(
            _ratio(sum(match.meal_type for match in matches), len(matches)) if matches else None
        ),
        case_exact_match_rate=_ratio(sum(result.exact_match for result in results), sample_count),
        p50_latency_ms=_percentile([result.latency_ms for result in results], 0.5),
        p95_latency_ms=_percentile([result.latency_ms for result in results], 0.95),
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        average_tokens_per_case=round((total_input_tokens + total_output_tokens) / sample_count, 2),
        estimated_total_cost_usd=total_cost,
        estimated_average_cost_usd=average_cost,
        cost_status="known" if total_cost is not None else "unknown",
    )


def _tag_metrics(
    dataset: EvaluationDataset,
    results: list[EvaluationCaseResult],
) -> dict[str, EvaluationSliceMetrics]:
    result_by_id = {result.case_id: result for result in results}
    metrics: dict[str, EvaluationSliceMetrics] = {}
    for tag in sorted({tag for case in dataset.cases for tag in case.tags}):
        tagged = [result_by_id[case.id] for case in dataset.cases if tag in case.tags]
        successful = sum(result.success for result in tagged)
        metrics[tag] = EvaluationSliceMetrics(
            sample_count=len(tagged),
            successful_cases=successful,
            request_success_rate=_ratio(successful, len(tagged)),
            case_exact_match_rate=_ratio(sum(result.exact_match for result in tagged), len(tagged)),
        )
    return metrics


async def evaluate_dataset(
    dataset: EvaluationDataset,
    provider: FoodTextProvider,
    *,
    input_price_per_million_usd: Decimal | None = None,
    output_price_per_million_usd: Decimal | None = None,
    code_revision: str = "unknown",
) -> EvaluationReport:
    results = [await _evaluate_case(case, dataset, provider) for case in dataset.cases]
    observed_models = sorted({result.model for result in results if result.model is not None})
    provider_model = (
        ",".join(observed_models) if observed_models else getattr(provider, "model", None)
    )
    if not isinstance(provider_model, str):
        provider_model = "unknown"
    return EvaluationReport(
        dataset_schema_version=dataset.dataset_schema_version,
        dataset_version=dataset.dataset_version,
        dataset_split=dataset.split,
        dataset_fingerprint_sha256=dataset_fingerprint(dataset),
        code_revision=code_revision,
        provider=provider.name,
        model=provider_model,
        prompt_version=getattr(provider, "prompt_version", "unknown"),
        generated_at=datetime.now(UTC),
        evaluation_config={
            "locale": dataset.locale,
            "evaluation_date": dataset.evaluation_date.isoformat(),
            "amount_absolute_tolerance": dataset.amount_absolute_tolerance,
            "prices_configured": (
                input_price_per_million_usd is not None and output_price_per_million_usd is not None
            ),
        },
        metrics=_metrics(
            results,
            input_price_per_million_usd=input_price_per_million_usd,
            output_price_per_million_usd=output_price_per_million_usd,
        ),
        tag_metrics=_tag_metrics(dataset, results),
        failure_counts=dict(
            sorted(
                {
                    code: sum(result.error_code == code for result in results)
                    for code in {result.error_code for result in results if result.error_code}
                }.items()
            )
        ),
        cases=results,
    )


def write_report(report: EvaluationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
