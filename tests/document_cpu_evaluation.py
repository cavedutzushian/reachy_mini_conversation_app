"""Validate offline CPU acceptance artifacts without adding application behavior."""

import re
import math
from datetime import datetime, timedelta

from reachy_mini_conversation_app.document_assets import PreparationError, parse_object, source_line_numbers
from reachy_mini_conversation_app.document_retrieval import (
    valid_identifier,
    validate_document_query,
    validate_document_result,
)


def checked_object(
    value: object, required: set[str], optional: set[str] | frozenset[str] = frozenset()
) -> dict[str, object]:
    """Reject missing, unknown and null fields in acceptance records."""
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - optional:
        raise ValueError("Invalid acceptance record fields")
    if any(item is None for item in value.values()):
        raise ValueError("Null acceptance field")
    return dict(value)


def nonnegative_seconds(value: object) -> float:
    """Keep raw measurement values finite without treating booleans as numbers."""
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid acceptance time")
    return float(value)


def validate_dataset(payload: bytes, document: dict[str, object], source: str | None) -> dict[str, object]:
    """Validate frozen gold against its designated source before any CPU observations."""
    try:
        parsed = parse_object(payload)
    except (PreparationError, UnicodeError) as error:
        raise ValueError("Invalid acceptance JSON") from error
    dataset = checked_object(parsed, {"schema_version", "dataset_id", "dataset_version", "document", "questions"})
    if type(dataset["schema_version"]) is not int or dataset["schema_version"] != 1:
        raise ValueError("Invalid dataset version")
    if not all(valid_identifier(dataset[key]) for key in ("dataset_id", "dataset_version")):
        raise ValueError("Invalid dataset identity")
    identity = checked_object(dataset["document"], {"id", "version", "source_sha256"})
    if (
        not all(valid_identifier(identity[key]) for key in ("id", "version"))
        or not isinstance(identity["source_sha256"], str)
        or re.fullmatch("[0-9a-f]{64}", identity["source_sha256"]) is None
        or identity != {key: document.get(key) for key in identity}
    ):
        raise ValueError("Dataset source mismatch")
    questions = dataset["questions"]
    if not isinstance(questions, list) or len(questions) != 50:
        raise ValueError("Exactly fifty annotated questions are required")
    identifiers: set[str] = set()
    lines = source_line_numbers(source) if source is not None else None
    for candidate in questions:
        question = checked_object(candidate, {"id", "query", "answerability", "required_information", "evidence"})
        query = question["query"]
        if not valid_identifier(question["id"]) or question["id"] in identifiers:
            raise ValueError("Invalid question identity")
        identifiers.add(str(question["id"]))
        if not isinstance(query, str) or not 1 <= len(query) <= 200 or validate_document_query(query) is None:
            raise ValueError("Invalid acceptance query")
        required, evidence = question["required_information"], question["evidence"]
        if not isinstance(required, list) or not all(isinstance(item, str) and item.strip() for item in required):
            raise ValueError("Invalid required information")
        if not isinstance(evidence, list) or question["answerability"] not in ("answerable", "unanswerable"):
            raise ValueError("Invalid answerability")
        if (question["answerability"] == "answerable") != bool(required and evidence):
            raise ValueError("Missing frozen evidence")
        if question["answerability"] == "unanswerable" and (required or evidence):
            raise ValueError("Unanswerable gold must be empty")
        for entry in evidence:
            quote = checked_object(entry, {"text", "start", "end", "locator"})
            start, end, text = quote["start"], quote["end"], quote["text"]
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end
                or not isinstance(text, str)
                or len(text) != end - start
                or not isinstance(quote["locator"], str)
                or re.fullmatch(rf"L[1-9][0-9]*-L[1-9][0-9]*; chars\[{start},{end}\)", quote["locator"]) is None
            ):
                raise ValueError("Invalid gold evidence interval")
            if source is not None and (
                end > len(source)
                or text != source[start:end]
                or quote["locator"] != f"L{lines[start]}-L{lines[end - 1]}; chars[{start},{end})"
            ):
                raise ValueError("Gold does not match the source evidence")

    return dataset


def latency_summary(durations: list[float]) -> dict[str, object] | None:
    """Report nearest-rank percentiles without dropping failures from the caller's cohort."""
    if not durations:
        return None
    ordered = sorted(durations)
    return {
        "count": len(ordered),
        "p50": ordered[math.ceil(0.5 * len(ordered)) - 1],
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "max": ordered[-1],
    }


def summarize_cpu_run(dataset: dict[str, object], run: dict[str, object], reviews: object) -> dict[str, object]:
    """Join immutable observations with explicit human checks while preserving all fifty questions."""
    questions, observations = dataset["questions"], run["observations"]
    if (
        not isinstance(questions, list)
        or not isinstance(observations, list)
        or len(questions) != 50
        or len(observations) != 50
    ):
        raise ValueError("Incomplete CPU denominator")
    if not valid_identifier(run["run_id"]) or not isinstance(reviews, list) or len(reviews) != 50:
        raise ValueError("Incomplete manual review")
    review_by_id: dict[str, dict[str, object]] = {}
    for entry in reviews:
        review = checked_object(
            entry,
            {"run_id", "question_id", "decision", "annotation_status", "checks", "reason"},
            {"reviewer", "reviewed_at_utc", "review_seconds"},
        )
        identifier = review["question_id"]
        if not valid_identifier(identifier) or identifier in review_by_id or review["run_id"] != run["run_id"]:
            raise ValueError("Review identity mismatch")
        review_by_id[str(identifier)] = review
    counts: dict[str, int] = dict.fromkeys(
        (
            "ok",
            "supported",
            "within_five_supported",
            "over_five_supported",
            "unsupported_release",
            "pending",
            "uncertain",
            "annotation_invalid",
            "expected_refusal",
            "over_ten_seconds",
        ),
        0,
    )
    durations, supported_durations, review_durations = [], [], []
    previous_finish = 0.0
    for question, candidate in zip(questions, observations, strict=True):
        observation = checked_object(
            candidate,
            {"question_id", "accepted_at_monotonic", "finished_at_monotonic", "elapsed_seconds", "outcome", "result"},
        )
        if observation["question_id"] != question["id"]:
            raise ValueError("Observation order changed")
        accepted, finished, elapsed = (
            nonnegative_seconds(observation[key])
            for key in ("accepted_at_monotonic", "finished_at_monotonic", "elapsed_seconds")
        )
        if finished < accepted or not math.isclose(elapsed, finished - accepted, abs_tol=1e-6, rel_tol=1e-9):
            raise ValueError("Observation latency changed")
        if accepted < previous_finish:
            raise ValueError("CPU observations overlap or moved backwards")
        previous_finish = finished
        result = validate_document_result(observation["result"])
        outcome = "ok" if result.get("status") == "ok" else str(result["error"])
        if outcome != observation["outcome"]:
            raise ValueError("Observation outcome changed")
        if outcome == "ok":
            identity = result["document"]
            if any(identity[key] != dataset["document"][key] for key in ("id", "version")):
                raise ValueError("Observed source changed")
        counts[outcome] = counts.get(outcome, 0) + 1
        durations.append(elapsed)
        counts["over_ten_seconds"] += int(elapsed > 10)
        review = review_by_id.get(question["id"])
        if review is None:
            raise ValueError("Missing review identity")
        decision, annotation = review["decision"], review["annotation_status"]
        if decision not in (
            "pending",
            "supported",
            "unsupported",
            "uncertain",
            "not_applicable",
        ) or annotation not in ("pending", "valid", "invalid"):
            raise ValueError("Invalid manual decision")
        if not isinstance(review["reason"], str) or not review["reason"].strip():
            raise ValueError("Missing manual reason")
        if decision != "pending" or any(key in review for key in ("reviewer", "reviewed_at_utc", "review_seconds")):
            if not valid_identifier(review.get("reviewer")) or not isinstance(review.get("reviewed_at_utc"), str):
                raise ValueError("Missing manual reviewer")
            reviewed = datetime.fromisoformat(review["reviewed_at_utc"].replace("Z", "+00:00"))
            if reviewed.tzinfo is None or reviewed.utcoffset() != timedelta(0):
                raise ValueError("Review timestamp must be UTC")
            review_durations.append(nonnegative_seconds(review.get("review_seconds")))
        checks = review["checks"]
        if not isinstance(checks, list):
            raise ValueError("Invalid manual checks")
        if annotation == "invalid":
            if decision != "uncertain" or "annotation_invalid" not in review["reason"]:
                raise ValueError("Invalid annotations cannot support success")
            counts["annotation_invalid"] += 1
        elif decision == "pending":
            if annotation not in ("pending", "valid") or checks:
                raise ValueError("Pending reviews cannot contain completed checks")
        elif outcome != "ok":
            if decision != "not_applicable" or checks:
                raise ValueError("Failed tools cannot support evidence")
        else:
            required = question["required_information"]
            if annotation != "valid" or len(checks) != len(required):
                raise ValueError("Manual checks must cover every required item")
            passages = {entry["chunk_id"]: entry["locator"] for entry in result["passages"]}
            statuses = []
            for item in checks:
                check = checked_object(item, {"status", "evidence"})
                if check["status"] not in ("satisfied", "missing", "uncertain") or not isinstance(
                    check["evidence"], list
                ):
                    raise ValueError("Invalid requirement check")
                for entry in check["evidence"]:
                    citation = checked_object(entry, {"chunk_id", "locator"})
                    if (
                        not isinstance(citation["chunk_id"], str)
                        or passages.get(citation["chunk_id"]) != citation["locator"]
                    ):
                        raise ValueError("Manual evidence was not returned")
                if check["status"] == "satisfied" and not check["evidence"]:
                    raise ValueError("Satisfied checks need returned evidence")
                statuses.append(check["status"])
            expected = (
                "unsupported"
                if question["answerability"] == "unanswerable" or "missing" in statuses
                else "uncertain"
                if "uncertain" in statuses
                else "supported"
            )
            if decision != expected:
                raise ValueError("Manual decision contradicts its checks")
        if decision in ("pending", "uncertain"):
            counts[decision] += 1
        if outcome == "ok" and decision == "supported" and annotation == "valid":
            counts["supported"] += 1
            counts["within_five_supported"] += int(elapsed <= 5)
            counts["over_five_supported"] += int(elapsed > 5)
            supported_durations.append(elapsed)
        elif outcome == "ok" and decision == "unsupported":
            counts["unsupported_release"] += 1
        if question["answerability"] == "unanswerable" and outcome == "document_no_evidence":
            counts["expected_refusal"] += 1
    return {
        "denominator": 50,
        **counts,
        "latency": latency_summary(durations),
        "supported_latency": latency_summary(supported_durations),
        "manual_review_seconds": sum(review_durations),
    }
