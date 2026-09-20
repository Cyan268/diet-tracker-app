import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.evals.runner import (  # noqa: E402
    dataset_fingerprint,
    load_dataset,
    validate_dataset_partition,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AI evaluation dataset isolation")
    parser.add_argument(
        "--development",
        type=Path,
        default=BACKEND_DIR / "evals" / "food_text_dev_v1.json",
    )
    parser.add_argument(
        "--test",
        type=Path,
        default=BACKEND_DIR / "evals" / "food_text_v1.json",
    )
    parser.add_argument("--minimum-total-cases", type=int, default=100)
    parser.add_argument("--minimum-test-cases", type=int, default=40)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    development = load_dataset(arguments.development)
    test = load_dataset(arguments.test)
    validate_dataset_partition(development, test)
    total_cases = len(development.cases) + len(test.cases)
    if total_cases < arguments.minimum_total_cases:
        raise SystemExit(
            f"evaluation corpus requires at least {arguments.minimum_total_cases} cases; "
            f"received {total_cases}"
        )
    if len(test.cases) < arguments.minimum_test_cases:
        raise SystemExit(
            f"frozen test split requires at least {arguments.minimum_test_cases} cases; "
            f"received {len(test.cases)}"
        )
    print(
        "Evaluation datasets valid: "
        f"development={len(development.cases)} "
        f"({dataset_fingerprint(development)}), "
        f"test={len(test.cases)} ({dataset_fingerprint(test)}), total={total_cases}"
    )


if __name__ == "__main__":
    main()
