import json
from datetime import UTC, datetime
from pathlib import Path

from app.evals.review_schemas import (
    AnnotationReviewReport,
    BlindReviewBundle,
    BlindReviewCase,
)
from app.evals.runner import dataset_fingerprint
from app.evals.schemas import EvaluationDataset, ExpectedFoodEntity

REVIEW_INSTRUCTIONS = (
    "只根据原始文本独立标注实际已经摄入的食物，不查看现有标签、模型输出或评测报告。"
    "确认为无食物输入时使用 completed 和空列表；无法可靠判断时使用 uncertain 并填写原因。"
)


def create_blind_review_bundle(
    dataset: EvaluationDataset,
    reviewer_id: str,
    *,
    created_at: datetime | None = None,
) -> BlindReviewBundle:
    if reviewer_id in dataset.annotators:
        raise ValueError("blind reviewer must be independent from existing dataset annotators")
    return BlindReviewBundle(
        dataset_version=dataset.dataset_version,
        dataset_fingerprint_sha256=dataset_fingerprint(dataset),
        reviewer_id=reviewer_id,
        created_at=created_at or datetime.now(UTC),
        instructions=REVIEW_INSTRUCTIONS,
        cases=[
            BlindReviewCase(
                case_id=case.id,
                text=case.text,
                meal_type_hint=case.meal_type_hint,
            )
            for case in dataset.cases
        ],
    )


def _canonical_entities(entities: list[ExpectedFoodEntity]) -> list[dict[str, object]]:
    return sorted(
        (entity.model_dump(mode="json", exclude_none=True) for entity in entities),
        key=lambda entity: str(entity["normalized_name"]).casefold(),
    )


def compare_blind_review(
    dataset: EvaluationDataset,
    review: BlindReviewBundle,
) -> AnnotationReviewReport:
    expected_fingerprint = dataset_fingerprint(dataset)
    if review.dataset_version != dataset.dataset_version:
        raise ValueError("review dataset version does not match the current dataset")
    if review.dataset_fingerprint_sha256 != expected_fingerprint:
        raise ValueError("review dataset fingerprint does not match the current dataset")
    if review.reviewer_id in dataset.annotators:
        raise ValueError("reviewer must be independent from existing dataset annotators")

    expected_ids = {case.id for case in dataset.cases}
    reviewed_ids = {case.case_id for case in review.cases}
    if reviewed_ids != expected_ids:
        missing = sorted(expected_ids - reviewed_ids)
        extra = sorted(reviewed_ids - expected_ids)
        raise ValueError(f"review coverage mismatch; missing={missing}, extra={extra}")

    dataset_cases = {case.id: case for case in dataset.cases}
    completed = [case for case in review.cases if case.status == "completed"]
    uncertain = [case for case in review.cases if case.status == "uncertain"]
    pending = [case for case in review.cases if case.status == "pending"]
    disagreements = [
        case.case_id
        for case in completed
        if _canonical_entities(case.proposed_expected or [])
        != _canonical_entities(dataset_cases[case.case_id].expected)
    ]
    exact_agreements = len(completed) - len(disagreements)
    return AnnotationReviewReport(
        dataset_version=dataset.dataset_version,
        dataset_fingerprint_sha256=expected_fingerprint,
        reviewer_id=review.reviewer_id,
        sample_count=len(review.cases),
        completed_count=len(completed),
        uncertain_count=len(uncertain),
        pending_count=len(pending),
        review_coverage_rate=round((len(completed) + len(uncertain)) / len(review.cases), 4),
        exact_agreement_rate=(round(exact_agreements / len(completed), 4) if completed else None),
        disagreement_case_ids=sorted(disagreements),
        uncertain_case_ids=sorted(case.case_id for case in uncertain),
        pending_case_ids=sorted(case.case_id for case in pending),
    )


def load_review_bundle(path: Path) -> BlindReviewBundle:
    return BlindReviewBundle.model_validate_json(path.read_text(encoding="utf-8"))


def write_review_artifact(
    bundle_or_report: BlindReviewBundle | AnnotationReviewReport, path: Path
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            bundle_or_report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
