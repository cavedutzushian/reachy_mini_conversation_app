import os
import sys
import json
import math
import shutil
import hashlib
import platform
from pathlib import Path
from importlib.metadata import version
from importlib.resources import files

import numpy as np
import torch
import chromadb
from jsonschema import Draft202012Validator
from numpy.typing import NDArray
from chromadb.config import Settings
from chromadb.errors import ChromaError
from sentence_transformers import SentenceTransformer

from reachy_mini_conversation_app.document_retrieval import (
    CitationPassage,
    DocumentSuccess,
    DocumentIdentity,
    valid_identifier,
    valid_display_text,
    validate_document_query,
    validate_document_result,
)


class DocumentModelNotReadyError(RuntimeError):
    """Identify a missing or unusable local model without exposing its path."""


def runtime_target() -> dict[str, str]:
    """Normalize the runtime platform to the package's explicit target vocabulary."""
    return {
        "os": {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), "unsupported"),
        "architecture": {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(
            platform.machine().lower(), "unsupported"
        ),
    }


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("Expected an object")
    return dict(value)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _read_json(path: Path) -> object:
    with path.open("rb") as handle:
        payload = handle.read(16 * 1024 * 1024 + 1)
    if len(payload) > 16 * 1024 * 1024 or payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("Unsupported JSON encoding or size")
    return json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)


def _verify_files(root: Path, entries: object) -> None:
    if not root.is_dir() or root.is_symlink() or root.is_junction() or not isinstance(entries, list):
        raise ValueError("Invalid package directory")
    expected: dict[str, str] = {}
    aliases: set[str] = set()
    for entry in entries:
        record = _object(entry)
        relative, digest = record.get("path"), record.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise ValueError("Invalid inventory entry")
        if any(part in ("", ".", "..") for part in relative.split("/")) or "\\" in relative or ":" in relative:
            raise ValueError("Invalid package path")
        candidate = root / relative
        if not candidate.resolve().is_relative_to(root.resolve()) or relative in expected:
            raise ValueError("Duplicate or escaped package path")
        alias = "/".join(part.rstrip(" .").casefold() for part in relative.split("/"))
        if runtime_target()["os"] == "windows" and alias in aliases:
            raise ValueError("Colliding package paths")
        aliases.add(alias)
        expected[relative] = digest
    actual: set[str] = set()
    for directory, folders, filenames in os.walk(root, followlinks=False):
        for name in [*folders, *filenames]:
            item = Path(directory) / name
            if item.is_symlink() or item.is_junction():
                raise ValueError("Linked package files are not supported")
        for name in filenames:
            item = Path(directory) / name
            relative = item.relative_to(root).as_posix()
            actual.add(relative)
            if relative not in expected:
                raise ValueError("Unlisted package file")
            with item.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if digest != expected[relative]:
                raise ValueError("Package checksum mismatch")
    if actual != set(expected):
        raise ValueError("Missing package files")


class DocumentIndex:
    """Read one sealed document package with a matching local CPU encoder."""

    def __init__(self, package_path: Path, model_path: Path, work_path: Path) -> None:
        """Validate the whole package before permitting evidence retrieval."""
        manifest = _object(_read_json(package_path / "manifest.json"))
        schema = json.loads(
            files("reachy_mini_conversation_app").joinpath("document_manifest.schema.json").read_text(encoding="utf-8")
        )
        if list(Draft202012Validator(schema).iter_errors(manifest)):
            raise ValueError("Invalid document manifest")
        self.identity = _object(manifest["document"])
        if not valid_display_text(self.identity["title"], 160):
            raise ValueError("Invalid document title")
        self.index_version = str(manifest["index_version"])
        embedding, engine = _object(manifest["embedding"]), _object(manifest["engine"])
        targets = manifest["validated_targets"]
        if not isinstance(targets, list) or runtime_target() not in targets:
            raise ValueError("Package platform is not validated")
        if version("chromadb") != engine["version"]:
            raise ValueError("Chroma version mismatch")
        for package_name, key in (
            ("sentence-transformers", "sentence_transformers_version"),
            ("torch", "torch_version"),
            ("transformers", "transformers_version"),
        ):
            if version(package_name) != embedding[key]:
                raise ValueError("Embedding runtime version mismatch")
        _verify_files(package_path / "chroma", manifest["files"])
        inventory = manifest["files"]
        if not isinstance(inventory, list) or any(
            str(_object(entry)["path"]).endswith(("-wal", "-shm", "-journal")) for entry in inventory
        ):
            raise ValueError("Snapshot still contains a database journal")
        if not model_path.is_dir():
            raise DocumentModelNotReadyError("Local model is unavailable")
        _verify_files(model_path, embedding["files"])
        modules = _read_json(model_path / "modules.json")
        if not isinstance(modules, list) or [_object(module).get("type") for module in modules] != [
            "sentence_transformers.models.Transformer",
            "sentence_transformers.models.Pooling",
            "sentence_transformers.models.Normalize",
        ]:
            raise ValueError("Unsupported model modules")
        if [_object(module).get("path") for module in modules] != ["", "1_Pooling", "2_Normalize"]:
            raise ValueError("Unsupported model module paths")
        pooling = _object(_read_json(model_path / "1_Pooling/config.json"))
        if pooling.get("pooling_mode_cls_token") is not True or any(
            bool(value)
            for key, value in pooling.items()
            if key.startswith("pooling_mode_") and key != "pooling_mode_cls_token"
        ):
            raise ValueError("Unsupported pooling")
        encoder_config = _object(_read_json(model_path / "sentence_bert_config.json"))
        if encoder_config.get("max_seq_length") != 8192 or encoder_config.get("do_lower_case") is not False:
            raise ValueError("Unsupported tokenizer settings")
        inventory = embedding["files"]
        if not isinstance(inventory, list):
            raise ValueError("Missing model inventory")
        model_files = [str(_object(entry)["path"]) for entry in inventory]
        if not any(name.endswith(".safetensors") for name in model_files) or any(
            name.endswith((".py", ".pkl", ".pickle", ".pt", ".pth", ".bin")) for name in model_files
        ):
            raise ValueError("Only built-in modules and safe model weights are supported")
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        try:
            self.encoder = SentenceTransformer(
                str(model_path),
                device="cpu",
                local_files_only=True,
                trust_remote_code=False,
                model_kwargs={"torch_dtype": torch.float32, "use_safetensors": True},
            )
        except (OSError, RuntimeError) as error:
            raise DocumentModelNotReadyError(type(error).__name__) from None
        if self.encoder.max_seq_length != 8192:
            raise ValueError("Encoder length mismatch")
        reference = _object(manifest["reference"])
        reference_query = validate_document_query(reference["query"])
        if reference_query is None:
            raise ValueError("Invalid reference question")
        reference_vector = np.asarray(reference["embedding"], dtype=np.float32)
        if not np.isfinite(reference_vector).all() or abs(float(np.linalg.norm(reference_vector)) - 1) > 1e-4:
            raise ValueError("Invalid reference vector")
        if abs(1 - float(np.dot(self.encode(reference_query), reference_vector))) > 1e-5:
            raise ValueError("Reference embedding mismatch")
        _verify_files(model_path, embedding["files"])
        snapshot = work_path / "chroma"
        shutil.copytree(package_path / "chroma", snapshot)
        _verify_files(snapshot, manifest["files"])
        self.client = chromadb.PersistentClient(
            path=str(snapshot), settings=Settings(migrations="validate", anonymized_telemetry=False, allow_reset=False)
        )
        if len(self.client.list_collections()) != 1:
            raise ValueError("Expected exactly one document collection")
        self.collection = self.client.get_collection(name=str(engine["collection"]), embedding_function=None)
        configuration = _object(self.collection.configuration)
        if _object(configuration.get("hnsw")).get("space") != "cosine":
            raise ValueError("Collection metric mismatch")
        self.chunk_count = self.collection.count()
        if self.chunk_count != manifest["chunk_count"] or self.chunk_count <= 0:
            raise ValueError("Collection count mismatch")
        max_distance = _object(manifest["retrieval"])["max_distance"]
        if not isinstance(max_distance, (int, float)) or isinstance(max_distance, bool):
            raise ValueError("Invalid distance limit")
        self.max_distance = float(max_distance)
        if not math.isfinite(self.max_distance):
            raise ValueError("Invalid distance limit")
        seen: set[str] = set()
        for offset in range(0, self.chunk_count, 256):
            batch = self.collection.get(limit=256, offset=offset, include=["documents", "metadatas", "embeddings"])
            identifiers = batch["ids"]
            documents, metadatas, vectors = batch["documents"], batch["metadatas"], batch["embeddings"]
            if (
                documents is None
                or metadatas is None
                or vectors is None
                or not (len(identifiers) == len(documents) == len(metadatas) == len(vectors))
            ):
                raise ValueError("Missing document fields")
            for identifier, text, metadata, vector in zip(identifiers, documents, metadatas, vectors, strict=True):
                self._passage(identifier, text, metadata)
                if identifier in seen:
                    raise ValueError("Duplicate document passage")
                seen.add(identifier)
                values = np.asarray(vector, dtype=np.float32)
                if (
                    values.shape != (1024,)
                    or not np.isfinite(values).all()
                    or abs(float(np.linalg.norm(values)) - 1) > 1e-4
                ):
                    raise ValueError("Invalid document vector")
        if len(seen) != self.chunk_count:
            raise ValueError("Incomplete document collection")

    def encode(self, question: str) -> NDArray[np.float32]:
        """Encode a question with the same validated normalized dense pipeline."""
        values = np.asarray(
            self.encoder.encode(
                [question], prompt="", normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
            ),
            dtype=np.float32,
        )
        if (
            values.shape != (1, 1024)
            or not np.isfinite(values).all()
            or abs(float(np.linalg.norm(values[0])) - 1) > 1e-4
        ):
            raise ValueError("Invalid query vector")
        return np.asarray(values[0], dtype=np.float32)

    def _passage(self, identifier: object, text: object, metadata: object) -> CitationPassage:
        source = _object(metadata)
        locator = source.get("locator")
        if (
            source.get("document_id") != self.identity["id"]
            or source.get("document_version") != self.identity["version"]
        ):
            raise ValueError("Mixed document sources")
        if (
            not valid_identifier(identifier)
            or not isinstance(text, str)
            or not text
            or not valid_display_text(locator, 256)
        ):
            raise ValueError("Missing passage or source locator")
        return CitationPassage(chunk_id=str(identifier), locator=str(locator), text=text, truncated=False)

    def query(self, question: object) -> dict[str, object]:
        """Return bounded original passages from the sole pre-existing collection."""
        normalized = validate_document_query(question)
        if normalized is None:
            return {"error": "document_invalid_query"}
        matches = self.collection.query(
            query_embeddings=[self.encode(normalized).tolist()],
            n_results=min(3, self.chunk_count),
            include=["documents", "metadatas", "distances"],
        )
        documents, metadatas, distances = matches["documents"], matches["metadatas"], matches["distances"]
        if documents is None or metadatas is None or distances is None or not matches["ids"]:
            raise ValueError("Invalid query result")
        candidates: list[tuple[float, CitationPassage]] = []
        for identifier, text, metadata, distance in zip(
            matches["ids"][0], documents[0], metadatas[0], distances[0], strict=True
        ):
            if not math.isfinite(distance):
                raise ValueError("Invalid retrieval distance")
            passage = self._passage(identifier, text, metadata)
            if distance <= self.max_distance:
                candidates.append((distance, passage))
        candidates.sort(key=lambda match: (match[0], match[1]["chunk_id"]))
        passages: list[CitationPassage] = []
        remaining = 2000
        for _distance, passage in candidates[:3]:
            if remaining <= 0:
                break
            text = passage["text"]
            passage["text"] = text[:remaining]
            passage["truncated"] = len(text) > remaining
            remaining -= len(passage["text"])
            passages.append(passage)
        if not passages:
            return {"error": "document_no_evidence"}
        result = DocumentSuccess(
            status="ok",
            document=DocumentIdentity(
                id=str(self.identity["id"]), title=str(self.identity["title"]), version=str(self.identity["version"])
            ),
            index_version=self.index_version,
            passages=passages,
        )
        return validate_document_result(dict(result))


def _emit(envelope: dict[str, object]) -> None:
    envelope["version"] = 1
    sys.stdout.buffer.write(json.dumps(envelope, ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def main() -> int:
    """Serve one local retrieval request at a time over private standard streams."""
    try:
        index = DocumentIndex(
            Path(os.environ["REACHY_MINI_DOCUMENT_INDEX_PATH"]),
            Path(os.environ["REACHY_MINI_DOCUMENT_MODEL_PATH"]),
            Path(os.environ["REACHY_MINI_DOCUMENT_WORK_PATH"]),
        )
    except DocumentModelNotReadyError as error:
        _emit({"type": "failure", "error": "document_not_ready", "exception": type(error).__name__})
        return 1
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, ChromaError) as error:
        _emit({"type": "failure", "error": "document_unavailable", "exception": type(error).__name__})
        return 1
    _emit(
        {
            "type": "ready",
            "document": {key: index.identity[key] for key in ("id", "title", "version")},
            "index_version": index.index_version,
        }
    )
    while True:
        line = sys.stdin.buffer.readline(65537)
        if not line:
            return 0
        try:
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise ValueError("Invalid request size")
            request = _object(json.loads(line))
            if request.get("version") != 1 or request.get("type") != "query":
                raise ValueError("Invalid request protocol")
            request_id = request.get("request_id")
            if not valid_identifier(request_id):
                raise ValueError("Invalid request identity")
            result = index.query(request.get("query"))
            _emit({"type": "result", "request_id": request_id, "payload": result})
        except (OSError, ValueError, TypeError, RuntimeError, ChromaError) as error:
            _emit({"type": "failure", "error": "document_unavailable", "exception": type(error).__name__})
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
