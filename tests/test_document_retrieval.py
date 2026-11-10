"""Behavior checks for the bounded local retrieval runtime."""

import os
import sys
import json
import time
import uuid
import asyncio
import hashlib
import platform
import subprocess
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

import psutil
import pytest
from document_cpu_evaluation import checked_object, validate_dataset, summarize_cpu_run

from reachy_mini_conversation_app import document_retrieval
from reachy_mini_conversation_app.document_assets import read_object, parse_object, file_inventory
from reachy_mini_conversation_app.gemini_realtime import GeminiRealtimeHandler
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.huggingface_realtime import ToolInvocation, HuggingFaceRealtimeHandler
from reachy_mini_conversation_app.tools.search_document import SearchDocument
from reachy_mini_conversation_app.tools.background_tool_manager import ToolState, ToolNotification


WORKER_SCRIPT = """
import json
import sys
import time
print(json.dumps({"type": "ready", "version": 1}), flush=True)
for line in sys.stdin:
    message = json.loads(line)
    if message["type"] == "close":
        break
    if message["query"] == "slow":
        time.sleep(0.2)
    if message["query"] == "bad-json":
        print("sensitive-query-sentinel", flush=True)
        continue
    if message["query"] == "oversized":
        print("x" * 65537, flush=True)
        continue
    if message["query"] == "wrong-id":
        message["request_id"] = "retired-id"
    if message["query"] == "wrong-version":
        print(json.dumps({"version": 2, "type": "result", "request_id": message["request_id"]}), flush=True)
        continue
    if message["query"] == "wrong-type":
        print(json.dumps({"version": 1, "type": "unknown", "request_id": message["request_id"]}), flush=True)
        continue
    print(json.dumps({"type": "result", "version": 1, "request_id": message["request_id"],
        "payload": {"error": "document_no_evidence"}}), flush=True)
"""


@pytest.fixture
def worker_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Run the runtime against a deterministic private-pipe child."""
    worker = tmp_path / "fake_worker.py"
    worker.write_text(WORKER_SCRIPT, encoding="utf-8")
    original_popen = subprocess.Popen

    def launch(_command, **kwargs):
        return original_popen([sys.executable, "-u", str(worker)], **kwargs)

    monkeypatch.setattr(document_retrieval.subprocess, "Popen", launch)
    runtime = document_retrieval.DocumentRuntime(tmp_path / "package", tmp_path / "model", tmp_path / "reranker")
    yield runtime
    runtime.close()


async def wait_ready(runtime) -> None:
    """Wait for initialization without replaying the triggering query."""
    assert await runtime.query("first") == {"error": "document_not_ready"}
    deadline = time.monotonic() + 5
    while runtime.state == "loading" and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert runtime.state == "ready"


@pytest.mark.asyncio
@pytest.mark.parametrize("paths", [(None, None), (Path("package"), None), (None, Path("model"))])
async def test_unconfigured_runtime_does_not_start_worker(monkeypatch: pytest.MonkeyPatch, paths) -> None:
    """Missing paths leave ordinary conversation independent of a worker."""

    def reject_launch(*args, **kwargs):
        raise AssertionError("Worker must not start")

    monkeypatch.setattr(document_retrieval.subprocess, "Popen", reject_launch)
    runtime = document_retrieval.DocumentRuntime(*paths)
    assert await runtime.query("question") == {"error": "document_not_ready"}
    runtime.close()


@pytest.mark.asyncio
async def test_worker_completes_one_request_and_closes_early(worker_runtime) -> None:
    """A ready child returns a bounded result and exits without waiting nine seconds."""
    await wait_ready(worker_runtime)
    assert await worker_runtime.query("question") == {"error": "document_no_evidence"}
    started = time.monotonic()
    worker_runtime.close()
    assert time.monotonic() - started < 2
    assert worker_runtime.state == "closed"


@pytest.mark.asyncio
async def test_timeout_keeps_slot_until_real_completion(worker_runtime, monkeypatch: pytest.MonkeyPatch) -> None:
    """A retired waiter never admits another CPU job before the old job ends."""
    monkeypatch.setattr(document_retrieval, "QUERY_TIMEOUT_S", 0.04)
    await wait_ready(worker_runtime)
    assert await worker_runtime.query("slow") == {"error": "document_timeout"}
    assert await worker_runtime.query("next") == {"error": "document_busy"}
    monkeypatch.setattr(document_retrieval, "QUERY_TIMEOUT_S", 10.0)
    deadline = time.monotonic() + 5
    while worker_runtime.state == "busy" and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert worker_runtime.state == "ready"
    assert await worker_runtime.query("next") == {"error": "document_no_evidence"}


@pytest.mark.asyncio
@pytest.mark.parametrize("question", ["bad-json", "oversized", "wrong-id", "wrong-version", "wrong-type"])
async def test_invalid_protocol_fails_without_echoing_worker_output(
    worker_runtime, question: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed worker output retires retrieval without disclosing raw payloads."""
    await wait_ready(worker_runtime)
    assert await worker_runtime.query(question) == {"error": "document_unavailable"}
    assert "sensitive-query-sentinel" not in caplog.text
    assert worker_runtime.state == "failed"


def test_lightweight_runtime_import_does_not_load_optional_dependencies() -> None:
    """Normal installations can import the runtime without loading any inference stack."""
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import reachy_mini_conversation_app.document_retrieval; "
            "assert not {'torch', 'chromadb', 'sentence_transformers'} & set(sys.modules)",
        ],
        check=True,
    )


@pytest.mark.asyncio
async def test_cancelled_waiter_keeps_single_cpu_slot(worker_runtime) -> None:
    """Cancelling a conversation waiter does not cancel the underlying CPU request."""
    await wait_ready(worker_runtime)
    request = asyncio.create_task(worker_runtime.query("slow"))
    await asyncio.sleep(0.02)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert await worker_runtime.query("next") == {"error": "document_busy"}
    deadline = time.monotonic() + 5
    while worker_runtime.state == "busy" and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert await worker_runtime.query("next") == {"error": "document_no_evidence"}


@pytest.mark.asyncio
async def test_backend_replacement_reuses_the_injected_worker(worker_runtime, monkeypatch) -> None:
    """Replacing adapters does not create a second document runtime or worker."""
    launch = MagicMock(side_effect=document_retrieval.subprocess.Popen)
    monkeypatch.setattr(document_retrieval.subprocess, "Popen", launch)
    deps = ToolDependencies(MagicMock(), MagicMock(), document_retrieval=worker_runtime)
    first = HuggingFaceRealtimeHandler(deps)
    await wait_ready(first.deps.document_retrieval)
    replacement = GeminiRealtimeHandler(deps, session_state=first.session_state)
    assert await SearchDocument()(replacement.deps, query="question") == {"error": "document_no_evidence"}
    assert launch.call_count == 1
    assert replacement.deps.document_retrieval is first.deps.document_retrieval


@pytest.mark.asyncio
async def test_initialization_deadline_never_accepts_late_ready(tmp_path, monkeypatch) -> None:
    """A child finishing initialization late cannot revive a failed runtime."""
    worker = tmp_path / "late_worker.py"
    worker.write_text("import time; time.sleep(0.2)\n" + WORKER_SCRIPT, encoding="utf-8")
    original_popen = subprocess.Popen
    launches = []

    def launch(_command, **kwargs):
        launches.append(True)
        return original_popen([sys.executable, "-u", str(worker)], **kwargs)

    monkeypatch.setattr(document_retrieval.subprocess, "Popen", launch)
    monkeypatch.setattr(document_retrieval, "INITIALIZATION_TIMEOUT_S", 0.04)
    runtime = document_retrieval.DocumentRuntime(tmp_path, tmp_path, tmp_path)
    try:
        assert await runtime.query("first") == {"error": "document_not_ready"}
        await asyncio.sleep(0.35)
        assert runtime.state == "failed"
        assert await runtime.query("second") == {"error": "document_not_ready"}
        assert len(launches) == 1
    finally:
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kill_exits", [True, False])
async def test_shutdown_has_one_nine_second_budget_and_preserves_unconfirmed_copy(
    tmp_path, monkeypatch, caplog, kill_exits: bool
) -> None:
    """Staged shutdown only deletes its owned copy after the process is confirmed dead."""
    clock = SimpleNamespace(now=0.0)
    waits = []
    actions = []
    work = tmp_path / "owned-copy"
    work.mkdir()
    original = tmp_path / "original"
    original.mkdir()
    (original / "sentinel").write_text("unchanged", encoding="utf-8")
    runtime = document_retrieval.DocumentRuntime(original, tmp_path / "model", tmp_path / "reranker")
    runtime._started.set()
    process = SimpleNamespace(poll=lambda: None)

    def wait(*, timeout):
        waits.append(timeout)
        clock.now += timeout
        if len(waits) == 3 and kill_exits:
            return 0
        raise subprocess.TimeoutExpired("private-path-sentinel", timeout)

    process.wait = wait
    process.terminate = lambda: actions.append("terminate")
    process.kill = lambda: actions.append("kill")
    monkeypatch.setattr(runtime, "_process", process)
    monkeypatch.setattr(runtime, "_work_directory", work)
    monkeypatch.setattr(document_retrieval, "time", SimpleNamespace(monotonic=lambda: clock.now))
    runtime.close()
    assert waits == [5.0, 2.0, 2.0]
    assert actions == ["terminate", "kill"]
    assert clock.now == 9.0
    assert work.exists() is not kill_exits
    assert (original / "sentinel").read_text(encoding="utf-8") == "unchanged"
    assert ("cleanup_incomplete" in caplog.text) is not kill_exits
    assert "private-path-sentinel" not in caplog.text


@pytest.mark.asyncio
async def test_external_cpu_fifty_question_benchmark(tmp_path: Path) -> None:
    """Freeze one CPU run or apply manual reviews without repeating tool queries."""
    previous, manual_path = (os.environ.get(key) for key in ("RAG_ACCEPTANCE_RUN", "RAG_ACCEPTANCE_REVIEWS"))
    cache = Path(__file__).resolve().parents[1] / "cache" / "004-single-document-rag"
    if previous:
        assert Path(previous).resolve().parent.is_relative_to(cache.resolve()), (
            "Acceptance reports stay in workspace cache"
        )
        run = read_object(Path(previous))
        payload = run["dataset_utf8"].encode("utf-8")
        assert hashlib.sha256(payload).hexdigest() == run["dataset_sha256"]
        gold = validate_dataset(payload, run["document"], None)
        output = Path(previous).resolve().parent
    else:
        supplied = [
            os.environ.get(key)
            for key in (
                "RAG_ACCEPTANCE_PACKAGE",
                "RAG_ACCEPTANCE_MODEL",
                "RAG_ACCEPTANCE_RERANKER",
                "RAG_ACCEPTANCE_QUESTIONS",
            )
        ]
        if (
            os.environ.get("RUN_DOCUMENT_CPU_ACCEPTANCE") != "1"
            or os.environ.get("RAG_ACCEPTANCE_GOLD_REVIEWED") != "1"
            or not all(supplied)
        ):
            pytest.skip("Explicit CPU opt-in, two role models, package and annotated fifty-question gold required")
        package, model, reranker, questions_path = (Path(value) for value in supplied)
        manifest = read_object(package / "manifest.json")
        assert manifest["schema_version"] == 2 and manifest["chunk_count"] <= 1000
        assert manifest["chunking"]["embedding_input_max_tokens"] == 512
        records = [parse_object(line) for line in (package / "retrieval/chunks.jsonl").read_bytes().splitlines()]
        source = [None] * max(record["end"] for record in records)
        for record in records:
            for offset, character in enumerate(record["text"], record["start"]):
                assert source[offset] in (None, character)
                source[offset] = character
        assert all(isinstance(character, str) for character in source)
        payload = questions_path.read_bytes()
        gold = validate_dataset(payload, manifest["document"], "".join(source))
        run_id = uuid.uuid4().hex
        output = Path(__file__).resolve().parents[1] / "cache" / "004-single-document-rag" / "cpu" / run_id
        output.mkdir(parents=True)
        run = {
            "schema_version": 1,
            "run_id": run_id,
            "dataset_id": gold["dataset_id"],
            "dataset_version": gold["dataset_version"],
            "dataset_utf8": payload.decode("utf-8"),
            "dataset_sha256": hashlib.sha256(payload).hexdigest(),
            "document": gold["document"],
            "index_version": manifest["index_version"],
            "package_inventory_sha256": hashlib.sha256(
                json.dumps(file_inventory(package), sort_keys=True).encode()
            ).hexdigest(),
            "model_receipts": {
                role: {
                    "receipt_sha256": hashlib.sha256((directory / "model-receipt.json").read_bytes()).hexdigest(),
                    "revision": read_object(directory / "model-receipt.json")["revision"],
                    "runtime": read_object(directory / "model-receipt.json")["runtime"],
                }
                for role, directory in (("embedding", model), ("reranker", reranker))
            },
            "host": {
                "platform": platform.platform(),
                "cpu": platform.processor(),
                "machine": platform.machine(),
                "python": sys.version,
                "logical_cpu_count": os.cpu_count(),
                "ram_bytes": psutil.virtual_memory().total,
            },
            "lock_sha256": hashlib.sha256((Path(__file__).resolve().parents[1] / "uv.lock").read_bytes()).hexdigest(),
            "threads": {"intra_op": 2, "inter_op": 1},
            "rss_sampling_interval_seconds": 0.02,
            "rss_sampling_method": "parent RSS and largest recursive descendant RSS; not summed physical RAM",
            "audio_availability": "not_evaluated",
            "observations": [],
            "between_query_wait_seconds": [],
        }
        (output / "cpu-input.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        runtime = document_retrieval.DocumentRuntime(package, model, reranker)
        tool = SearchDocument()
        deps = ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime)
        parent, peaks, sampling = psutil.Process(), {"parent": 0, "worker": 0}, True

        async def sample_memory() -> None:
            while sampling:
                peaks["parent"] = max(peaks["parent"], parent.memory_info().rss)
                for child in parent.children(recursive=True):
                    try:
                        peaks["worker"] = max(peaks["worker"], child.memory_info().rss)
                    except psutil.NoSuchProcess:
                        document_retrieval.logger.info("CPU acceptance worker exited during RSS sampling")
                await asyncio.sleep(0.02)

        memory_task = asyncio.create_task(sample_memory())
        cold_start = time.monotonic()
        try:
            probe = await tool(deps, query="初始化文件檢索")
            run["initialization_probe_result"] = probe
            assert probe == {"error": "document_not_ready"}
            while runtime.state == "loading" and time.monotonic() - cold_start <= 121:
                await asyncio.sleep(0.05)
            run["cold_seconds"], run["startup_state"] = time.monotonic() - cold_start, runtime.state
            assert runtime.state == "ready", "CPU worker not ready; preserve partial run"
            previous_finish = time.monotonic()
            for question in gold["questions"]:
                accepted = time.monotonic()
                result = await tool(deps, query=question["query"])
                finished = time.monotonic()
                run["between_query_wait_seconds"].append(accepted - previous_finish)
                run["observations"].append(
                    {
                        "question_id": question["id"],
                        "accepted_at_monotonic": accepted,
                        "finished_at_monotonic": finished,
                        "elapsed_seconds": finished - accepted,
                        "outcome": "ok" if result.get("status") == "ok" else result["error"],
                        "result": result,
                    }
                )
                previous_finish = finished
                (output / "cpu-run.partial.json").write_text(
                    json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        finally:
            sampling = False
            await memory_task
            runtime.close()
            run["rss_peak_bytes"], run["close_state"] = peaks, runtime.state
            (output / "cpu-run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        assert questions_path.read_bytes() == payload, "Gold changed; retain original frozen run"
    if manual_path:
        manual = checked_object(read_object(Path(manual_path)), {"schema_version", "run_id", "reviews"})
        assert (
            type(manual["schema_version"]) is int
            and manual["schema_version"] == 1
            and manual["run_id"] == run["run_id"]
        )
        reviews = manual["reviews"]
    else:
        reviews = [
            {
                "run_id": run["run_id"],
                "question_id": question["id"],
                "decision": "pending",
                "annotation_status": "pending",
                "checks": [],
                "reason": "待人工核對實際回傳原文",
            }
            for question in gold["questions"]
        ]
        (output / "cpu-reviews.pending.json").write_text(
            json.dumps(
                {"schema_version": 1, "run_id": run["run_id"], "reviews": reviews}, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
    report = summarize_cpu_run(gold, run, reviews)
    report.update(
        run_id=run["run_id"],
        dataset_sha256=run["dataset_sha256"],
        observations_sha256=hashlib.sha256(
            json.dumps(run["observations"], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (output / f"cpu-summary-{stamp}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"CPU observations={report['denominator']}; supported={report['supported']}; pending={report['pending']}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,reason,extra,expected",
    [
        ("document_unavailable", "legacy_package", {}, "legacy_package"),
        ("document_unavailable", "absent", {}, None),
        ("document_unavailable", "legacy_package", {"type": "ready"}, None),
        ("document_unavailable", None, {}, None),
        ("document_unavailable", "unknown", {}, None),
        ("document_not_ready", "legacy_package", {}, None),
        ("document_unavailable", "legacy_package", {"path": "private-sentinel"}, None),
    ],
)
async def test_private_initialization_reason_is_strict_and_cleared_on_close(
    tmp_path, monkeypatch, error, reason, extra, expected, caplog
) -> None:
    """Only a valid private legacy failure survives for the next explicit query."""
    envelope = {"version": 1, "type": "failure", "error": error, **extra}
    if reason != "absent":
        envelope["reason"] = reason
    worker = tmp_path / "failure.py"
    worker.write_text(
        "import sys; sys.stdout.write(" + repr(json.dumps(envelope) + "\n") + "); sys.stdout.flush()", encoding="utf-8"
    )
    original = subprocess.Popen
    monkeypatch.setattr(
        document_retrieval.subprocess,
        "Popen",
        lambda command, **kwargs: original([sys.executable, str(worker)], **kwargs),
    )
    runtime = document_retrieval.DocumentRuntime(tmp_path, tmp_path, tmp_path)
    try:
        assert runtime.unavailable_reason is None
        assert await runtime.query("first") == {"error": "document_not_ready"}
        deadline = time.monotonic() + 5
        while runtime.state == "loading" and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert runtime.state == "failed"
        assert runtime.unavailable_reason == expected
        result = await runtime.query("next")
        assert set(result) == {"error"}
        if expected:
            assert result == {"error": "document_unavailable"}
        assert await runtime.query("!!!") == {"error": "document_invalid_query"}
        assert "private-sentinel" not in caplog.text
    finally:
        runtime.close()
    assert runtime.unavailable_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize("handler_type", [HuggingFaceRealtimeHandler, GeminiRealtimeHandler])
@pytest.mark.parametrize("retirement", [None, "epoch", "generation", "disabled", "cancelled"])
async def test_legacy_notice_is_local_once_and_owned_by_the_original_call(
    monkeypatch, handler_type, retirement
) -> None:
    """Both adapters share one local notice and retire it before consuming stale output."""
    runtime = document_retrieval.DocumentRuntime(None, None)
    monkeypatch.setattr(runtime, "_unavailable_reason", "legacy_package", raising=False)
    tools = {"search_document": SearchDocument()}
    monkeypatch.setattr("reachy_mini_conversation_app.tools.core_tools.get_tools", lambda: tools)
    handler = handler_type(ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime))
    invocation = ToolInvocation("search_document", "running")
    handler.session_state.invocations["doc"] = invocation
    note = ToolNotification(
        id="doc",
        tool_name="search_document",
        is_idle_tool_call=False,
        status=ToolState.FAILED,
        error="document_unavailable",
    )
    assert handler._document_result(note) == {"error": "document_unavailable"}
    assert invocation.legacy_notice_sent
    assert not invocation.timeout_notice_sent
    assert handler._document_result(note) is None
    assert handler.output_queue.qsize() == 1
    if retirement == "epoch":
        handler.playback_epoch += 1
    elif retirement == "generation":
        handler.session_state.begin_connection()
    elif retirement == "disabled":
        tools.clear()
    elif retirement == "cancelled":
        invocation.status = "cancelled"
    displayed = await handler.emit()
    if retirement:
        assert displayed is None
    else:
        assert "此文件索引為舊版" in str(displayed.args)
        handler.session_state.invocations["next"] = ToolInvocation("search_document", "running")
        handler._document_result(
            ToolNotification(
                id="next",
                tool_name="search_document",
                is_idle_tool_call=False,
                status=ToolState.FAILED,
                error="document_unavailable",
            )
        )
        assert handler.output_queue.qsize() == 1
    runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason,payload",
    [
        (None, {"error": "document_unavailable"}),
        ("legacy_package", {"error": "document_unavailable", "path": "private-sentinel"}),
        ("legacy_package", {"error": "document_invalid_query"}),
    ],
)
async def test_generic_or_synthesized_unavailable_never_reports_legacy(monkeypatch, reason, payload) -> None:
    """Malformed tool results cannot borrow a cached package cause to emit a false notice."""
    runtime = document_retrieval.DocumentRuntime(None, None)
    monkeypatch.setattr(runtime, "_unavailable_reason", reason, raising=False)
    monkeypatch.setattr(
        "reachy_mini_conversation_app.tools.core_tools.get_tools", lambda: {"search_document": SearchDocument()}
    )
    handler = HuggingFaceRealtimeHandler(ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime))
    handler.session_state.invocations["doc"] = ToolInvocation("search_document", "running")
    handler._document_result(
        ToolNotification(
            id="doc", tool_name="search_document", is_idle_tool_call=False, status=ToolState.COMPLETED, result=payload
        )
    )
    assert handler.output_queue.empty()
    runtime.close()


@pytest.mark.asyncio
async def test_manual_cpu_review_updates_reports_without_rerunning_queries(monkeypatch) -> None:
    """A review-only run keeps the frozen observations and never touches a model or tool."""
    root = (
        Path(__file__).resolve().parents[1] / "cache" / "004-single-document-rag" / "review-tests" / uuid.uuid4().hex
    )
    root.mkdir(parents=True)
    gold = {
        "schema_version": 1,
        "dataset_id": "unit",
        "dataset_version": "v1",
        "document": {"id": "manual", "version": "v1", "source_sha256": "a" * 64},
        "questions": [
            {
                "id": f"q{i}",
                "query": "無依據問題",
                "answerability": "unanswerable",
                "required_information": [],
                "evidence": [],
            }
            for i in range(50)
        ],
    }
    payload = json.dumps(gold, ensure_ascii=False).encode()
    run = {
        "run_id": "unit-run",
        "document": gold["document"],
        "dataset_utf8": payload.decode(),
        "dataset_sha256": hashlib.sha256(payload).hexdigest(),
        "observations": [
            {
                "question_id": f"q{i}",
                "accepted_at_monotonic": i * 10.0,
                "finished_at_monotonic": i * 10.0 + 4.0,
                "elapsed_seconds": 4.0,
                "outcome": "document_no_evidence",
                "result": {"error": "document_no_evidence"},
            }
            for i in range(50)
        ],
    }
    raw = json.dumps(run, ensure_ascii=False).encode()
    path = root / "cpu-run.json"
    path.write_bytes(raw)
    monkeypatch.setenv("RAG_ACCEPTANCE_RUN", str(path))
    monkeypatch.delenv("RAG_ACCEPTANCE_REVIEWS", raising=False)

    async def reject_query(*args, **kwargs):
        raise AssertionError("Review-only mode must not repeat CPU work")

    monkeypatch.setattr(SearchDocument, "__call__", reject_query)
    await test_external_cpu_fifty_question_benchmark(root)
    manual = read_object(root / "cpu-reviews.pending.json")
    for entry in manual["reviews"]:
        entry.update(
            decision="not_applicable",
            annotation_status="valid",
            reviewer="unit-reviewer",
            reviewed_at_utc="2026-11-10T01:00:00Z",
            review_seconds=30.0,
            reason="工具無依據；未回傳段落",
        )
    manual_path = root / "manual.json"
    manual_path.write_text(json.dumps(manual, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("RAG_ACCEPTANCE_REVIEWS", str(manual_path))
    await test_external_cpu_fifty_question_benchmark(root)
    assert path.read_bytes() == raw
    reports = [read_object(path) for path in root.glob("cpu-summary-*.json")]
    assert len(reports) == 2
    assert sorted(report["pending"] for report in reports) == [0, 50]
    assert all(report["supported"] == 0 and report["expected_refusal"] == 50 for report in reports)


@pytest.mark.asyncio
async def test_cpu_sampler_includes_the_worker_below_a_windows_launcher(tmp_path, monkeypatch) -> None:
    """Worker RSS must include the real interpreter beneath a small launcher process."""
    run_id = "rss-unit-" + uuid.uuid4().hex
    source = "原文"
    identity = {"id": "rss-manual", "version": "v1", "source_sha256": hashlib.sha256(source.encode()).hexdigest()}
    package = tmp_path / "package"
    (package / "retrieval").mkdir(parents=True)
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "chunk_count": 1,
                "chunking": {"embedding_input_max_tokens": 512},
                "document": identity,
                "index_version": "idx",
            }
        ),
        encoding="utf-8",
    )
    (package / "retrieval/chunks.jsonl").write_text(
        json.dumps({"start": 0, "end": len(source), "text": source}) + "\n", encoding="utf-8"
    )
    models = [tmp_path / "embedding", tmp_path / "reranker"]
    for directory in models:
        directory.mkdir()
        (directory / "model-receipt.json").write_text(
            json.dumps({"revision": "a" * 40, "runtime": {"unit": "fake"}}), encoding="utf-8"
        )
    dataset = {
        "schema_version": 1,
        "dataset_id": "rss-unit",
        "dataset_version": "v1",
        "document": identity,
        "questions": [
            {
                "id": f"q{i}",
                "query": "未記載的資訊",
                "answerability": "unanswerable",
                "required_information": [],
                "evidence": [],
            }
            for i in range(50)
        ],
    }
    questions = tmp_path / "questions.json"
    questions.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
    for key, value in {
        "RUN_DOCUMENT_CPU_ACCEPTANCE": "1",
        "RAG_ACCEPTANCE_GOLD_REVIEWED": "1",
        "RAG_ACCEPTANCE_PACKAGE": str(package),
        "RAG_ACCEPTANCE_MODEL": str(models[0]),
        "RAG_ACCEPTANCE_RERANKER": str(models[1]),
        "RAG_ACCEPTANCE_QUESTIONS": str(questions),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("RAG_ACCEPTANCE_RUN", raising=False)
    monkeypatch.delenv("RAG_ACCEPTANCE_REVIEWS", raising=False)
    monkeypatch.setattr(uuid, "uuid4", lambda: SimpleNamespace(hex=run_id))

    class ReadyRuntime:
        state = "dormant"

        def __init__(self, *paths):
            self.state = "dormant"

        async def query(self, question):
            if self.state == "dormant":
                self.state = "ready"
                return {"error": "document_not_ready"}
            await asyncio.sleep(0.002)
            return {"error": "document_no_evidence"}

        def close(self):
            self.state = "closed"

    launcher = SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=5 * 1024 * 1024))
    interpreter = SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=4 * 1024 * 1024 * 1024))

    class MemoryParent:
        def memory_info(self):
            return SimpleNamespace(rss=128 * 1024 * 1024)

        def children(self, recursive=False):
            return [launcher, interpreter] if recursive else [launcher]

    monkeypatch.setattr(document_retrieval, "DocumentRuntime", ReadyRuntime)
    monkeypatch.setattr(psutil, "Process", MemoryParent)
    await test_external_cpu_fifty_question_benchmark(tmp_path)
    output = Path(__file__).resolve().parents[1] / "cache/004-single-document-rag/cpu" / run_id
    run = read_object(output / "cpu-run.json")
    assert run["rss_peak_bytes"]["worker"] == 4 * 1024 * 1024 * 1024
    assert len(run["observations"]) == 50
    assert run["close_state"] == "closed"
