import argparse
import asyncio
import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.ai import OpenAIResponsesFoodTextProvider, RuleBasedFoodTextProvider  # noqa: E402
from app.evals.runner import evaluate_dataset, load_dataset, write_report  # noqa: E402
from app.evals.schemas import EvaluationReport  # noqa: E402

DEFAULT_DATASET = BACKEND_DIR / "evals" / "food_text_v1.json"


def _optional_decimal(environment_name: str) -> Decimal | None:
    raw_value = os.getenv(environment_name)
    if raw_value is None or not raw_value.strip():
        return None
    try:
        value = Decimal(raw_value)
    except InvalidOperation as error:
        raise SystemExit(f"{environment_name} must be a decimal number") from error
    if value < 0:
        raise SystemExit(f"{environment_name} must not be negative")
    return value


def _provider(arguments: argparse.Namespace):
    if arguments.provider == "rule_based":
        return RuleBasedFoodTextProvider()
    if not arguments.allow_paid_api:
        raise SystemExit(
            "OpenAI evaluation can incur charges. Re-run with --allow-paid-api after reviewing "
            "the dataset size."
        )
    api_key = os.getenv("NUTRIPILOT_OPENAI_API_KEY")
    if api_key is None or not api_key.strip():
        raise SystemExit("NUTRIPILOT_OPENAI_API_KEY is required for OpenAI evaluation")
    return OpenAIResponsesFoodTextProvider(
        api_key=api_key,
        model=os.getenv("NUTRIPILOT_OPENAI_MODEL", "gpt-5.6-luna"),
        base_url=os.getenv("NUTRIPILOT_OPENAI_BASE_URL", "https://api.openai.com/v1"),
        timeout_seconds=float(os.getenv("NUTRIPILOT_AI_TIMEOUT_SECONDS", "20")),
    )


def _check_baseline(report: EvaluationReport, path: Path) -> list[str]:
    baseline = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if baseline.get("dataset_version") != report.dataset_version:
        failures.append(
            f"dataset_version expected {baseline.get('dataset_version')}, "
            f"received {report.dataset_version}"
        )
    if baseline.get("provider") != report.provider:
        failures.append(f"provider expected {baseline.get('provider')}, received {report.provider}")
    metrics = report.metrics.model_dump(mode="python")
    for metric_name, minimum in baseline.get("minimums", {}).items():
        actual = metrics.get(metric_name)
        if actual is None or actual < minimum:
            failures.append(f"{metric_name} expected >= {minimum}, received {actual}")
    return failures


async def _run(arguments: argparse.Namespace) -> int:
    dataset = load_dataset(arguments.dataset)
    if arguments.max_cases is not None:
        dataset = dataset.model_copy(update={"cases": dataset.cases[: arguments.max_cases]})
    provider = _provider(arguments)
    report = await evaluate_dataset(
        dataset,
        provider,
        input_price_per_million_usd=_optional_decimal("NUTRIPILOT_AI_INPUT_PRICE_PER_MILLION_USD"),
        output_price_per_million_usd=_optional_decimal(
            "NUTRIPILOT_AI_OUTPUT_PRICE_PER_MILLION_USD"
        ),
    )
    if arguments.output is not None:
        write_report(report, arguments.output)
        print(f"Wrote evaluation report to {arguments.output}")
    else:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))

    metrics = report.metrics
    print(
        "AI eval summary: "
        f"cases={metrics.sample_count}, schema={metrics.schema_validity_rate}, "
        f"precision={metrics.entity_precision}, recall={metrics.entity_recall}, "
        f"f1={metrics.entity_f1}, exact={metrics.case_exact_match_rate}, "
        f"p95_ms={metrics.p95_latency_ms}"
    )
    if arguments.baseline is not None:
        failures = _check_baseline(report, arguments.baseline)
        if failures:
            print("Regression baseline failed:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            return 1
        print(f"Regression baseline passed: {arguments.baseline}")
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the food-text AI provider")
    parser.add_argument("--provider", choices=("rule_based", "openai"), default="rule_based")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--max-cases", type=int, choices=range(1, 1001))
    parser.add_argument(
        "--allow-paid-api",
        action="store_true",
        help="acknowledge that the OpenAI evaluation may incur API charges",
    )
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_arguments())))


if __name__ == "__main__":
    main()
