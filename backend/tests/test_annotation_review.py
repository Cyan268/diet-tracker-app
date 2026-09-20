from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.evals.annotation_review import compare_blind_review, create_blind_review_bundle
from app.evals.review_schemas import BlindReviewBundle
from app.evals.runner import load_dataset

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASET_PATH = BACKEND_DIR / "evals" / "food_text_v1.json"


def test_blind_review_export_hides_ground_truth_and_model_output() -> None:
    dataset = load_dataset(DATASET_PATH)

    bundle = create_blind_review_bundle(
        dataset,
        "reviewer_two",
        created_at=datetime(2026, 9, 16, tzinfo=UTC),
    )
    payload = bundle.model_dump_json()

    assert len(bundle.cases) == 40
    assert bundle.blind is True
    assert all(case.status == "pending" for case in bundle.cases)
    assert all(case.proposed_expected is None for case in bundle.cases)
    assert '"expected"' not in payload
    case_fields = set(bundle.cases[0].model_dump())
    assert "expected" not in case_fields
    assert "actual" not in case_fields
    assert "tags" not in case_fields


def test_completed_review_reports_agreement_and_disagreement() -> None:
    dataset = load_dataset(DATASET_PATH)
    bundle = create_blind_review_bundle(dataset, "reviewer_two")
    completed_cases = []
    for index, review_case in enumerate(bundle.cases):
        expected = dataset.cases[index].expected
        if index == 1:
            expected = []
        completed_cases.append(
            review_case.model_copy(update={"status": "completed", "proposed_expected": expected})
        )
    completed_bundle = bundle.model_copy(update={"cases": completed_cases})

    report = compare_blind_review(dataset, completed_bundle)

    assert report.sample_count == 40
    assert report.completed_count == 40
    assert report.review_coverage_rate == 1
    assert report.exact_agreement_rate == 0.975
    assert report.disagreement_case_ids == [dataset.cases[1].id]
    assert report.pending_case_ids == []


def test_review_rejects_existing_annotator_and_stale_dataset() -> None:
    dataset = load_dataset(DATASET_PATH)

    with pytest.raises(ValueError, match="independent"):
        create_blind_review_bundle(dataset, "project_author")

    bundle = create_blind_review_bundle(dataset, "reviewer_two")
    stale_payload = bundle.model_dump(mode="json")
    stale_payload["dataset_fingerprint_sha256"] = "0" * 64
    stale_bundle = BlindReviewBundle.model_validate(stale_payload)

    with pytest.raises(ValueError, match="fingerprint"):
        compare_blind_review(dataset, stale_bundle)
