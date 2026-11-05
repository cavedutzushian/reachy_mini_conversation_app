"""Behavior checks for the bounded local retrieval runtime."""

import os
import sys
import json
import time
import asyncio
import hashlib
import platform
import subprocess
from types import SimpleNamespace
from pathlib import Path
from statistics import median
from unittest.mock import MagicMock

import psutil
import pytest

from reachy_mini_conversation_app import document_retrieval
from reachy_mini_conversation_app.gemini_realtime import GeminiRealtimeHandler
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.huggingface_realtime import HuggingFaceRealtimeHandler
from reachy_mini_conversation_app.tools.search_document import SearchDocument


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
    runtime = document_retrieval.DocumentRuntime(tmp_path / "package", tmp_path / "model")
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
    runtime = document_retrieval.DocumentRuntime(tmp_path, tmp_path)
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
    runtime = document_retrieval.DocumentRuntime(original, tmp_path / "model")
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


def benchmark_passes(samples: list[tuple[float, dict[str, object]]]) -> bool:
    """Require the fixed fifty-question denominator and timely evidence, never just fast errors."""
    successes = sum(
        elapsed <= 5 and result.get("status") == "ok" and bool(result.get("passages")) for elapsed, result in samples
    )
    return len(samples) == 50 and successes >= 48 and all(elapsed <= 10 for elapsed, _result in samples)


@pytest.mark.parametrize("successes,expected", [(47, False), (48, True)])
def test_benchmark_counts_evidence_in_fixed_denominator(successes: int, expected: bool) -> None:
    """Quick no-evidence and other failures cannot inflate CPU acceptance."""
    samples = [(4.0, {"status": "ok", "passages": [{"text": "evidence"}]})] * successes
    samples += [(0.01, {"error": "document_no_evidence"})] * (50 - successes)
    assert benchmark_passes(samples) is expected
    assert not benchmark_passes(samples[:49])
    assert not benchmark_passes(samples[:49] + [(10.01, {"error": "document_timeout"})])


@pytest.mark.asyncio
async def test_external_cpu_fifty_question_benchmark(tmp_path: Path) -> None:
    """Opt in to a real CPU run through the public tool using supplied local assets only."""
    package, model, questions_path = (
        os.environ.get(name) for name in ("RAG_ACCEPTANCE_PACKAGE", "RAG_ACCEPTANCE_MODEL", "RAG_ACCEPTANCE_QUESTIONS")
    )
    if not package or not model or not questions_path:
        pytest.skip("CPU benchmark requires an external package, local model and exactly fifty fixed questions")
    questions_bytes = Path(questions_path).read_bytes()
    questions = json.loads(questions_bytes)
    assert isinstance(questions, list) and len(questions) == 50
    assert all(isinstance(question, str) and 1 <= len(question) <= 200 for question in questions)
    manifest_bytes = (Path(package) / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["chunk_count"] <= 1000
    runtime = document_retrieval.DocumentRuntime(Path(package), Path(model))
    tool = SearchDocument()
    deps = ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime)
    samples = []
    parent = psutil.Process()
    parent_peak, worker_peak = 0, 0
    sampling = True

    async def sample_memory():
        nonlocal parent_peak, worker_peak
        while sampling:
            parent_peak = max(parent_peak, parent.memory_info().rss)
            for child in parent.children():
                try:
                    worker_peak = max(worker_peak, child.memory_info().rss)
                except psutil.NoSuchProcess:
                    continue
            await asyncio.sleep(0.02)

    memory_task = asyncio.create_task(sample_memory())
    cold_start = time.monotonic()
    try:
        assert await tool(deps, query=questions[0]) == {"error": "document_not_ready"}
        while runtime.state == "loading" and time.monotonic() - cold_start <= 121:
            await asyncio.sleep(0.05)
        cold_seconds = time.monotonic() - cold_start
        assert runtime.state == "ready", "External CPU worker did not become ready"
        for question in questions:
            started = time.monotonic()
            result = await tool(deps, query=question)
            samples.append((time.monotonic() - started, result))
    finally:
        sampling = False
        await memory_task
        runtime.close()
    durations = sorted(elapsed for elapsed, _result in samples)
    report = {
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "physical_ram_bytes": psutil.virtual_memory().total,
        "parent_peak_rss": parent_peak,
        "worker_peak_rss": worker_peak,
        "cold_seconds": cold_seconds,
        "model_revision": manifest["embedding"]["revision"],
        "embedding_runtime": {
            key: manifest["embedding"][key]
            for key in ("sentence_transformers_version", "torch_version", "transformers_version")
        },
        "threads": {"intra_op": 2, "inter_op": 1},
        "questions_sha256": hashlib.sha256(questions_bytes).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "p50_seconds": median(durations),
        "p95_nearest_rank_seconds": durations[47],
        "denominator": 50,
        "samples": [
            {"seconds": elapsed, "passage_count": len(result.get("passages", [])), "error": result.get("error")}
            for elapsed, result in samples
        ],
        "passed": benchmark_passes(samples),
    }
    (tmp_path / "cpu-benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert report["passed"], "CPU acceptance failed; retain the original benchmark report"
