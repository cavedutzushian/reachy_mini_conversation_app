"""Offline package and evidence checks with no model download or real index creation."""

import io
import os
import sys
import json
import hashlib
import importlib
import subprocess
from types import ModuleType, SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.fixture
def document_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Supply a synthetic snapshot and replace only the optional inference libraries."""
    vector = np.array([1.0] + [0.0] * 1023, dtype=np.float32)
    metadata = {"document_id": "manual", "document_version": "v1", "locator": "第一節"}
    collection = MagicMock()
    collection.configuration = {"hnsw": {"space": "cosine"}}
    collection.count.return_value = 1
    collection.get.return_value = {
        "ids": ["first"],
        "documents": ["原文" * 1200],
        "metadatas": [metadata],
        "embeddings": [vector],
    }
    collection.query.return_value = {
        "ids": [["first"]],
        "documents": [["原文" * 1200]],
        "metadatas": [[metadata]],
        "distances": [[0.1]],
    }
    client = MagicMock()
    client.list_collections.return_value = [SimpleNamespace(name="manual")]
    client.get_collection.return_value = collection
    chroma = ModuleType("chromadb")
    chroma.PersistentClient = MagicMock(return_value=client)
    settings = ModuleType("chromadb.config")
    settings.Settings = MagicMock()
    errors = ModuleType("chromadb.errors")
    errors.ChromaError = RuntimeError
    torch = ModuleType("torch")
    torch.float32 = "float32"
    torch.set_num_threads = MagicMock()
    torch.set_num_interop_threads = MagicMock()
    sentence = ModuleType("sentence_transformers")
    encoder = MagicMock()
    encoder.max_seq_length = 8192
    encoder.encode.side_effect = lambda questions, **kwargs: np.array([vector for _ in questions])
    sentence.SentenceTransformer = MagicMock(return_value=encoder)
    for name, module in {
        "chromadb": chroma,
        "chromadb.config": settings,
        "chromadb.errors": errors,
        "torch": torch,
        "sentence_transformers": sentence,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    module_name = "reachy_mini_conversation_app.document_worker"
    monkeypatch.delitem(sys.modules, "reachy_mini_conversation_app.document_model", raising=False)
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    worker = importlib.import_module(module_name)
    monkeypatch.setattr(worker, "version", lambda name: "1.5.9" if name == "chromadb" else "0.0.0")
    package, model, work = tmp_path / "package", tmp_path / "model", tmp_path / "work"
    (package / "chroma").mkdir(parents=True)
    model.mkdir()
    work.mkdir()
    (package / "chroma/chroma.sqlite3").write_bytes(b"synthetic snapshot, not a real Chroma index")
    model_contents = {
        "modules.json": json.dumps(
            [
                {"type": "sentence_transformers.models.Transformer", "path": ""},
                {"type": "sentence_transformers.models.Pooling", "path": "1_Pooling"},
                {"type": "sentence_transformers.models.Normalize", "path": "2_Normalize"},
            ]
        ),
        "1_Pooling/config.json": json.dumps({"pooling_mode_cls_token": True, "pooling_mode_mean_tokens": False}),
        "sentence_bert_config.json": json.dumps({"max_seq_length": 8192, "do_lower_case": False}),
        "model.safetensors": "synthetic model placeholder, never loaded",
    }
    for name, content in model_contents.items():
        target = model / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    platform = worker.runtime_target()
    manifest = {
        "schema_version": 1,
        "index_version": "unit-1",
        "document": {"id": "manual", "title": "測試手冊", "version": "v1", "source_sha256": "0" * 64},
        "engine": {"name": "chromadb", "version": "1.5.9", "collection": "manual"},
        "producer": platform,
        "validated_targets": [platform],
        "snapshot_complete": True,
        "chunk_count": 1,
        "files": [
            {
                "path": "chroma.sqlite3",
                "sha256": hashlib.sha256((package / "chroma/chroma.sqlite3").read_bytes()).hexdigest(),
            }
        ],
        "embedding": {
            "model_id": "BAAI/bge-m3",
            "revision": "0" * 40,
            "files": [
                {"path": name, "sha256": hashlib.sha256((model / name).read_bytes()).hexdigest()}
                for name in model_contents
            ],
            "sentence_transformers_version": "0.0.0",
            "torch_version": "0.0.0",
            "transformers_version": "0.0.0",
            "mode": "dense",
            "dimension": 1024,
            "precision": "float32",
            "pooling": "cls",
            "normalize": True,
            "query_prefix": "",
            "document_prefix": "",
            "max_seq_length": 8192,
            "metric": "cosine",
        },
        "retrieval": {"max_distance": 0.3},
        "reference": {"query": "參考問題", "embedding": vector.tolist()},
    }
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    yield SimpleNamespace(
        worker=worker,
        package=package,
        model=model,
        work=work,
        manifest=manifest,
        collection=collection,
        chroma=chroma,
        client=client,
        sentence=sentence,
        settings=settings,
    )
    sys.modules.pop(module_name, None)
    sys.modules.pop("reachy_mini_conversation_app.document_model", None)


def test_existing_package_returns_bounded_original_text(document_index) -> None:
    """Only a byte copy is opened and original evidence is truncated with its locator."""
    fixture = document_index
    original = (fixture.package / "chroma/chroma.sqlite3").read_bytes()
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work)
    result = index.query("問題")
    assert result["document"]["title"] == "測試手冊"
    assert len(result["passages"][0]["text"]) == 2000
    assert result["passages"][0]["truncated"] is True
    assert result["passages"][0]["locator"] == "第一節"
    assert Path(fixture.chroma.PersistentClient.call_args.kwargs["path"]) != fixture.package / "chroma"
    assert fixture.client.get_collection.call_args.kwargs["embedding_function"] is None
    assert "query_texts" not in fixture.collection.query.call_args.kwargs
    assert (fixture.package / "chroma/chroma.sqlite3").read_bytes() == original
    fixture.client.create_collection.assert_not_called()
    fixture.collection.add.assert_not_called()
    assert fixture.sentence.SentenceTransformer.call_args.kwargs["device"] == "cpu"
    assert fixture.sentence.SentenceTransformer.call_args.kwargs["local_files_only"] is True


@pytest.mark.parametrize(
    "fault",
    [
        "checksum",
        "missing_file",
        "unlisted_file",
        "escaped_path",
        "duplicate_path",
        "incomplete_snapshot",
        "version",
        "platform",
        "multiple_collections",
        "empty",
        "metric",
        "locator",
        "missing_text",
        "dimension",
        "nonfinite",
        "norm",
        "reference_norm",
        "reference_nan",
        "pipeline",
        "null",
        "unknown_nested",
        "journal",
        "migration",
    ],
)
def test_invalid_snapshot_never_repairs_or_rebuilds(document_index, fault: str) -> None:
    """All incompatible inputs fail closed without invoking a write API."""
    fixture = document_index
    manifest = fixture.manifest
    if fault == "checksum":
        manifest["files"][0]["sha256"] = "f" * 64
    elif fault == "missing_file":
        (fixture.package / "chroma/chroma.sqlite3").unlink()
    elif fault == "unlisted_file":
        (fixture.package / "chroma/unlisted").write_bytes(b"unexpected")
    elif fault == "escaped_path":
        manifest["files"][0]["path"] = "../outside"
    elif fault == "duplicate_path":
        manifest["files"].append(dict(manifest["files"][0]))
    elif fault == "incomplete_snapshot":
        manifest["snapshot_complete"] = False
    elif fault == "version":
        manifest["embedding"]["torch_version"] = "0.0.0+different"
    elif fault == "platform":
        manifest["validated_targets"] = [{"os": "other", "architecture": "x86_64"}]
    elif fault == "multiple_collections":
        fixture.client.list_collections.return_value = ["manual", "other"]
    elif fault == "empty":
        fixture.collection.count.return_value = 0
    elif fault == "metric":
        fixture.collection.configuration = {"hnsw": {"space": "l2"}}
    elif fault == "locator":
        fixture.collection.get.return_value["metadatas"][0]["locator"] = ""
    elif fault == "missing_text":
        fixture.collection.get.return_value["documents"] = None
    elif fault == "dimension":
        fixture.collection.get.return_value["embeddings"] = [[1.0]]
    elif fault == "nonfinite":
        fixture.collection.get.return_value["embeddings"][0][0] = np.nan
    elif fault == "norm":
        fixture.collection.get.return_value["embeddings"][0][0] = 0.5
    elif fault == "reference_norm":
        manifest["reference"]["embedding"][0] = 0.5
    elif fault == "reference_nan":
        manifest["reference"]["embedding"][0] = float("nan")
    elif fault == "pipeline":
        manifest["embedding"]["pooling"] = "mean"
    elif fault == "null":
        manifest["document"]["title"] = None
    elif fault == "journal":
        (fixture.package / "chroma/chroma.sqlite3-wal").write_bytes(b"unflushed")
        manifest["files"].append({"path": "chroma.sqlite3-wal", "sha256": hashlib.sha256(b"unflushed").hexdigest()})
    elif fault == "migration":
        fixture.chroma.PersistentClient.side_effect = RuntimeError("private-migration-sentinel")
    else:
        manifest["embedding"]["unexpected"] = True
    (fixture.package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work)
    for owner in (fixture.client, fixture.collection):
        for method in (
            "create_collection",
            "get_or_create_collection",
            "modify",
            "add",
            "upsert",
            "update",
            "delete",
            "reset",
        ):
            getattr(owner, method).assert_not_called()


def test_missing_local_model_does_not_download_or_open_chroma(document_index) -> None:
    """A missing local model is distinguishable from an invalid document package."""
    fixture = document_index
    with pytest.raises(fixture.worker.DocumentModelNotReadyError):
        fixture.worker.DocumentIndex(fixture.package, fixture.model / "missing", fixture.work)
    fixture.sentence.SentenceTransformer.assert_not_called()
    fixture.chroma.PersistentClient.assert_not_called()


def test_model_module_path_cannot_escape_checked_inventory(document_index) -> None:
    """Even a checksum-matching model cannot direct ST to an unchecked module path."""
    fixture = document_index
    modules_path = fixture.model / "modules.json"
    modules = json.loads(modules_path.read_text(encoding="utf-8"))
    modules[0]["path"] = "../unchecked-model"
    modules_path.write_text(json.dumps(modules), encoding="utf-8")
    for entry in fixture.manifest["embedding"]["files"]:
        if entry["path"] == "modules.json":
            entry["sha256"] = hashlib.sha256(modules_path.read_bytes()).hexdigest()
    (fixture.package / "manifest.json").write_text(json.dumps(fixture.manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="module paths"):
        fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work)
    fixture.sentence.SentenceTransformer.assert_not_called()


def test_low_relevance_does_not_fabricate_evidence(document_index) -> None:
    """A distance above the calibrated limit yields a distinct no-evidence outcome."""
    fixture = document_index
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work)
    fixture.collection.query.return_value["distances"] = [[0.9]]
    assert index.query("問題") == {"error": "document_no_evidence"}


def test_three_passages_have_stable_ties_and_an_explicit_query_limit(document_index) -> None:
    """Multiple candidates remain bounded and equal distances use stable passage identifiers."""
    fixture = document_index
    vector = fixture.collection.get.return_value["embeddings"][0]
    metadata = fixture.collection.get.return_value["metadatas"][0]
    fixture.manifest["chunk_count"] = 3
    (fixture.package / "manifest.json").write_text(json.dumps(fixture.manifest), encoding="utf-8")
    fixture.collection.count.return_value = 3
    fixture.collection.get.return_value = {
        "ids": ["b", "a", "c"],
        "documents": ["乙", "甲", "丙"],
        "metadatas": [metadata] * 3,
        "embeddings": [vector] * 3,
    }
    fixture.collection.query.return_value = {
        "ids": [["b", "a", "c"]],
        "documents": [["乙", "甲", "丙"]],
        "metadatas": [[metadata] * 3],
        "distances": [[0.1, 0.1, 0.2]],
    }
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work)
    result = index.query("問題")
    assert [passage["chunk_id"] for passage in result["passages"]] == ["a", "b", "c"]
    assert fixture.collection.query.call_args.kwargs["n_results"] == 3


@pytest.mark.parametrize("change", ["missing", "unknown", "wrong_revision", "mixed_document"])
def test_incomplete_or_incompatible_package_is_not_repaired(document_index, change: str) -> None:
    """Invalid packages are rejected without creating a replacement collection."""
    fixture = document_index
    if change == "missing":
        del fixture.manifest["reference"]
    elif change == "unknown":
        fixture.manifest["extra"] = "not allowed"
    elif change == "wrong_revision":
        fixture.manifest["embedding"]["revision"] = "main"
    else:
        fixture.collection.get.return_value["metadatas"][0]["document_id"] = "another-document"
    (fixture.package / "manifest.json").write_text(json.dumps(fixture.manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work)
    fixture.client.create_collection.assert_not_called()


def test_worker_ready_identity_matches_query_identity(document_index, monkeypatch) -> None:
    """The private ready handshake and query results use the same public source identity."""
    fixture = document_index
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work)
    envelopes = []
    monkeypatch.setattr(fixture.worker, "DocumentIndex", MagicMock(return_value=index))
    monkeypatch.setattr(fixture.worker, "_emit", envelopes.append)
    monkeypatch.setattr(fixture.worker, "sys", SimpleNamespace(stdin=SimpleNamespace(buffer=io.BytesIO())))
    for name in ("INDEX", "MODEL", "WORK"):
        monkeypatch.setenv("REACHY_MINI_DOCUMENT_" + name + "_PATH", "unused")
    assert fixture.worker.main() == 0
    assert envelopes[0]["document"] == index.query("問題")["document"]


def test_replacement_package_is_only_used_by_a_new_index_instance(document_index) -> None:
    """A restarted reader reports only the replacement document and index version."""
    fixture = document_index
    first = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work)
    assert first.query("問題")["document"]["version"] == "v1"
    fixture.manifest["document"]["version"] = "v2"
    fixture.manifest["index_version"] = "unit-2"
    (fixture.package / "manifest.json").write_text(json.dumps(fixture.manifest), encoding="utf-8")
    fixture.collection.get.return_value["metadatas"][0]["document_version"] = "v2"
    replacement = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work / "replacement")
    result = replacement.query("問題")
    assert result["document"]["version"] == "v2"
    assert result["index_version"] == "unit-2"
    assert first.identity["version"] == "v1"


def test_external_prebuilt_snapshot_integrity(tmp_path: Path) -> None:
    """Opt in to real snapshot verification without creating or rebuilding any index."""
    package = os.environ.get("RAG_ACCEPTANCE_PACKAGE")
    model = os.environ.get("RAG_ACCEPTANCE_MODEL")
    if not package or not model:
        pytest.skip("Real prebuilt package and matching local model have not been supplied")
    script = """
import os, json, hashlib
from pathlib import Path
from reachy_mini_conversation_app.document_worker import DocumentIndex
package, model, work = (Path(os.environ[key]) for key in
    ("RAG_ACCEPTANCE_PACKAGE", "RAG_ACCEPTANCE_MODEL", "RAG_ACCEPTANCE_WORK"))
def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}
before = hashes(package)
manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
index = DocumentIndex(package, model, work)
snapshot_before = hashes(work / "chroma")
rows_before = index.collection.get(include=["documents", "metadatas", "embeddings"])
index.query(manifest["reference"]["query"])
rows_after = index.collection.get(include=["documents", "metadatas", "embeddings"])
for field in ("ids", "documents", "metadatas"):
    assert rows_before[field] == rows_after[field]
import numpy as np
assert np.array_equal(rows_before["embeddings"], rows_after["embeddings"])
assert before == hashes(package)
snapshot_after = hashes(work / "chroma")
for path, digest in before.items():
    if path.startswith("chroma/") and not Path(path).name.startswith("chroma.sqlite3"):
        relative = path.removeprefix("chroma/")
        assert snapshot_before[relative] == digest == snapshot_after[relative]
assert index.collection.count() == manifest["chunk_count"]
"""
    environment = dict(
        os.environ,
        RAG_ACCEPTANCE_WORK=str(tmp_path / "work"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        ANONYMIZED_TELEMETRY="False",
        REACHY_MINI_SKIP_DOTENV="1",
    )
    result = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True, timeout=180)
    assert result.returncode == 0, (
        "Real snapshot integrity verification failed; inspect locally without publishing content"
    )
