from datetime import date

import pytest
from pydantic import ValidationError

from app.evals.image_manifest import validate_image_manifest_partition
from app.evals.image_schemas import (
    ExpectedImageFood,
    ImageEvaluationCase,
    ImageEvaluationManifest,
)


def image_case(
    case_id: str,
    group_id: str,
    asset_hash: str,
    *,
    annotators: list[str],
) -> ImageEvaluationCase:
    return ImageEvaluationCase(
        id=case_id,
        group_id=group_id,
        asset_reference=f"private-eval/{case_id}.png",
        asset_sha256=asset_hash,
        source_type="self_captured",
        authorization_reference=f"self-capture-record:{case_id}",
        contains_personal_data=False,
        captured_on=date(2026, 9, 17),
        annotated_on=date(2026, 9, 17),
        scene_tags=["single_food"],
        annotators=annotators,
        expected_outcome="recognition",
        expected_foods=[
            ExpectedImageFood(
                normalized_name="苹果",
                amount=150,
                unit="g",
                amount_basis="weighed",
                basis_reference=f"scale-record:{case_id}",
            )
        ],
    )


def manifest(
    split: str,
    frozen: bool,
    cases: list[ImageEvaluationCase],
) -> ImageEvaluationManifest:
    return ImageEvaluationManifest(
        manifest_schema_version="1.0",
        dataset_version=f"image-food-{split}-v1",
        description="授权图片评测测试夹具",
        split=split,
        frozen=frozen,
        source="项目测试夹具",
        authorization="测试夹具由项目生成并授权",
        contains_personal_data=False,
        grouping_policy="同一食物图片变体共享 group_id",
        cases=cases,
    )


def test_valid_image_manifests_require_provenance_review_and_measurement_basis() -> None:
    development = manifest(
        "development",
        False,
        [image_case("dev_image", "dev_group", "1" * 64, annotators=["author"])],
    )
    test = manifest(
        "test",
        True,
        [
            image_case(
                "test_image",
                "test_group",
                "2" * 64,
                annotators=["author", "reviewer_two"],
            )
        ],
    )

    validate_image_manifest_partition(
        development,
        test,
        minimum_total_groups=2,
        minimum_test_groups=1,
    )


def test_image_manifest_rejects_cross_split_group_leakage() -> None:
    development = manifest(
        "development",
        False,
        [image_case("dev_image", "shared_group", "1" * 64, annotators=["author"])],
    )
    test = manifest(
        "test",
        True,
        [
            image_case(
                "test_image",
                "shared_group",
                "2" * 64,
                annotators=["author", "reviewer_two"],
            )
        ],
    )

    with pytest.raises(ValueError, match="cross dataset splits"):
        validate_image_manifest_partition(
            development,
            test,
            minimum_total_groups=1,
            minimum_test_groups=1,
        )


def test_image_amount_and_frozen_review_cannot_be_faked() -> None:
    with pytest.raises(ValidationError, match="evidence reference"):
        ExpectedImageFood(
            normalized_name="苹果",
            amount=150,
            unit="g",
            amount_basis="weighed",
        )

    one_annotator_case = image_case(
        "test_image",
        "test_group",
        "2" * 64,
        annotators=["author"],
    )
    with pytest.raises(ValidationError, match="at least two annotators"):
        manifest("test", True, [one_annotator_case])


def test_unknown_image_amount_must_not_include_invented_grams() -> None:
    with pytest.raises(ValidationError, match="must not contain an amount"):
        ExpectedImageFood(
            normalized_name="麻辣香锅",
            amount=300,
            unit="g",
            amount_basis="unknown",
        )
