import json
from copy import deepcopy

import pytest
from document_cpu_evaluation import validate_dataset, summarize_cpu_run


SOURCE = "原文證據。"
IDENTITY = {"id": "manual", "version": "v1", "source_sha256": "a" * 64}


def dataset() -> dict[str, object]:
    """Keep the same fifty annotated questions across report variants."""
    return {
        "schema_version": 1,
        "dataset_id": "cpu",
        "dataset_version": "v1",
        "document": IDENTITY,
        "questions": [
            {
                "id": f"q{ordinal}",
                "query": "文件說了什麼？",
                "answerability": "answerable",
                "required_information": ["完整原文"],
                "evidence": [{"text": SOURCE, "start": 0, "end": len(SOURCE), "locator": "L1-L1; chars[0,5)"}],
            }
            for ordinal in range(50)
        ],
    }


def run_and_reviews() -> tuple[dict[str, object], list[dict[str, object]]]:
    """Supply raw tool observations and separate explicit human checks."""
    result = {
        "status": "ok",
        "document": {"id": "manual", "version": "v1", "title": "手冊"},
        "index_version": "idx",
        "passages": [{"chunk_id": "one", "locator": "L1-L1; chars[0,5)", "text": SOURCE, "truncated": False}],
    }
    run = {
        "run_id": "run-1",
        "observations": [
            {
                "question_id": f"q{i}",
                "accepted_at_monotonic": i * 10.0,
                "finished_at_monotonic": i * 10.0 + 4.0,
                "elapsed_seconds": 4.0,
                "outcome": "ok",
                "result": deepcopy(result),
            }
            for i in range(50)
        ],
    }
    reviews = [
        {
            "run_id": "run-1",
            "question_id": f"q{i}",
            "reviewer": "reviewer-1",
            "reviewed_at_utc": "2026-11-10T01:00:00Z",
            "review_seconds": 300.0,
            "decision": "supported",
            "annotation_status": "valid",
            "checks": [{"status": "satisfied", "evidence": [{"chunk_id": "one", "locator": "L1-L1; chars[0,5)"}]}],
            "reason": "回傳原文涵蓋必要資訊",
        }
        for i in range(50)
    ]
    return run, reviews


@pytest.mark.parametrize(
    "fault",
    [
        "array",
        "bool",
        "duplicate-id",
        "unknown",
        "null",
        "wrong-source",
        "wrong-evidence",
        "query",
        "negative-with-gold",
        "duplicate-json",
        "nonfinite",
    ],
)
def test_dataset_rejects_unfrozen_or_invalid_gold(fault: str) -> None:
    """Malformed gold never silently changes the fifty-question cohort."""
    candidate = deepcopy(dataset())
    if fault == "array":
        candidate = ["question"] * 50
    elif fault == "bool":
        candidate["schema_version"] = True
    elif fault == "duplicate-id":
        candidate["questions"][1]["id"] = "q0"
    elif fault == "unknown":
        candidate["path"] = "secret"
    elif fault == "null":
        candidate["questions"][0]["required_information"] = None
    elif fault == "wrong-source":
        candidate["document"] = {**IDENTITY, "version": "v2"}
    elif fault == "wrong-evidence":
        candidate["questions"][0]["evidence"][0]["text"] = "編造證據。"
    elif fault == "query":
        candidate["questions"][0]["query"] = " " * 200 + "字"
    elif fault == "negative-with-gold":
        candidate["questions"][0]["answerability"] = "unanswerable"
    payload = json.dumps(candidate, ensure_ascii=False).encode()
    if fault == "duplicate-json":
        payload = payload.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1')
    if fault == "nonfinite":
        payload = payload.replace(b'"schema_version": 1', b'"schema_version": NaN')
    with pytest.raises(ValueError):
        validate_dataset(payload, IDENTITY, SOURCE)


def test_valid_gold_is_not_modified_or_automatically_calibrated() -> None:
    """Validated annotations remain byte-for-byte stable for freezing."""
    original = json.dumps(dataset(), ensure_ascii=False).encode()
    parsed = validate_dataset(original, IDENTITY, SOURCE)
    assert parsed == dataset()
    assert json.dumps(parsed, ensure_ascii=False).encode() == original


@pytest.mark.parametrize("supported", [0, 47, 48, 50])
def test_report_keeps_denominator_and_never_reinstates_quality_gate(supported: int) -> None:
    """Observed quality remains a count rather than a selection gate."""
    run, reviews = run_and_reviews()
    for review in reviews[supported:]:
        review.update(decision="unsupported", checks=[{"status": "missing", "evidence": []}])
    report = summarize_cpu_run(dataset(), run, reviews)
    assert report["denominator"] == 50
    assert report["supported"] == supported
    assert report["within_five_supported"] == supported
    assert report["unsupported_release"] == 50 - supported
    assert "passed" not in report
    assert report["supported_latency"] is None if supported == 0 else report["supported_latency"]["count"] == supported
    assert run["observations"][0]["elapsed_seconds"] == 4.0


@pytest.mark.parametrize("state", ["pending", "uncertain", "invalid", "slow", "failed", "negative"])
def test_unreviewed_unsupported_and_slow_observations_cannot_inflate_success(state: str) -> None:
    """Only timely, explicitly supported results count as five-second successes."""
    gold = dataset()
    run, reviews = run_and_reviews()
    if state == "pending":
        reviews[0] = {
            "run_id": "run-1",
            "question_id": "q0",
            "decision": "pending",
            "annotation_status": "pending",
            "checks": [],
            "reason": "待核對",
        }
    elif state == "uncertain":
        reviews[0].update(decision="uncertain", checks=[{"status": "uncertain", "evidence": []}])
    elif state == "invalid":
        reviews[0].update(
            decision="uncertain", annotation_status="invalid", checks=[], reason="annotation_invalid：原標註錯誤"
        )
    elif state == "slow":
        run["observations"][0].update(finished_at_monotonic=6.0, elapsed_seconds=6.0)
    elif state == "failed":
        run["observations"][0].update(
            outcome="document_timeout",
            result={"error": "document_timeout"},
            finished_at_monotonic=10.0,
            elapsed_seconds=10.0,
        )
        reviews[0].update(decision="not_applicable", checks=[])
    elif state == "negative":
        gold["questions"][0].update(answerability="unanswerable", required_information=[], evidence=[])
        reviews[0].update(decision="unsupported", checks=[])
    report = summarize_cpu_run(gold, run, reviews)
    assert report["denominator"] == 50
    assert report["within_five_supported"] == 49
    assert report["supported"] == (50 if state == "slow" else 49)


@pytest.mark.parametrize(
    "fault",
    [
        "wrong-run",
        "unknown",
        "missing-check",
        "invisible",
        "non-utc",
        "negative-time",
        "bad-elapsed",
        "nan",
        "missing-observation",
        "invalid-supported",
    ],
)
def test_invalid_review_or_timing_is_rejected_without_editing_raw_observations(fault: str) -> None:
    """Unverifiable reviews cannot rewrite raw tool outcomes or timings."""
    run, reviews = run_and_reviews()
    if fault == "wrong-run":
        reviews[0]["run_id"] = "another"
    elif fault == "unknown":
        reviews[0]["score"] = 1.0
    elif fault == "missing-check":
        reviews[0]["checks"] = []
    elif fault == "invisible":
        reviews[0]["checks"][0]["evidence"][0]["chunk_id"] = "not-returned"
    elif fault == "non-utc":
        reviews[0]["reviewed_at_utc"] = "2026-11-10T01:00:00"
    elif fault == "negative-time":
        reviews[0]["review_seconds"] = -1
    elif fault == "bad-elapsed":
        run["observations"][0]["elapsed_seconds"] = 3.0
    elif fault == "nan":
        run["observations"][0]["elapsed_seconds"] = float("nan")
    elif fault == "missing-observation":
        run["observations"].pop()
    elif fault == "invalid-supported":
        reviews[0]["annotation_status"] = "invalid"
    with pytest.raises(ValueError):
        summarize_cpu_run(dataset(), run, reviews)


def test_percentiles_use_all_fifty_and_separate_supported_subset() -> None:
    """All fifty latencies use nearest ranks independently of manual review."""
    run, reviews = run_and_reviews()
    for ordinal, observation in enumerate(run["observations"]):
        observation.update(
            elapsed_seconds=(ordinal + 1) / 10,
            finished_at_monotonic=observation["accepted_at_monotonic"] + (ordinal + 1) / 10,
        )
    report = summarize_cpu_run(dataset(), run, reviews)
    assert report["latency"] == {"count": 50, "p50": 2.5, "p95": 4.8, "max": 5.0}
