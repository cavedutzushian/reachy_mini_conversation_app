import os
import re
import sys
import json
import time
import uuid
import queue
import shutil
import asyncio
import logging
import tempfile
import threading
import subprocess
from typing import Literal, TypedDict
from pathlib import Path, PurePosixPath, PureWindowsPath
from concurrent.futures import Future

from reachy_mini_conversation_app.document_assets import PreparationError, parse_object


DOCUMENT_ERRORS = frozenset(
    {
        "document_not_ready",
        "document_busy",
        "document_unavailable",
        "document_invalid_query",
        "document_no_evidence",
        "document_timeout",
    }
)
QUERY_TIMEOUT_S = 10.0
INITIALIZATION_TIMEOUT_S = 120.0
PROTOCOL_LIMIT_BYTES = 64 * 1024
logger = logging.getLogger(__name__)


class DocumentIdentity(TypedDict):
    """Identify the sole document version represented by a package."""

    id: str
    title: str
    version: str


class CitationPassage(TypedDict):
    """Carry one unchanged passage and its real source locator."""

    chunk_id: str
    locator: str
    text: str
    truncated: bool


class DocumentSuccess(TypedDict):
    """Bound the evidence returned to a conversation provider."""

    status: str
    document: DocumentIdentity
    index_version: str
    passages: list[CitationPassage]


def valid_identifier(value: object) -> bool:
    """Accept bounded identifiers without paths or control characters."""
    return isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}", value) is not None


def validate_document_query(query: object) -> str | None:
    """Validate the original input length before trimming its whitespace."""
    if not isinstance(query, str) or not 1 <= len(query) <= 500:
        return None
    stripped = query.strip()
    return stripped if any(character.isalnum() for character in stripped) else None


def valid_display_text(value: object, limit: int) -> bool:
    """Accept bounded source labels without control characters or absolute paths."""
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= limit
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
        and "://" not in value
        and not PurePosixPath(value).is_absolute()
        and not PureWindowsPath(value).is_absolute()
    )


def validate_document_result(payload: object) -> dict[str, object]:
    """Reject unbounded or malformed worker output before exposing it to a provider."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid document result")
    if set(payload) == {"error"}:
        error = payload["error"]
        if isinstance(error, str) and error in DOCUMENT_ERRORS:
            return {"error": error}
        raise ValueError("Invalid document error")
    if set(payload) != {"status", "document", "index_version", "passages"} or payload["status"] != "ok":
        raise ValueError("Invalid document result")
    identity = payload["document"]
    if not isinstance(identity, dict) or set(identity) != {"id", "title", "version"}:
        raise ValueError("Invalid document identity")
    if not valid_identifier(identity["id"]) or not valid_identifier(identity["version"]):
        raise ValueError("Invalid document identity")
    title = identity["title"]
    if not isinstance(title, str) or not valid_display_text(title, 160):
        raise ValueError("Invalid document title")
    if not valid_identifier(payload["index_version"]):
        raise ValueError("Invalid index version")
    passages = payload["passages"]
    if not isinstance(passages, list) or not 1 <= len(passages) <= 3:
        raise ValueError("Invalid passage count")
    total = 0
    bounded_passages: list[CitationPassage] = []
    chunk_ids: set[str] = set()
    for passage in passages:
        if not isinstance(passage, dict) or set(passage) != {"chunk_id", "locator", "text", "truncated"}:
            raise ValueError("Invalid passage")
        if not valid_identifier(passage["chunk_id"]) or not isinstance(passage["truncated"], bool):
            raise ValueError("Invalid passage")
        locator, text = passage["locator"], passage["text"]
        if not isinstance(locator, str) or not valid_display_text(locator, 256):
            raise ValueError("Invalid locator")
        if not isinstance(text, str) or not text:
            raise ValueError("Invalid passage text")
        total += len(text)
        chunk_id = str(passage["chunk_id"])
        if chunk_id in chunk_ids:
            raise ValueError("Duplicate passage")
        chunk_ids.add(chunk_id)
        bounded_passages.append(
            CitationPassage(chunk_id=chunk_id, locator=locator, text=text, truncated=bool(passage["truncated"]))
        )
    if total > 2000:
        raise ValueError("Document text exceeds limit")
    result = DocumentSuccess(
        status="ok",
        document=DocumentIdentity(id=str(identity["id"]), title=title, version=str(identity["version"])),
        index_version=str(payload["index_version"]),
        passages=bounded_passages,
    )
    return dict(result)


class DocumentRuntime:
    """Own one local retrieval process without queuing additional CPU requests."""

    def __init__(self, index_path: Path | None, model_path: Path | None, reranker_path: Path | None = None) -> None:
        """Freeze local paths without opening files or importing retrieval dependencies."""
        self._index_path = index_path
        self._model_path = model_path
        self._reranker_path = reranker_path
        self._state = (
            "dormant"
            if index_path is not None and model_path is not None and reranker_path is not None
            else "unconfigured"
        )
        self._error = "document_not_ready"
        self._unavailable_reason: Literal["legacy_package"] | None = None
        self._lock = threading.RLock()
        self._closing = threading.Event()
        self._started = threading.Event()
        self._requests: queue.Queue[tuple[str, str] | None] = queue.Queue(maxsize=1)
        self._pending: Future[dict[str, object]] | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._startup_timer: threading.Timer | None = None
        self._work_directory: Path | None = None
        self._identity: object = None
        self._index_version: object = None

    @property
    def state(self) -> str:
        """Return readiness independently of conversation ownership."""
        with self._lock:
            return self._state

    @property
    def unavailable_reason(self) -> Literal["legacy_package"] | None:
        """Expose only the verified local cause without adding provider result fields."""
        with self._lock:
            return self._unavailable_reason

    async def query(self, query: object) -> dict[str, object]:
        """Return evidence or a fixed error within the local request deadline."""
        normalized = validate_document_query(query)
        if normalized is None:
            return {"error": "document_invalid_query"}
        with self._lock:
            if self._closing.is_set():
                return {"error": "document_not_ready"}
            if self._state == "dormant":
                self._state = "loading"
                self._unavailable_reason = None
                self._startup_timer = threading.Timer(INITIALIZATION_TIMEOUT_S, self._expire_initialization)
                self._startup_timer.daemon = True
                self._startup_timer.start()
                self._thread = threading.Thread(target=self._run_worker, name="document-retrieval", daemon=True)
                self._thread.start()
                return {"error": "document_not_ready"}
            if self._state == "busy":
                return {"error": "document_busy"}
            if self._state != "ready":
                return {"error": self._error}
            pending: Future[dict[str, object]] = Future()
            self._pending = pending
            self._state = "busy"
            self._requests.put_nowait((uuid.uuid4().hex, normalized))
        try:
            return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(pending)), timeout=QUERY_TIMEOUT_S)
        except TimeoutError:
            logger.warning("Document retrieval: document_timeout")
            return {"error": "document_timeout"}

    def _expire_initialization(self) -> None:
        with self._lock:
            if self._state == "loading":
                self._state = "failed"
                logger.warning("Document retrieval: document_not_ready")

    def _read_message(self, process: subprocess.Popen[bytes]) -> dict[str, object]:
        if process.stdout is None:
            raise ValueError("Worker pipe missing")
        line = process.stdout.readline(PROTOCOL_LIMIT_BYTES + 1)
        if not line or len(line) > PROTOCOL_LIMIT_BYTES or not line.endswith(b"\n"):
            raise ValueError("Invalid worker message")
        try:
            envelope: object = parse_object(line)
        except PreparationError:
            raise ValueError("Invalid worker JSON") from None
        if not isinstance(envelope, dict) or type(envelope.get("version")) is not int or envelope.get("version") != 1:
            raise ValueError("Invalid worker protocol")
        if "reason" in envelope and not (
            envelope.get("type") == "failure"
            and envelope.get("error") == "document_unavailable"
            and envelope["reason"] == "legacy_package"
        ):
            raise ValueError("Invalid private failure reason")
        return dict(envelope)

    def _run_worker(self) -> None:
        try:
            if self._closing.is_set():
                return
            environment = dict(os.environ)
            environment.update(
                {
                    "REACHY_MINI_SKIP_DOTENV": "1",
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "ANONYMIZED_TELEMETRY": "False",
                    "REACHY_MINI_DOCUMENT_INDEX_PATH": str(self._index_path),
                    "REACHY_MINI_DOCUMENT_MODEL_PATH": str(self._model_path),
                    "REACHY_MINI_DOCUMENT_RERANKER_PATH": str(self._reranker_path),
                }
            )
            self._work_directory = Path(tempfile.mkdtemp(prefix="reachy-document-"))
            environment["REACHY_MINI_DOCUMENT_WORK_PATH"] = str(self._work_directory)
            if self._closing.is_set():
                return
            process = subprocess.Popen(
                [sys.executable, "-u", "-m", "reachy_mini_conversation_app.document_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._process = process
            self._started.set()
            ready = self._read_message(process)
            if ready.get("type") == "failure":
                error = ready.get("error")
                if (
                    set(ready) - {"version", "type", "error", "reason"}
                    or error not in ("document_not_ready", "document_unavailable")
                    or "reason" in ready
                    and not (error == "document_unavailable" and ready["reason"] == "legacy_package")
                ):
                    raise ValueError("Invalid initialization failure")
                with self._lock:
                    if self._state == "loading" and not self._closing.is_set():
                        self._error = str(error)
                        self._unavailable_reason = "legacy_package" if "reason" in ready else None
                raise ValueError("Worker initialization failed")
            if ready.get("type") != "ready":
                raise ValueError("Worker did not initialize")
            self._identity = ready.get("document")
            self._index_version = ready.get("index_version")
            with self._lock:
                if self._state != "loading" or self._closing.is_set():
                    return
                self._state = "ready"
            if self._startup_timer is not None:
                self._startup_timer.cancel()
            while not self._closing.is_set():
                request = self._requests.get()
                if request is None or self._closing.is_set():
                    break
                request_id, question = request
                if process.stdin is None:
                    raise ValueError("Worker input missing")
                process.stdin.write(
                    json.dumps({"version": 1, "type": "query", "request_id": request_id, "query": question}).encode()
                    + b"\n"
                )
                process.stdin.flush()
                envelope = self._read_message(process)
                if envelope.get("type") != "result" or envelope.get("request_id") != request_id:
                    raise ValueError("Unexpected worker response")
                result = validate_document_result(envelope.get("payload"))
                if "error" not in result and (
                    result["document"] != self._identity or result["index_version"] != self._index_version
                ):
                    raise ValueError("Worker source changed")
                with self._lock:
                    if self._pending is not None and not self._pending.done():
                        self._pending.set_result(result)
                    self._pending = None
                    if not self._closing.is_set():
                        self._state = "ready"
        except (OSError, ValueError, TypeError) as error:
            logger.warning("Document worker failed: %s", type(error).__name__)
            with self._lock:
                if not self._closing.is_set():
                    if self._state == "busy":
                        self._error = "document_unavailable"
                    self._state = "failed"
                if self._pending is not None and not self._pending.done():
                    self._pending.set_result({"error": "document_unavailable"})
                self._pending = None
        finally:
            self._started.set()
            if self._process is not None and self._process.stdin is not None:
                try:
                    self._process.stdin.close()
                except OSError as error:
                    logger.warning("Document pipe cleanup failed: %s", type(error).__name__)
            if self._process is not None and self._process.stdout is not None:
                self._process.stdout.close()

    def close(self) -> None:
        """Retire all work and bound worker shutdown to five, two and two seconds."""
        if self._closing.is_set():
            return
        started_at = time.monotonic()
        self._closing.set()
        with self._lock:
            self._state = "closing"
            self._unavailable_reason = None
            if self._startup_timer is not None:
                self._startup_timer.cancel()
            if self._pending is not None and not self._pending.done():
                self._pending.set_result({"error": "document_not_ready"})
            if self._thread is None:
                self._started.set()
            if not self._requests.full():
                self._requests.put_nowait(None)
        self._started.wait(max(0, started_at + 5 - time.monotonic()))
        process = self._process
        confirmed = self._started.is_set() and process is None
        if process is not None:
            for stage_end, action in ((5, None), (7, process.terminate), (9, process.kill)):
                if process.poll() is not None:
                    confirmed = True
                    break
                try:
                    if action is not None:
                        action()
                    process.wait(timeout=max(0, started_at + stage_end - time.monotonic()))
                    confirmed = True
                    break
                except subprocess.TimeoutExpired:
                    continue
                except OSError as error:
                    logger.warning("Document worker shutdown failed: %s", type(error).__name__)
                    break
        if confirmed:
            if self._work_directory is not None:
                try:
                    shutil.rmtree(self._work_directory)
                except OSError as error:
                    logger.warning("Document cleanup failed: %s", type(error).__name__)
            with self._lock:
                self._state = "closed"
        else:
            logger.warning("Document retrieval: cleanup_incomplete")
