import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.evals.annotation_review import (  # noqa: E402
    compare_blind_review,
    create_blind_review_bundle,
    load_review_bundle,
    write_review_artifact,
)
from app.evals.runner import load_dataset  # noqa: E402

DEFAULT_DATASET = BACKEND_DIR / "evals" / "food_text_v1.json"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or compare blind annotation reviews")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export", help="create a blind review template")
    export.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    export.add_argument("--reviewer", required=True)
    export.add_argument("--output", type=Path, required=True)

    compare = subparsers.add_parser("compare", help="compare completed labels after blind review")
    compare.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    compare.add_argument("--review", type=Path, required=True)
    compare.add_argument("--output", type=Path)
    compare.add_argument(
        "--require-complete",
        action="store_true",
        help="return a failure when pending or uncertain cases remain",
    )
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    dataset = load_dataset(arguments.dataset)
    if arguments.command == "export":
        bundle = create_blind_review_bundle(dataset, arguments.reviewer)
        write_review_artifact(bundle, arguments.output)
        print(f"Wrote blind review template with {len(bundle.cases)} cases to {arguments.output}")
        return

    review = load_review_bundle(arguments.review)
    report = compare_blind_review(dataset, review)
    if arguments.output is not None:
        write_review_artifact(report, arguments.output)
        print(f"Wrote annotation review report to {arguments.output}")
    else:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print(
        "Annotation review summary: "
        f"coverage={report.review_coverage_rate}, "
        f"agreement={report.exact_agreement_rate}, "
        f"disagreements={len(report.disagreement_case_ids)}, "
        f"uncertain={report.uncertain_count}, pending={report.pending_count}"
    )
    if arguments.require_complete and (report.pending_count or report.uncertain_count):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
