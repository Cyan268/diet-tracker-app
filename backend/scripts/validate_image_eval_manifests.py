import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.evals.image_manifest import (  # noqa: E402
    load_image_manifest,
    validate_image_manifest_partition,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate licensed image evaluation manifests")
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--minimum-total-groups", type=int, default=30)
    parser.add_argument("--minimum-test-groups", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    development = load_image_manifest(arguments.development)
    test = load_image_manifest(arguments.test)
    validate_image_manifest_partition(
        development,
        test,
        minimum_total_groups=arguments.minimum_total_groups,
        minimum_test_groups=arguments.minimum_test_groups,
    )
    development_groups = {case.group_id for case in development.cases}
    test_groups = {case.group_id for case in test.cases}
    print(
        "Image evaluation manifests valid: "
        f"development_cases={len(development.cases)}, "
        f"development_groups={len(development_groups)}, "
        f"test_cases={len(test.cases)}, test_groups={len(test_groups)}"
    )


if __name__ == "__main__":
    main()
