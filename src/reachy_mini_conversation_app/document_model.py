import os
import json
import hashlib
from pathlib import Path

import numpy as np
import torch
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer

from reachy_mini_conversation_app.document_retrieval import validate_document_query


class DocumentModelNotReadyError(RuntimeError):
    """Identify a missing or unusable local model without exposing its path."""


def object_value(value: object) -> dict[str, object]:
    """Require string-keyed JSON objects without weakening nested validation."""
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("Expected an object")
    return dict(value)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def read_json(path: Path) -> object:
    """Read bounded local JSON while rejecting a BOM and duplicate keys."""
    with path.open("rb") as handle:
        payload = handle.read(16 * 1024 * 1024 + 1)
    if len(payload) > 16 * 1024 * 1024 or payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("Unsupported JSON encoding or size")
    return json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_pairs)


def verify_files(root: Path, entries: object) -> None:
    """Verify every listed byte and reject missing, unlisted or linked files."""
    if not root.is_dir() or root.is_symlink() or root.is_junction() or not isinstance(entries, list):
        raise ValueError("Invalid package directory")
    expected: dict[str, str] = {}
    aliases: set[str] = set()
    for entry in entries:
        record = object_value(entry)
        relative, digest = record.get("path"), record.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise ValueError("Invalid inventory entry")
        if any(part in ("", ".", "..") for part in relative.split("/")) or "\\" in relative or ":" in relative:
            raise ValueError("Invalid package path")
        candidate = root / relative
        if not candidate.resolve().is_relative_to(root.resolve()) or relative in expected:
            raise ValueError("Duplicate or escaped package path")
        alias = "/".join(part.rstrip(" .").casefold() for part in relative.split("/"))
        if os.name == "nt" and alias in aliases:
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


class DocumentModel:
    """Load and encode with the existing checked local CPU pipeline."""

    def __init__(self, model_path: Path, embedding: dict[str, object], reference: dict[str, object] | None) -> None:
        """Validate all model files, built-in modules and the reference vector before use."""
        if not model_path.is_dir():
            raise DocumentModelNotReadyError("Local model is unavailable")
        verify_files(model_path, embedding["files"])
        modules = read_json(model_path / "modules.json")
        if not isinstance(modules, list) or [object_value(module).get("type") for module in modules] != [
            "sentence_transformers.models.Transformer",
            "sentence_transformers.models.Pooling",
            "sentence_transformers.models.Normalize",
        ]:
            raise ValueError("Unsupported model modules")
        if [object_value(module).get("path") for module in modules] != ["", "1_Pooling", "2_Normalize"]:
            raise ValueError("Unsupported model module paths")
        pooling = object_value(read_json(model_path / "1_Pooling/config.json"))
        if pooling.get("pooling_mode_cls_token") is not True or any(
            bool(value)
            for key, value in pooling.items()
            if key.startswith("pooling_mode_") and key != "pooling_mode_cls_token"
        ):
            raise ValueError("Unsupported pooling")
        encoder_config = object_value(read_json(model_path / "sentence_bert_config.json"))
        if encoder_config.get("max_seq_length") != 8192 or encoder_config.get("do_lower_case") is not False:
            raise ValueError("Unsupported tokenizer settings")
        inventory = embedding["files"]
        if not isinstance(inventory, list):
            raise ValueError("Missing model inventory")
        model_files = [str(object_value(entry)["path"]) for entry in inventory]
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
        if reference is not None:
            reference_query = validate_document_query(reference["query"])
            if reference_query is None:
                raise ValueError("Invalid reference question")
            reference_vector = np.asarray(reference["embedding"], dtype=np.float32)
            if not np.isfinite(reference_vector).all() or abs(float(np.linalg.norm(reference_vector)) - 1) > 1e-4:
                raise ValueError("Invalid reference vector")
            if abs(1 - float(np.dot(self.encode(reference_query), reference_vector))) > 1e-5:
                raise ValueError("Reference embedding mismatch")
        verify_files(model_path, embedding["files"])

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

    def offsets(self, text: str) -> list[tuple[int, int]]:
        """Return fast-tokenizer source offsets without special tokens or truncation."""
        if not self.encoder.tokenizer.is_fast:
            raise ValueError("A fast tokenizer is required")
        encoded = self.encoder.tokenizer(text, add_special_tokens=False, truncation=False, return_offsets_mapping=True)
        identifiers, mapping = encoded["input_ids"], encoded["offset_mapping"]
        if not isinstance(identifiers, list) or not isinstance(mapping, list) or len(identifiers) != len(mapping):
            raise ValueError("Invalid tokenizer mapping")
        offsets: list[tuple[int, int]] = []
        for interval in mapping:
            if not isinstance(interval, (list, tuple)) or len(interval) != 2:
                raise ValueError("Invalid tokenizer offset")
            start, end = interval
            if not isinstance(start, int) or not isinstance(end, int):
                raise ValueError("Invalid tokenizer offset")
            offsets.append((start, end))
        return offsets

    def encoded_count(self, text: str) -> int:
        """Count input tokens including special tokens without truncation."""
        identifiers = self.encoder.tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"]
        if not isinstance(identifiers, list):
            raise ValueError("Invalid tokenizer output")
        return len(identifiers)
