import os
import re
import sys
import json
import math
import uuid
import shutil
import hashlib
import logging
import argparse
import subprocess
from typing import NoReturn
from pathlib import Path
from dataclasses import dataclass
from importlib.util import find_spec
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files

from jsonschema import Draft202012Validator


logger = logging.getLogger(__name__)
MODEL_ID = "BAAI/bge-m3"
MODEL_REVISION = "50f9396f75618b3389c1fd1068a1ff58dc7b5b26"
RERANKER_ID = "BAAI/bge-reranker-base"
RERANKER_REVISION = "2cfc18c9415c912f9d8155881c133215df768a70"
REFERENCE_PASSAGE = "這是一份提供文件查詢的示範說明。"
REFERENCE_QUERY = "這份文件主要說明什麼？"
PAYLOAD_FILES = (
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "1_Pooling/config.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "model.safetensors",
)

RERANKER_PAYLOAD_FILES = (
    "config.json",
    "model.safetensors",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)


class PreparationArgumentParser(argparse.ArgumentParser):
    """Keep preparation argument failures localized without echoing untrusted argument values."""

    def error(self, message: str) -> NoReturn:
        """Explain rejected arguments using a fixed Traditional Chinese diagnostic."""
        self.print_usage(sys.stderr)
        self.exit(2, "???????? --help ????????????\n")


@dataclass(frozen=True)
class PreparationResult:
    """Describe publication independently from whether material is verified ready."""

    status: str
    published: bool
    ready: bool | None
    code: str
    exit_code: int

    def describe(self) -> str:
        """Explain readiness separately from the publication boundary for CLI callers."""
        labels = {
            "completed": "完成",
            "already_ready": "已就緒",
            "failed": "未完成",
            "busy": "目的地忙碌",
            "recovery_required": "需要人工處理",
        }
        readiness = "已驗證" if self.ready is True else "未就緒" if self.ready is False else "未判定"
        publication = "已發布" if self.published else "本次未發布"
        return f"結果：{labels[self.status]}；{publication}；素材：{readiness}；代碼：{self.code}；結束碼：{self.exit_code}"


class PreparationError(RuntimeError):
    """Carry a content-free preparation outcome and its CLI exit code."""

    def __init__(self, code: str, exit_code: int) -> None:
        """Record the fixed failure category without retaining private exception text."""
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


def load_preparation_scheme() -> dict[str, object]:
    """Read the bundled complete selection without depending on experiment cache paths."""
    value = json.loads(files("reachy_mini_conversation_app").joinpath("document_scheme.json").read_text("utf-8"))
    if (
        not isinstance(value, dict)
        or set(value) != {"strategy", "chunking", "bm25", "retrieval", "reranking", "embedding", "provenance"}
        or any(not isinstance(item, dict) for item in value.values())
    ):
        raise PreparationError("invalid_scheme", 2)
    json.dumps(value, allow_nan=False)
    return dict(value)


def read_object(path: Path) -> dict[str, object]:
    """Read bounded, finite UTF-8 JSON without duplicate keys or a BOM."""
    with path.open("rb") as stream:
        payload = stream.read(16 * 1024 * 1024 + 1)
    return parse_object(payload)


def parse_object(payload: bytes) -> dict[str, object]:
    """Parse a bounded byte snapshot without rereading a mutable source file."""
    if len(payload) > 16 * 1024 * 1024 or payload.startswith(b"\xef\xbb\xbf"):
        raise PreparationError("validation_failed", 6)
    result = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_pairs)
    json.dumps(result, allow_nan=False)
    if not isinstance(result, dict):
        raise PreparationError("validation_failed", 6)
    return dict(result)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PreparationError("validation_failed", 6)
        result[key] = value
    return result


def source_line_numbers(text: str) -> list[int]:
    """Count only original CRLF, CR and LF endings without rewriting source characters."""
    line_numbers: list[int] = []
    line = 1
    for position, character in enumerate(text):
        line_numbers.append(line)
        if character == "\n" or character == "\r" and text[position + 1 : position + 2] != "\n":
            line += 1
    return line_numbers


def lexical_terms(text: str) -> list[str]:
    """Tokenize fixed ASCII words and original CJK adjacent pairs and triples."""
    terms = re.findall(r"[a-z0-9]+", text.casefold())
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        terms.extend(run[start : start + width] for width in (2, 3) for start in range(len(run) - width + 1))
    return terms


def write_object(path: Path, value: dict[str, object]) -> None:
    """Write an owned candidate record as finite UTF-8 JSON."""
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf-8")
    if len(payload) > 16 * 1024 * 1024:
        raise PreparationError("validation_failed", 6)
    pending = path.with_name(f".{path.name}.{uuid.uuid4().hex}.pending")
    with pending.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


def file_inventory(directory: Path) -> list[dict[str, object]]:
    """Hash a closed regular-file tree without accepting links or Windows aliases."""
    inventory: list[dict[str, object]] = []
    aliases: set[str] = set()
    if not directory.is_dir() or directory.is_symlink() or directory.is_junction():
        raise PreparationError("validation_failed", 6)
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise PreparationError("unsafe_path", 4)
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        alias = "/".join(part.rstrip(" .").casefold() for part in relative.split("/"))
        if alias in aliases or any(":" in part or part.rstrip(" .") != part for part in relative.split("/")):
            raise PreparationError("unsafe_path", 4)
        aliases.add(alias)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        inventory.append({"path": relative, "sha256": digest})
    return inventory


def source_identity(path: Path) -> list[int]:
    """Identify source replacement or modification without treating a read as an atime mutation."""
    status = path.stat()
    return [status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns]


def checkout_root() -> Path | None:
    """Locate the source checkout independently of the invocation directory."""
    module_path = Path(__file__).resolve()
    candidate = module_path.parents[2]
    if (
        candidate / "pyproject.toml"
    ).is_file() and module_path.parent == candidate / "src/reachy_mini_conversation_app":
        return candidate
    return None


def validate_paths(destination: Path, inputs: list[Path]) -> None:
    """Reject linked, protected, overlapping or unignored repository output paths."""
    paths = [destination, *inputs]
    for path in paths:
        for ancestor in [path, *path.parents]:
            if ancestor.is_symlink() or ancestor.is_junction():
                raise PreparationError("unsafe_path", 4)
            if ancestor.name and (ancestor.name.rstrip(" .") != ancestor.name or ":" in ancestor.name):
                raise PreparationError("unsafe_path", 4)
    resolved = destination.resolve()
    if destination.exists() and not destination.is_dir():
        raise PreparationError("unsafe_path", 4)
    if resolved == Path(resolved.anchor):
        raise PreparationError("unsafe_path", 4)
    for source in inputs:
        source = source.resolve()
        if source.is_relative_to(resolved) or resolved.is_relative_to(source):
            raise PreparationError("unsafe_path", 4)
    repository = checkout_root()
    if repository is not None and resolved.is_relative_to(repository):
        for name in ("src", "tests", ".git", ".agents", ".specify", "profiles", "docs", ".venv"):
            protected = repository / name
            if resolved.is_relative_to(protected) or protected.is_relative_to(resolved):
                raise PreparationError("unsafe_path", 4)
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", "--no-index", str(resolved / "probe")],
            cwd=repository,
            capture_output=True,
            check=False,
        )
        if ignored.returncode != 0:
            raise PreparationError("unsafe_path", 4)


def validate_receipt(directory: Path) -> dict[str, object]:
    """Verify the pinned receipt and every payload byte without loading inference."""
    receipt = read_object(directory / "model-receipt.json")
    schema = json.loads(
        files("reachy_mini_conversation_app").joinpath("document_model_receipt.schema.json").read_text("utf-8")
    )
    if list(Draft202012Validator(schema).iter_errors(receipt)):
        raise PreparationError("model_incompatible", 3)
    if receipt["revision"] != receipt["resolved_revision"]:
        raise PreparationError("model_incompatible", 3)
    runtime = receipt["runtime"]
    if not isinstance(runtime, dict):
        raise PreparationError("model_incompatible", 3)
    try:
        for package, key in (
            ("sentence-transformers", "sentence_transformers_version"),
            ("torch", "torch_version"),
            ("transformers", "transformers_version"),
        ):
            if version(package) != runtime[key]:
                raise PreparationError("model_incompatible", 3)
    except PackageNotFoundError:
        raise PreparationError("model_not_ready", 3) from None
    entries = receipt["files"]
    if not isinstance(entries, list):
        raise PreparationError("model_incompatible", 3)
    payload_files = PAYLOAD_FILES if receipt["role"] == "embedding" else RERANKER_PAYLOAD_FILES
    expected: dict[str, object] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise PreparationError("model_incompatible", 3)
        name = entry["path"]
        if name in expected or (directory / name).stat().st_size != entry["size_bytes"]:
            raise PreparationError("model_incompatible", 3)
        expected[name] = entry["sha256"]
    actual = {entry["path"]: entry["sha256"] for entry in file_inventory(directory)}
    if set(actual) != {*payload_files, "model-receipt.json"} or set(expected) != set(payload_files):
        raise PreparationError("model_incompatible", 3)
    if any(actual[name] != digest for name, digest in expected.items()):
        raise PreparationError("model_incompatible", 3)
    verification = receipt["verification"]
    if not isinstance(verification, dict):
        raise PreparationError("model_incompatible", 3)
    if receipt["role"] == "reranker":
        score = verification.get("logit")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise PreparationError("model_incompatible", 3)
        return receipt
    if not isinstance(verification.get("embedding"), list):
        raise PreparationError("model_incompatible", 3)
    vector = verification["embedding"]
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector
    ):
        raise PreparationError("model_incompatible", 3)
    if abs(math.sqrt(sum(value * value for value in vector)) - 1) > 1e-4:
        raise PreparationError("model_incompatible", 3)
    return receipt


class AssetOperation:
    """Own a sibling lock and stage with an explicit irreversible publication boundary."""

    published = False
    preserve = False

    def __init__(self, destination: Path, kind: str, replace: bool) -> None:
        """Allocate unique sibling names without changing the destination."""
        if kind not in ("model", "package"):
            raise PreparationError("invalid_arguments", 2)
        validate_paths(destination.absolute(), [])
        self.destination = destination.resolve()
        self.kind = kind
        self.replace = replace
        self.operation_id = uuid.uuid4().hex
        self.lock = self.destination.with_name(f".{self.destination.name}.lock")
        self.stage = self.destination.with_name(f".{self.destination.name}.stage-{self.operation_id}")
        self.backup = self.destination.with_name(f".{self.destination.name}.backup-{self.operation_id}")
        self.candidate_files: list[dict[str, object]] = []
        self.previous_files: list[dict[str, object]] = []

    def __enter__(self) -> "AssetOperation":
        """Acquire exclusive ownership before creating the private candidate."""
        validate_paths(self.destination, [])
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.lock.mkdir()
        except FileExistsError:
            raise PreparationError("destination_busy", 4) from None
        try:
            if self.destination.exists() and not self.replace:
                raise PreparationError("destination_exists", 4)
            self.record("locked")
            self.stage.mkdir()
            self.record("preparing")
        except (OSError, PreparationError):
            self._cleanup()
            raise
        return self

    def record(self, phase: str) -> None:
        """Persist only owned basenames and safe phase metadata outside the payload."""
        if phase == "validated":
            self.candidate_files = file_inventory(self.stage)
            if self.destination.exists():
                self.previous_files = file_inventory(self.destination)
        write_object(
            self.lock / "operation.json",
            {
                "operation_id": self.operation_id,
                "kind": self.kind,
                "pid": os.getpid(),
                "destination_name": self.destination.name,
                "stage_name": self.stage.name,
                "backup_name": self.backup.name,
                "phase": phase,
                "candidate_files": self.candidate_files,
                "previous_files": self.previous_files,
            },
        )

    def publish(self) -> None:
        """Publish a validated stage and preserve the new destination after this boundary."""
        if read_object(self.lock / "operation.json")["phase"] != "validated":
            raise PreparationError("validation_failed", 6)
        validate_paths(self.destination, [])
        if file_inventory(self.stage) != self.candidate_files:
            raise PreparationError("validation_failed", 6)
        if self.destination.exists():
            if not self.replace:
                raise PreparationError("destination_exists", 4)
            if file_inventory(self.destination) != self.previous_files:
                raise PreparationError("validation_failed", 6)
            self.destination.rename(self.backup)
            self.record("backed_up")
        try:
            self.stage.rename(self.destination)
        except BaseException as error:
            if not self.stage.exists() and self.destination.exists():
                self.published = True
                logger.error("Publication completed before interruption: %s", type(error).__name__)
                raise PreparationError("cleanup_incomplete", 8) from None
            if self.backup.exists():
                try:
                    self.backup.rename(self.destination)
                except OSError as error:
                    logger.error("Asset recovery failed: %s", type(error).__name__)
                    raise PreparationError("recovery_required", 8) from None
            raise
        self.published = True
        try:
            self.record("published")
        except OSError as error:
            logger.error("Publication record failed: %s", type(error).__name__)
            raise PreparationError("cleanup_incomplete", 8) from None

    def _cleanup(self) -> None:
        for path in (self.stage, self.backup, self.lock):
            if path.exists():
                if path.parent != self.destination.parent or path.is_symlink() or path.is_junction():
                    raise PreparationError("recovery_required", 8)
                shutil.rmtree(path)

    def __exit__(self, exception_type: object, exception: object, traceback: object) -> None:
        """Restore prepublication backups or clean owned postpublication remnants."""
        if self.preserve:
            return
        if self.published and isinstance(exception, PreparationError) and exception.code == "cleanup_incomplete":
            return
        if not self.published and self.backup.exists():
            if self.destination.exists():
                raise PreparationError("recovery_required", 8)
            try:
                self.backup.rename(self.destination)
            except OSError as error:
                logger.error("Asset recovery failed: %s", type(error).__name__)
                raise PreparationError("recovery_required", 8) from None
        try:
            if self.published:
                self.record("cleaning")
            self._cleanup()
        except KeyboardInterrupt:
            if self.published:
                logger.warning("Published asset cleanup was interrupted")
                raise PreparationError("cleanup_incomplete", 8) from None
            raise
        except OSError as error:
            logger.error("Asset cleanup failed: %s", type(error).__name__)
            raise PreparationError("cleanup_incomplete" if self.published else "recovery_required", 8) from None


def report_preparation_failure(code: str, exit_code: int, operation: AssetOperation | None) -> int:
    """Report a safe CLI failure without confusing completed publication with a retryable failure."""
    published = operation is not None and operation.published
    if published:
        code, exit_code = "cleanup_incomplete", 8
    status = "recovery_required" if exit_code == 8 else "busy" if code == "destination_busy" else "failed"
    print(PreparationResult(status, published, True if published else None, code, exit_code).describe())
    logger.warning("Preparation outcome: %s", code)
    if code == "model_not_ready":
        print("請依 README 確認既有 rag extra 與本機模型；不會自動安裝或下載缺少項目。")
    if operation is not None and exit_code == 8:
        if published:
            print(f"已發布，清理未完成：{operation.destination}；請核對 {operation.lock} 與目的地，不要自動重跑。")
        else:
            print(f"請先確認本次工作程序已停止，再核對 {operation.lock} 及自有暫存；不要只刪除鎖或自動重跑。")
    return exit_code


def validate_preparation_request(request: dict[str, object]) -> None:
    """Reject content-bearing or untyped private requests before launching inference."""
    allowed = {
        "operation",
        "role",
        "reranker_model",
        "scheme",
        "aliases",
        "model",
        "source",
        "stage",
        "document_id",
        "title",
        "document_version",
        "index_version",
        "revision",
        "policy",
    }
    if set(request) - allowed or request.get("operation") not in ("verify-model", "produce", "verify-package"):
        raise PreparationError("invalid_arguments", 2)
    if any(not isinstance(value, str) for value in request.values()):
        raise PreparationError("invalid_arguments", 2)
    if request["operation"] == "verify-model":
        role = request.get("role")
        if role not in ("embedding", "reranker") or not isinstance(request.get("model"), str):
            raise PreparationError("invalid_arguments", 2)
        revision = MODEL_REVISION if role == "embedding" else RERANKER_REVISION
        if request.get("revision") != revision:
            raise PreparationError("invalid_arguments", 2)


def run_preparation_worker(request: dict[str, object], operation: AssetOperation) -> dict[str, object]:
    """Run isolated inference over private JSON streams and confirm release before cleanup."""
    validate_preparation_request(request)
    if any(find_spec(package) is None for package in ("chromadb", "torch", "sentence_transformers")):
        raise PreparationError("model_not_ready", 3)
    environment = dict(os.environ)
    for name in (
        "HF_TOKEN",
        "HF_TOKEN_PATH",
        "HUGGING_FACE_HUB_TOKEN",
        "HF_ENDPOINT",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
    ):
        environment.pop(name, None)
    isolated_cache = operation.lock / "inference-cache"
    isolated_cache.mkdir(exist_ok=True)
    environment.update(
        HF_HOME=str(isolated_cache),
        HF_HUB_CACHE=str(isolated_cache / "hub"),
        TRANSFORMERS_CACHE=str(isolated_cache / "transformers"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        SKIP_DOTENV="1",
        REACHY_MINI_SKIP_DOTENV="1",
        SENTENCE_TRANSFORMERS_HOME=str(isolated_cache / "sentence-transformers"),
        ANONYMIZED_TELEMETRY="False",
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "reachy_mini_conversation_app.document_prepare_worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    try:
        stdout, _stderr = process.communicate(json.dumps(request, allow_nan=False).encode("utf-8"))
    except BaseException:
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            operation.preserve = True
            logger.error("Preparation worker termination was not confirmed: %s", type(error).__name__)
            raise PreparationError("recovery_required", 8) from None
        raise
    if len(stdout) > 65536:
        raise PreparationError("validation_failed", 6)
    try:
        result = json.loads(stdout)
    except (UnicodeError, ValueError):
        raise PreparationError("validation_failed", 6) from None
    if not isinstance(result, dict) or set(result) - {"status", "code", "count", "source_sha256", "verified"}:
        raise PreparationError("validation_failed", 6)
    if process.returncode != 0 or result.get("status") != "ok":
        logger.warning("Preparation worker failed with a fixed validation outcome")
        code = result.get("code")
        failures = {
            "invalid_arguments": 2,
            "invalid_document": 2,
            "invalid_scheme": 2,
            "invalid_aliases": 2,
            "model_not_ready": 3,
            "model_incompatible": 3,
            "snapshot_incomplete": 6,
        }
        if isinstance(code, str) and code in failures:
            raise PreparationError(code, failures[code])
        raise PreparationError("validation_failed", 6)
    return dict(result)
