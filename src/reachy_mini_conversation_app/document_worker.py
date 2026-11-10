import os
import sys
import json
import math
import shutil
import hashlib
import logging
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
from chromadb.api.client import Client

from reachy_mini_conversation_app.document_model import (
    DocumentModel,
    DocumentReranker,
    DocumentModelNotReadyError,
    object_value,
    verify_files,
)
from reachy_mini_conversation_app.document_assets import (
    PreparationError,
    read_object,
    parse_object,
    lexical_terms,
    file_inventory,
    validate_receipt,
    source_line_numbers,
    load_preparation_scheme,
)
from reachy_mini_conversation_app.document_retrieval import (
    CitationPassage,
    DocumentSuccess,
    DocumentIdentity,
    valid_identifier,
    valid_display_text,
    validate_document_query,
    validate_document_result,
)


logger = logging.getLogger(__name__)


def runtime_target() -> dict[str, str]:
    """Normalize the runtime platform to the package's explicit target vocabulary."""
    return {
        "os": {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), "unsupported"),
        "architecture": {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(
            platform.machine().lower(), "unsupported"
        ),
    }


class LegacyDocumentPackageError(ValueError):
    """Identify only a parsed integer v1 header before opening any engine."""


class DocumentIndex:
    """Read a sealed v2 package with prebuilt lexical data and fixed CPU reranking."""

    def __init__(
        self, package_path: Path, model_path: Path, work_path: Path, reranker_path: Path | None = None
    ) -> None:
        """Validate every asset before querying a complete private copy of the package."""
        manifest = read_object(package_path / "manifest.json")
        if type(manifest.get("schema_version")) is int and manifest["schema_version"] == 1:
            raise LegacyDocumentPackageError("Offline regeneration is required")
        schema = json.loads(
            files("reachy_mini_conversation_app").joinpath("document_manifest.schema.json").read_text(encoding="utf-8")
        )
        if list(Draft202012Validator(schema).iter_errors(manifest)):
            raise ValueError("Invalid document manifest")
        scheme = load_preparation_scheme()
        for key in ("strategy", "chunking", "bm25", "retrieval", "provenance"):
            if manifest[key] != scheme[key]:
                raise ValueError("Selected scheme mismatch")
        if reranker_path is None:
            raise DocumentModelNotReadyError("Local reranker is unavailable")
        self.identity = object_value(manifest["document"])
        if not valid_display_text(self.identity["title"], 160):
            raise ValueError("Invalid document title")
        self.index_version = str(manifest["index_version"])
        embedding, reranking, engine = (object_value(manifest[key]) for key in ("embedding", "reranking", "engine"))
        targets = manifest["validated_targets"]
        if (
            not isinstance(targets, list)
            or runtime_target() not in targets
            or version("chromadb") != engine["version"]
        ):
            raise ValueError("Unvalidated runtime target")
        for role, directory, configuration in (
            ("embedding", model_path, embedding),
            ("reranker", reranker_path, reranking),
        ):
            if not directory.is_dir() or not (directory / "model-receipt.json").is_file():
                raise DocumentModelNotReadyError("Local model is unavailable")
            try:
                receipt = validate_receipt(directory)
            except PreparationError:
                raise ValueError("Invalid local model receipt") from None
            if receipt["role"] != role or receipt["revision"] != configuration["revision"]:
                raise ValueError("Model role mismatch")
            for package, key in (
                ("sentence-transformers", "sentence_transformers_version"),
                ("torch", "torch_version"),
                ("transformers", "transformers_version"),
            ):
                if version(package) != configuration[key]:
                    raise ValueError("Model runtime mismatch")
            verify_files(directory, configuration["files"])
        verify_files(package_path / "chroma", manifest["files"])
        verify_files(package_path / "retrieval", object_value(manifest["assets"])["files"])
        inventory = manifest["files"]
        if not isinstance(inventory, list) or any(
            str(object_value(entry)["path"]).endswith(("-wal", "-shm", "-journal")) for entry in inventory
        ):
            raise ValueError("Unsealed snapshot")
        expected_paths = {"manifest.json"}
        for folder, entries in (("chroma", inventory), ("retrieval", object_value(manifest["assets"])["files"])):
            if not isinstance(entries, list):
                raise ValueError("Invalid asset inventory")
            expected_paths.update(folder + "/" + str(object_value(entry)["path"]) for entry in entries)
        if {str(entry["path"]) for entry in file_inventory(package_path)} != expected_paths:
            raise ValueError("Unlisted package files")
        self._chunks: list[dict[str, object]] = []
        seen: set[str] = set()
        assembled = ""
        previous_start = -1
        with (package_path / "retrieval/chunks.jsonl").open("rb") as stream:
            while True:
                line = stream.readline(16 * 1024 * 1024 + 1)
                if not line:
                    break
                if len(line) > 16 * 1024 * 1024:
                    raise ValueError("Oversized source record")
                row = parse_object(line)
                if set(row) != {
                    "chunk_id",
                    "document_id",
                    "document_version",
                    "start",
                    "end",
                    "line_start",
                    "line_end",
                    "text",
                    "headings",
                    "aliases",
                    "context",
                    "alias_context",
                    "model_text",
                    "model_text_sha256",
                }:
                    raise ValueError("Invalid source record")
                identifier, text = row["chunk_id"], row["text"]
                start, stop = row["start"], row["end"]
                if (
                    not valid_identifier(identifier)
                    or not isinstance(identifier, str)
                    or identifier in seen
                    or not isinstance(text, str)
                    or not text
                    or type(start) is not int
                    or type(stop) is not int
                ):
                    raise ValueError("Invalid source interval")
                if (
                    not isinstance(start, int)
                    or not isinstance(stop, int)
                    or not 0 <= start < stop
                    or stop - start != len(text)
                    or start > len(assembled)
                    or assembled[start : min(stop, len(assembled))] != text[: max(0, len(assembled) - start)]
                    or start < previous_start
                ):
                    raise ValueError("Source gap or overlap mismatch")
                previous_start = start
                assembled += text[max(0, len(assembled) - start) :]
                if row["document_id"] != self.identity["id"] or row["document_version"] != self.identity["version"]:
                    raise ValueError("Mixed document sources")
                if not isinstance(row["context"], str) or not isinstance(row["alias_context"], str):
                    raise ValueError("Invalid source context")
                prefix = (
                    f"脈絡：{row['context']}\n"
                    + (f"戰隊別名：{row['alias_context']}\n" if row["alias_context"] else "")
                    + "原文：\n"
                )
                if (
                    row["model_text"] != prefix + text
                    or row["model_text_sha256"] != hashlib.sha256((prefix + text).encode("utf-8")).hexdigest()
                ):
                    raise ValueError("Model source mapping mismatch")
                seen.add(identifier)
                self._chunks.append(row)
        if len(self._chunks) != manifest["chunk_count"] or not self._chunks:
            raise ValueError("Source count mismatch")
        lines = source_line_numbers(assembled)
        for row in self._chunks:
            first, stop = row["start"], row["end"]
            if type(row["line_start"]) is not int or type(row["line_end"]) is not int:
                raise ValueError("Invalid source line type")
            if (
                not isinstance(first, int)
                or not isinstance(stop, int)
                or row["line_start"] != lines[first]
                or row["line_end"] != lines[stop - 1]
            ):
                raise ValueError("Source line mismatch")
            for key, text_key, first_key, last_key, line_first_key, line_last_key in (
                ("headings", "text", "start", "end", "line_start", "line_end"),
                ("aliases", "text", "evidence_start", "evidence_end", "evidence_line_start", "evidence_line_end"),
            ):
                entries = row[key]
                if not isinstance(entries, list):
                    raise ValueError("Invalid source labels")
                for entry in entries:
                    label = object_value(entry)
                    allowed = {text_key, first_key, last_key, line_first_key, line_last_key}
                    if key == "aliases":
                        allowed.update(("scope_start", "scope_end"))
                    if set(label) != allowed:
                        raise ValueError("Invalid source label fields")
                    label_first, label_last = label[first_key], label[last_key]
                    if (
                        type(label_first) is not int
                        or type(label_last) is not int
                        or not isinstance(label_first, int)
                        or not isinstance(label_last, int)
                        or not 0 <= label_first <= label_last <= len(assembled)
                        or label[text_key] != assembled[label_first:label_last]
                    ):
                        raise ValueError("Source evidence mismatch")
                    if (
                        label[line_first_key] != lines[min(label_first, len(lines) - 1)]
                        or label[line_last_key] != lines[max(0, label_last - 1)]
                    ):
                        raise ValueError("Source evidence line mismatch")
                    if key == "aliases":
                        scope_first, scope_last = label["scope_start"], label["scope_end"]
                        if (
                            type(scope_first) is not int
                            or type(scope_last) is not int
                            or not isinstance(scope_first, int)
                            or not isinstance(scope_last, int)
                            or not 0 <= scope_first <= label_first < label_last <= scope_last <= len(assembled)
                            or not scope_first <= first < stop <= scope_last
                        ):
                            raise ValueError("Alias scope mismatch")
        stats = read_object(package_path / "retrieval/bm25.json")
        if (
            set(stats)
            != {
                "version",
                "chunk_ids",
                "term_frequencies",
                "document_lengths",
                "document_frequencies",
                "average_document_length",
            }
            or stats["version"] != "bm25-prebuilt-v1"
            or stats["chunk_ids"] != [row["chunk_id"] for row in self._chunks]
        ):
            raise ValueError("Invalid prebuilt lexical identity")
        frequencies = stats["term_frequencies"]
        if not isinstance(frequencies, list) or len(frequencies) != len(self._chunks):
            raise ValueError("Invalid lexical rows")
        self._counts: list[dict[str, int]] = []
        calculated_df: dict[str, int] = {}
        self._lengths: list[int] = []
        for value in frequencies:
            frequency = object_value(value)
            counts: dict[str, int] = {}
            for term, count in frequency.items():
                if not term or type(count) is not int or not isinstance(count, int) or count <= 0:
                    raise ValueError("Invalid lexical term frequency")
                counts[term] = count
                calculated_df[term] = calculated_df.get(term, 0) + 1
            self._counts.append(counts)
            self._lengths.append(sum(counts.values()))
        stored_lengths = stats["document_lengths"]
        stored_df = object_value(stats["document_frequencies"])
        if (
            not isinstance(stored_lengths, list)
            or any(type(item) is not int for item in stored_lengths)
            or any(type(item) is not int for item in stored_df.values())
        ):
            raise ValueError("Invalid lexical integer type")
        if stats["document_lengths"] != self._lengths or stats["document_frequencies"] != calculated_df:
            raise ValueError("Inconsistent prebuilt statistics")
        average = stats["average_document_length"]
        if (
            isinstance(average, bool)
            or not isinstance(average, (int, float))
            or not math.isfinite(average)
            or average != sum(self._lengths) / len(self._lengths)
        ):
            raise ValueError("Invalid prebuilt average length")
        self._average = float(average)
        self._df = calculated_df
        self.model = DocumentModel(model_path, embedding, object_value(manifest["reference"]))
        self.reranker = DocumentReranker(reranker_path, reranking)
        snapshot = work_path / "chroma"
        work_path.mkdir(parents=True, exist_ok=True)
        if any(work_path.iterdir()):
            raise ValueError("Expected a private empty work directory")
        shutil.copytree(package_path, work_path, dirs_exist_ok=True)
        verify_files(snapshot, inventory)
        verify_files(work_path / "retrieval", object_value(manifest["assets"])["files"])
        if read_object(work_path / "manifest.json") != manifest:
            raise ValueError("Copied manifest changed")
        self.client = chromadb.PersistentClient(
            path=str(snapshot), settings=Settings(migrations="validate", anonymized_telemetry=False, allow_reset=False)
        )
        if not isinstance(self.client, Client):
            raise ValueError("Unsupported public client")
        self._vectors: dict[str, NDArray[np.float32]] = {}
        try:
            if len(self.client.list_collections()) != 1:
                raise ValueError("Expected exactly one document collection")
            self.collection = self.client.get_collection(name=str(engine["collection"]), embedding_function=None)
            if object_value(object_value(self.collection.configuration).get("hnsw")).get("space") != "cosine":
                raise ValueError("Collection metric mismatch")
            self.chunk_count = self.collection.count()
            if self.chunk_count != len(self._chunks):
                raise ValueError("Collection count mismatch")
            by_id = {str(row["chunk_id"]): row for row in self._chunks}
            for offset in range(0, self.chunk_count, 256):
                batch = self.collection.get(limit=256, offset=offset, include=["documents", "metadatas", "embeddings"])
                documents, metadatas, vectors = batch["documents"], batch["metadatas"], batch["embeddings"]
                if documents is None or metadatas is None or vectors is None:
                    raise ValueError("Missing document fields")
                for identifier, text, metadata, vector in zip(
                    batch["ids"], documents, metadatas, vectors, strict=True
                ):
                    if identifier not in by_id or identifier in self._vectors:
                        raise ValueError("Unlisted or duplicate passage")
                    row = by_id[identifier]
                    expected_metadata = {
                        "document_id": self.identity["id"],
                        "document_version": self.identity["version"],
                        "locator": f"L{row['line_start']}-L{row['line_end']}; chars[{row['start']},{row['end']})",
                    }
                    if text != row["text"] or metadata != expected_metadata:
                        raise ValueError("Original row mismatch")
                    values = np.asarray(vector, dtype=np.float32)
                    if (
                        values.shape != (1024,)
                        or not np.isfinite(values).all()
                        or abs(float(np.linalg.norm(values)) - 1) > 1e-4
                    ):
                        raise ValueError("Invalid document vector")
                    self._vectors[identifier] = values
            if set(self._vectors) != set(by_id):
                raise ValueError("Incomplete document collection")
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, ChromaError):
            self.client.close()
            raise

    def query(self, question: object) -> dict[str, object]:
        """Fuse exact dense and prebuilt BM25 candidates before fixed reranking and distance filtering."""
        normalized = validate_document_query(question)
        if normalized is None:
            return {"error": "document_invalid_query"}
        query_vector = self.model.encode(normalized)
        distances = {
            identifier: 1 - float(np.dot(vector, query_vector)) for identifier, vector in self._vectors.items()
        }
        dense = sorted(distances, key=lambda identifier: (distances[identifier], identifier))[:10]
        terms = set(lexical_terms(normalized))
        lexical: dict[str, float] = {}
        for row, counts, length in zip(self._chunks, self._counts, self._lengths, strict=True):
            score = 0.0
            if self._average:
                for term in terms:
                    frequency = counts.get(term, 0)
                    if frequency:
                        idf = math.log1p((self.chunk_count - self._df[term] + 0.5) / (self._df[term] + 0.5))
                        score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / self._average))
            if score > 0:
                lexical[str(row["chunk_id"])] = score
        lexical_ids = sorted(lexical, key=lambda identifier: (-lexical[identifier], identifier))[:10]
        fusion: dict[str, float] = {}
        for ranking in (dense, lexical_ids):
            for rank, identifier in enumerate(ranking, 1):
                fusion[identifier] = fusion.get(identifier, 0) + 1 / (60 + rank)
        candidates = sorted(fusion, key=lambda identifier: (-fusion[identifier], identifier))[:5]
        by_id = {str(row["chunk_id"]): row for row in self._chunks}
        visible = self.reranker.score_passages(
            normalized, [(str(by_id[key]["model_text"]), str(by_id[key]["text"])) for key in candidates]
        )
        ranked = sorted(visible, key=lambda item: (-item[1], candidates[item[0]]))
        if not ranked or ranked[0][1] < 3.486859679222107:
            return {"error": "document_no_evidence"}
        selected: list[CitationPassage] = []
        remaining = 2000
        for ordinal, score, text, truncated in ranked:
            if score < 3.486859679222107 or ranked[0][1] - score > 4 or remaining <= 0 or len(selected) == 3:
                continue
            identifier = candidates[ordinal]
            row = by_id[identifier]
            original = text
            text = text[:remaining]
            if text.endswith("\r") and original[len(text) :].startswith("\n"):
                text = text[:-1]
            if not text:
                continue
            remaining -= len(text)
            first = row["start"]
            if not isinstance(first, int):
                raise ValueError("Invalid visible source interval")
            line_first = row["line_start"]
            if not isinstance(line_first, int):
                raise ValueError("Invalid visible source line")
            last_line = line_first + source_line_numbers(text)[-1] - 1
            locator = f"L{line_first}-L{last_line}; chars[{first},{first + len(text)})"
            selected.append(
                CitationPassage(
                    chunk_id=identifier, locator=locator, text=text, truncated=truncated or len(text) < len(original)
                )
            )
        if not selected or distances[selected[0]["chunk_id"]] > 0.58:
            return {"error": "document_no_evidence"}
        selected = [passage for passage in selected if distances[passage["chunk_id"]] <= 0.58]
        result = DocumentSuccess(
            status="ok",
            document=DocumentIdentity(
                id=str(self.identity["id"]), title=str(self.identity["title"]), version=str(self.identity["version"])
            ),
            index_version=self.index_version,
            passages=selected,
        )
        return validate_document_result(dict(result))


def _emit(envelope: dict[str, object]) -> None:
    envelope["version"] = 1
    sys.stdout.buffer.write(json.dumps(envelope, ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def main() -> int:
    """Serve one local retrieval request at a time over private standard streams."""
    try:
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        index = DocumentIndex(
            Path(os.environ["REACHY_MINI_DOCUMENT_INDEX_PATH"]),
            Path(os.environ["REACHY_MINI_DOCUMENT_MODEL_PATH"]),
            Path(os.environ["REACHY_MINI_DOCUMENT_WORK_PATH"]),
            Path(os.environ["REACHY_MINI_DOCUMENT_RERANKER_PATH"])
            if os.environ.get("REACHY_MINI_DOCUMENT_RERANKER_PATH")
            else None,
        )
    except LegacyDocumentPackageError as error:
        logger.warning("Document initialization failed: %s", type(error).__name__)
        _emit(
            {
                "type": "failure",
                "error": "document_unavailable",
                "reason": "legacy_package",
            }
        )
        return 1
    except DocumentModelNotReadyError as error:
        logger.warning("Document initialization failed: %s", type(error).__name__)
        _emit({"type": "failure", "error": "document_not_ready"})
        return 1
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, ChromaError) as error:
        logger.warning("Document worker failed: %s", type(error).__name__)
        _emit({"type": "failure", "error": "document_unavailable"})
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
            request = object_value(json.loads(line))
            if request.get("version") != 1 or request.get("type") != "query":
                raise ValueError("Invalid request protocol")
            request_id = request.get("request_id")
            if not valid_identifier(request_id):
                raise ValueError("Invalid request identity")
            result = index.query(request.get("query"))
            _emit({"type": "result", "request_id": request_id, "payload": result})
        except (OSError, ValueError, TypeError, RuntimeError, ChromaError) as error:
            logger.warning("Document worker failed: %s", type(error).__name__)
            _emit({"type": "failure", "error": "document_unavailable"})
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
