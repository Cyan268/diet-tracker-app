import asyncio
import json
import selectors
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import dispose_engine, session_factory  # noqa: E402
from app.services.catalog_seed import seed_global_catalog  # noqa: E402
from app.services.food_matching import (  # noqa: E402
    AMBIGUITY_MARGIN,
    MATCH_RECALL_THRESHOLD,
    PRESELECT_THRESHOLD,
    match_visible_foods,
)

DATASET_PATH = BACKEND_DIR / "evals" / "food_matching_v1.json"


def _assert_isolated_database() -> None:
    from app.core.config import get_settings

    url = make_url(get_settings().database_url)
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("food matching evaluation only permits a loopback PostgreSQL host")
    if url.database != "nutripilot_u4_test":
        raise RuntimeError("food matching evaluation requires database nutripilot_u4_test")


def _target_matches(candidate, case: dict[str, object]) -> bool:
    return candidate.name == case.get("expectedName") and candidate.brand == case.get(
        "expectedBrand"
    )


async def _evaluate() -> dict[str, object]:
    _assert_isolated_database()
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    expected_thresholds = dataset["thresholds"]
    actual_thresholds = {
        "recall": MATCH_RECALL_THRESHOLD,
        "preselect": PRESELECT_THRESHOLD,
        "ambiguityMargin": AMBIGUITY_MARGIN,
    }
    if expected_thresholds != actual_thresholds:
        raise RuntimeError(
            f"dataset thresholds {expected_thresholds} do not match code {actual_thresholds}"
        )

    counters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    failures: list[dict[str, object]] = []
    async with session_factory() as session:
        await seed_global_catalog(session)
        for case in dataset["cases"]:
            split = case["split"]
            decision = await match_visible_foods(
                session,
                user_id=__import__("uuid").UUID(int=0),
                query=case["query"],
                brand=case.get("brand"),
            )
            counter = counters[split]
            counter["cases"] += 1
            status_correct = decision.status == case["expectedStatus"]
            counter["status_correct"] += int(status_correct)

            has_target = "expectedName" in case
            target_in_candidates = has_target and any(
                _target_matches(candidate, case) for candidate in decision.candidates
            )
            top1_correct = (
                has_target
                and bool(decision.candidates)
                and _target_matches(decision.candidates[0], case)
            )
            if has_target:
                counter["target_cases"] += 1
                counter["candidate_hits"] += int(target_in_candidates)
                counter["top1_hits"] += int(top1_correct)
            if decision.preselected_food_item_id is not None:
                counter["preselected"] += 1
                counter["correct_preselected"] += int(top1_correct)

            if not status_correct or (has_target and not top1_correct):
                failures.append(
                    {
                        "id": case["id"],
                        "expectedStatus": case["expectedStatus"],
                        "actualStatus": decision.status,
                        "actualTop1": (
                            {
                                "name": decision.candidates[0].name,
                                "brand": decision.candidates[0].brand,
                                "score": decision.candidates[0].score,
                                "reason": decision.candidates[0].reason,
                            }
                            if decision.candidates
                            else None
                        ),
                    }
                )

    metrics: dict[str, dict[str, float | int]] = {}
    for split, counter in counters.items():
        metrics[split] = {
            "cases": counter["cases"],
            "statusAccuracy": counter["status_correct"] / counter["cases"],
            "candidateRecall": counter["candidate_hits"] / counter["target_cases"],
            "top1Accuracy": counter["top1_hits"] / counter["target_cases"],
            "preselectionPrecision": (
                counter["correct_preselected"] / counter["preselected"]
                if counter["preselected"]
                else 1.0
            ),
        }
    return {
        "datasetVersion": dataset["datasetVersion"],
        "thresholds": actual_thresholds,
        "metrics": metrics,
        "failures": failures,
        "minimums": dataset["minimums"],
    }


def _selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


async def _run() -> int:
    try:
        report = await _evaluate()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        minimums = report["minimums"]
        failed = bool(report["failures"])
        for metrics in report["metrics"].values():
            failed = failed or any(metrics[name] < minimum for name, minimum in minimums.items())
        return int(failed)
    finally:
        await dispose_engine()


def main() -> None:
    loop_factory = _selector_loop if sys.platform == "win32" else None
    raise SystemExit(asyncio.run(_run(), loop_factory=loop_factory))


if __name__ == "__main__":
    main()
