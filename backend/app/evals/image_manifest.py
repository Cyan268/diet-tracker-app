from pathlib import Path

from app.evals.image_schemas import ImageEvaluationManifest


def load_image_manifest(path: Path) -> ImageEvaluationManifest:
    return ImageEvaluationManifest.model_validate_json(path.read_text(encoding="utf-8"))


def validate_image_manifest_partition(
    development: ImageEvaluationManifest,
    test: ImageEvaluationManifest,
    *,
    minimum_total_groups: int = 30,
    minimum_test_groups: int = 10,
) -> None:
    if development.split != "development" or development.frozen:
        raise ValueError("development image manifest must be non-frozen development data")
    if test.split != "test" or not test.frozen:
        raise ValueError("test image manifest must be frozen test data")

    development_groups = {case.group_id for case in development.cases}
    test_groups = {case.group_id for case in test.cases}
    leaked_groups = sorted(development_groups & test_groups)
    if leaked_groups:
        raise ValueError("image groups cross dataset splits: " + ", ".join(leaked_groups))

    development_hashes = {case.asset_sha256 for case in development.cases}
    test_hashes = {case.asset_sha256 for case in test.cases}
    leaked_assets = sorted(development_hashes & test_hashes)
    if leaked_assets:
        raise ValueError("image assets cross dataset splits: " + ", ".join(leaked_assets))

    total_groups = len(development_groups) + len(test_groups)
    if total_groups < minimum_total_groups:
        raise ValueError(
            f"image evaluation requires at least {minimum_total_groups} semantic groups; "
            f"received {total_groups}"
        )
    if len(test_groups) < minimum_test_groups:
        raise ValueError(
            f"image test split requires at least {minimum_test_groups} semantic groups; "
            f"received {len(test_groups)}"
        )
