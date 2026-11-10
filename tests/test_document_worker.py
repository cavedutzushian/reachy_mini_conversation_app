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
from collections import Counter
from unittest.mock import MagicMock
from importlib.metadata import version

import numpy as np
import pytest


def write_retrieval_assets(package: Path, manifest: dict, rows: list[dict]) -> None:
    """Write internally consistent synthetic source assets for reader behavior tests."""
    from reachy_mini_conversation_app.document_assets import lexical_terms, file_inventory

    directory = package / "retrieval"
    directory.mkdir(exist_ok=True)
    for row in rows:
        row["model_text_sha256"] = hashlib.sha256(row["model_text"].encode("utf-8")).hexdigest()
    (directory / "chunks.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    counts = [dict(Counter(lexical_terms(row["model_text"]))) for row in rows]
    lengths = [sum(frequency.values()) for frequency in counts]
    df = Counter()
    for frequency in counts:
        df.update(frequency.keys())
    stats = {
        "version": "bm25-prebuilt-v1",
        "chunk_ids": [row["chunk_id"] for row in rows],
        "term_frequencies": counts,
        "document_lengths": lengths,
        "document_frequencies": dict(df),
        "average_document_length": sum(lengths) / len(lengths),
    }
    (directory / "bm25.json").write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    manifest["assets"] = {"files": file_inventory(directory)}
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


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
    client_module = ModuleType("chromadb.api.client")
    client_module.Client = MagicMock
    torch = ModuleType("torch")
    torch.float32 = "float32"
    torch.nn = SimpleNamespace(Identity=MagicMock())
    torch.set_num_threads = MagicMock()
    torch.set_num_interop_threads = MagicMock()
    sentence = ModuleType("sentence_transformers")
    encoder = MagicMock()
    encoder.max_seq_length = 8192
    encoder.encode.side_effect = lambda questions, **kwargs: np.array([vector for _ in questions])
    sentence.SentenceTransformer = MagicMock(return_value=encoder)
    sentence.CrossEncoder = MagicMock()
    for name, module in {
        "chromadb": chroma,
        "chromadb.config": settings,
        "chromadb.errors": errors,
        "chromadb.api.client": client_module,
        "torch": torch,
        "sentence_transformers": sentence,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    module_name = "reachy_mini_conversation_app.document_worker"
    monkeypatch.delitem(sys.modules, "reachy_mini_conversation_app.document_model", raising=False)
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    worker = importlib.import_module(module_name)
    monkeypatch.setattr(worker, "version", version)
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
    from reachy_mini_conversation_app.document_assets import (
        PAYLOAD_FILES,
        MODEL_REVISION,
        RERANKER_REVISION,
        RERANKER_PAYLOAD_FILES,
        file_inventory,
        load_preparation_scheme,
    )

    runtime = {
        "sentence_transformers_version": version("sentence-transformers"),
        "torch_version": version("torch"),
        "transformers_version": version("transformers"),
    }
    reranker = tmp_path / "reranker"
    reranker.mkdir()
    for role, directory, names, model_id, revision in (
        ("embedding", model, PAYLOAD_FILES, "BAAI/bge-m3", MODEL_REVISION),
        ("reranker", reranker, RERANKER_PAYLOAD_FILES, "BAAI/bge-reranker-base", RERANKER_REVISION),
    ):
        for name in names:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(b"synthetic; never loaded")
        verification = {"kind": role, "query": "這份文件主要說明什麼？", "device": "cpu", "precision": "float32"}
        if role == "embedding":
            verification["embedding"] = vector.tolist()
        else:
            (directory / "config.json").write_text(
                json.dumps({"model_type": "xlm-roberta", "architectures": ["XLMRobertaForSequenceClassification"]}),
                encoding="utf-8",
            )
            verification.update(
                passage="這是一份提供文件查詢的示範說明。", logit=4.5, activation="identity", max_pair_tokens=512
            )
        receipt = {
            "schema_version": 2,
            "role": role,
            "model_id": model_id,
            "revision": revision,
            "resolved_revision": revision,
            "runtime": runtime,
            "verification": verification,
            "files": [
                {**entry, "size_bytes": (directory / entry["path"]).stat().st_size}
                for entry in file_inventory(directory)
            ],
        }
        (directory / "model-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    scheme = load_preparation_scheme()
    platform = worker.runtime_target()
    manifest = {
        **scheme,
        "schema_version": 2,
        "index_version": "unit-1",
        "document": {"id": "manual", "title": "測試手冊", "version": "v1", "source_sha256": "0" * 64},
        "engine": {"name": "chromadb", "version": version("chromadb"), "collection": "manual"},
        "producer": platform,
        "validated_targets": [platform],
        "snapshot_complete": True,
        "chunk_count": 1,
        "files": file_inventory(package / "chroma"),
        "embedding": {**scheme["embedding"], **runtime, "files": file_inventory(model)},
        "reranking": {**scheme["reranking"], **runtime, "files": file_inventory(reranker)},
        "reference": {"query": "參考問題", "embedding": vector.tolist()},
    }
    records = [
        {
            "chunk_id": "first",
            "document_id": "manual",
            "document_version": "v1",
            "start": 0,
            "end": 2400,
            "line_start": 1,
            "line_end": 1,
            "text": "原文" * 1200,
            "headings": [],
            "aliases": [],
            "context": "manual.txt",
            "alias_context": "",
            "model_text": "脈絡：manual.txt\n原文：\n" + "原文" * 1200,
        }
    ]
    write_retrieval_assets(package, manifest, records)
    collection.get.return_value["metadatas"][0]["locator"] = "L1-L1; chars[0,2400)"
    worker.DocumentReranker = MagicMock()
    worker.DocumentReranker.return_value.score_passages.side_effect = lambda question, passages: [
        (ordinal, 4.5, text, False) for ordinal, (_model_text, text) in enumerate(passages)
    ]
    yield SimpleNamespace(
        worker=worker,
        package=package,
        model=model,
        reranker=reranker,
        records=records,
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
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    result = index.query("問題")
    assert result["document"]["title"] == "測試手冊"
    assert len(result["passages"][0]["text"]) == 2000
    assert result["passages"][0]["truncated"] is True
    assert result["passages"][0]["locator"] == "L1-L1; chars[0,2000)"
    assert Path(fixture.chroma.PersistentClient.call_args.kwargs["path"]) != fixture.package / "chroma"
    assert fixture.client.get_collection.call_args.kwargs["embedding_function"] is None
    fixture.collection.query.assert_not_called()
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
        fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
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
        fixture.worker.DocumentIndex(fixture.package, fixture.model / "missing", fixture.work, fixture.reranker)
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
    with pytest.raises(ValueError):
        fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    fixture.sentence.SentenceTransformer.assert_not_called()


def test_low_relevance_does_not_fabricate_evidence(document_index) -> None:
    """A distance above the calibrated limit yields a distinct no-evidence outcome."""
    fixture = document_index
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    fixture.sentence.SentenceTransformer.return_value.encode.side_effect = lambda queries, **kwargs: np.array(
        [[0.0, 1.0] + [0.0] * 1022 for _ in queries], dtype=np.float32
    )
    assert index.query("問題") == {"error": "document_no_evidence"}


def test_three_passages_have_stable_ties_and_an_explicit_query_limit(document_index) -> None:
    """Multiple candidates remain bounded and equal distances use stable passage identifiers."""
    fixture = document_index
    vector = fixture.collection.get.return_value["embeddings"][0]
    rows = []
    for position, (identifier, text) in enumerate((("b", "乙"), ("a", "甲"), ("c", "丙"))):
        rows.append(
            {
                **fixture.records[0],
                "chunk_id": identifier,
                "text": text,
                "start": position,
                "end": position + 1,
                "model_text": "脈絡：manual.txt\n原文：\n" + text,
            }
        )
    fixture.manifest["chunk_count"] = 3
    write_retrieval_assets(fixture.package, fixture.manifest, rows)
    fixture.collection.count.return_value = 3
    fixture.collection.get.return_value = {
        "ids": [row["chunk_id"] for row in rows],
        "documents": [row["text"] for row in rows],
        "embeddings": [vector] * 3,
        "metadatas": [
            {"document_id": "manual", "document_version": "v1", "locator": f"L1-L1; chars[{position},{position + 1})"}
            for position in range(3)
        ],
    }
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    result = index.query("問題")
    assert [passage["chunk_id"] for passage in result["passages"]] == ["a", "b", "c"]
    fixture.collection.query.assert_not_called()


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
        fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    fixture.client.create_collection.assert_not_called()


def test_worker_ready_identity_matches_query_identity(document_index, monkeypatch) -> None:
    """The private ready handshake and query results use the same public source identity."""
    fixture = document_index
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
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
    first = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    assert first.query("問題")["document"]["version"] == "v1"
    fixture.manifest["document"]["version"] = "v2"
    fixture.manifest["index_version"] = "unit-2"
    (fixture.package / "manifest.json").write_text(json.dumps(fixture.manifest), encoding="utf-8")
    fixture.collection.get.return_value["metadatas"][0]["document_version"] = "v2"
    fixture.records[0]["document_version"] = "v2"
    write_retrieval_assets(fixture.package, fixture.manifest, fixture.records)
    replacement = fixture.worker.DocumentIndex(
        fixture.package, fixture.model, fixture.work / "replacement", fixture.reranker
    )
    result = replacement.query("問題")
    assert result["document"]["version"] == "v2"
    assert result["index_version"] == "unit-2"
    assert first.identity["version"] == "v1"


def test_external_prebuilt_snapshot_integrity(tmp_path: Path) -> None:
    """Opt in to real snapshot verification without creating or rebuilding any index."""
    package = os.environ.get("RAG_ACCEPTANCE_PACKAGE")
    model = os.environ.get("RAG_ACCEPTANCE_MODEL")
    reranker = os.environ.get("RAG_ACCEPTANCE_RERANKER")
    if not package or not model or not reranker or os.environ.get("RUN_DOCUMENT_SNAPSHOT_ACCEPTANCE") != "1":
        pytest.skip("Explicit real snapshot opt-in and both role models are required")
    script = """
import os, json, hashlib
from pathlib import Path
from reachy_mini_conversation_app.document_worker import DocumentIndex
package, model, work = (Path(os.environ[key]) for key in
    ("RAG_ACCEPTANCE_PACKAGE", "RAG_ACCEPTANCE_MODEL", "RAG_ACCEPTANCE_WORK"))
def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}
import torch
torch.set_num_threads(2)
torch.set_num_interop_threads(1)
before = hashes(package)
manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
index = DocumentIndex(package, model, work, Path(os.environ["RAG_ACCEPTANCE_RERANKER"]))
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
index.client.close()
closed = hashes(work / "chroma")
for path, digest in snapshot_before.items():
    if not Path(path).name.startswith("chroma.sqlite3"):
        assert closed[path] == digest
import chromadb
from chromadb.config import Settings
opened = chromadb.PersistentClient(path=str(work / "chroma"), settings=Settings(migrations="validate", anonymized_telemetry=False, allow_reset=False))
try:
    collection = opened.get_collection(manifest["engine"]["collection"], embedding_function=None)
    reopened_rows = collection.get(include=["documents", "metadatas", "embeddings"])
    for field in ("ids", "documents", "metadatas"):
        assert reopened_rows[field] == rows_before[field]
    assert np.array_equal(reopened_rows["embeddings"], rows_before["embeddings"])
finally:
    opened.close()
for path, digest in closed.items():
    if not Path(path).name.startswith("chroma.sqlite3"):
        assert hashes(work / "chroma")[path] == digest
assert before == hashes(package)
import shutil
from reachy_mini_conversation_app.document_worker import LegacyDocumentPackageError
legacy = work.parent / ("legacy-" + work.name)
shutil.copytree(package, legacy)
(legacy / "manifest.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
legacy_before = hashes(legacy)
legacy_rejected = False
try:
    DocumentIndex(legacy, model, work.parent / "legacy-work", Path(os.environ["RAG_ACCEPTANCE_RERANKER"]))
except LegacyDocumentPackageError:
    legacy_rejected = True
assert legacy_rejected, "Legacy package was accepted"
assert legacy_before == hashes(legacy)
assert before == hashes(package)
"""
    environment = dict(
        os.environ,
        RAG_ACCEPTANCE_WORK=str(tmp_path / "work"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        ANONYMIZED_TELEMETRY="False",
        REACHY_MINI_SKIP_DOTENV="1",
    )
    for ordinal in range(2):
        environment["RAG_ACCEPTANCE_WORK"] = str(tmp_path / f"work-{ordinal}")
        result = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True, timeout=300)
        assert result.returncode == 0, (
            "Real snapshot integrity verification failed; inspect locally without publishing content"
        )


@pytest.mark.parametrize("bad_top", [True, False])
def test_distance_is_applied_after_rerank_and_budget_without_refilling(document_index, bad_top: bool) -> None:
    """An over-distance winner refuses everything; removed extras never release budget for a refill."""
    fixture = document_index
    rows = []
    for position, (identifier, character) in enumerate((("a", "甲"), ("b", "乙"), ("c", "丙"), ("d", "丁"))):
        text = character * 1000
        rows.append(
            {
                **fixture.records[0],
                "chunk_id": identifier,
                "start": position * 1000,
                "end": (position + 1) * 1000,
                "text": text,
                "model_text": "脈絡：manual.txt\n原文：\n" + text,
            }
        )
    fixture.manifest["chunk_count"] = 4
    write_retrieval_assets(fixture.package, fixture.manifest, rows)
    fixture.collection.count.return_value = 4
    near = np.array([1.0] + [0.0] * 1023, dtype=np.float32)
    far = np.array([0.4, float(np.sqrt(0.84))] + [0.0] * 1022, dtype=np.float32)
    fixture.collection.get.return_value = {
        "ids": [row["chunk_id"] for row in rows],
        "documents": [row["text"] for row in rows],
        "embeddings": [far if bad_top else near, near if bad_top else far, near, near],
        "metadatas": [
            {
                "document_id": "manual",
                "document_version": "v1",
                "locator": f"L1-L1; chars[{position * 1000},{(position + 1) * 1000})",
            }
            for position in range(4)
        ],
    }

    def score(question, passages):
        return [
            (ordinal, {"甲": 9.0, "乙": 8.0, "丙": 7.0, "丁": 6.0}[text[0]], text, False)
            for ordinal, (_model_text, text) in enumerate(passages)
        ]

    fixture.worker.DocumentReranker.return_value.score_passages.side_effect = score
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    result = index.query("問題")
    if bad_top:
        assert result == {"error": "document_no_evidence"}
    else:
        assert [passage["chunk_id"] for passage in result["passages"]] == ["a"]
        assert len(result["passages"][0]["text"]) == 1000
    fixture.collection.query.assert_not_called()
    fixture.worker.DocumentReranker.return_value.score_passages.assert_called_once()


@pytest.mark.parametrize("header,legacy", [(1, True), (True, False), (1.0, False), ("1", False)])
def test_only_an_integer_v1_header_is_classified_as_legacy(document_index, header, legacy: bool) -> None:
    """The private legacy reason never comes from a guessed or malformed package version."""
    fixture = document_index
    (fixture.package / "manifest.json").write_text(json.dumps({"schema_version": header}), encoding="utf-8")
    with pytest.raises(ValueError) as failure:
        fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    assert isinstance(failure.value, fixture.worker.LegacyDocumentPackageError) is legacy
    fixture.chroma.PersistentClient.assert_not_called()


@pytest.mark.parametrize("fault", ["length_bool", "df_float", "model_text", "line_bool"])
def test_prebuilt_semantic_corruption_is_rejected_before_engine_open(document_index, fault: str) -> None:
    """Rehashing damaged assets cannot hide inconsistent lexical statistics or source mappings."""
    from reachy_mini_conversation_app.document_assets import file_inventory

    fixture = document_index
    directory = fixture.package / "retrieval"
    if fault in ("length_bool", "df_float"):
        stats = json.loads((directory / "bm25.json").read_text(encoding="utf-8"))
        if fault == "length_bool":
            stats["document_lengths"][0] = True
        else:
            term = next(iter(stats["document_frequencies"]))
            stats["document_frequencies"][term] = float(stats["document_frequencies"][term])
        (directory / "bm25.json").write_text(json.dumps(stats), encoding="utf-8")
    else:
        row = fixture.records[0]
        row["model_text" if fault == "model_text" else "line_start"] = "unrelated" if fault == "model_text" else True
        (directory / "chunks.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    fixture.manifest["assets"] = {"files": file_inventory(directory)}
    (fixture.package / "manifest.json").write_text(json.dumps(fixture.manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    fixture.chroma.PersistentClient.assert_not_called()


@pytest.mark.parametrize("logit,accepted", [(3.486859679222107, True), (3.4868594, False), (-9.0, False)])
def test_minimum_raw_logit_boundary_is_not_a_probability(document_index, logit: float, accepted: bool) -> None:
    """The fixed Identity cutoff includes equality and rejects lower raw scores."""
    fixture = document_index
    fixture.worker.DocumentReranker.return_value.score_passages.side_effect = lambda question, passages: [
        (ordinal, logit, text, False) for ordinal, (_model_text, text) in enumerate(passages)
    ]
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    result = index.query("問題")
    assert (result.get("status") == "ok") is accepted
    if not accepted:
        assert result == {"error": "document_no_evidence"}


def test_reranker_receives_at_most_five_whole_candidates(document_index) -> None:
    """Fusion limits complete parents before scoring and never expands them into short windows."""
    fixture = document_index
    records = []
    for position, (identifier, text) in enumerate(zip("abcdef", "甲乙丙丁戊己", strict=True)):
        records.append(
            {
                **fixture.records[0],
                "chunk_id": identifier,
                "text": text,
                "start": position,
                "end": position + 1,
                "model_text": "脈絡：manual.txt\n原文：\n" + text,
            }
        )
    fixture.manifest["chunk_count"] = 6
    write_retrieval_assets(fixture.package, fixture.manifest, records)
    fixture.collection.count.return_value = 6
    fixture.collection.get.return_value = {
        "ids": [row["chunk_id"] for row in records],
        "documents": [row["text"] for row in records],
        "embeddings": [np.array([1.0] + [0.0] * 1023, dtype=np.float32)] * 6,
        "metadatas": [
            {"document_id": "manual", "document_version": "v1", "locator": f"L1-L1; chars[{position},{position + 1})"}
            for position in range(6)
        ],
    }
    index = fixture.worker.DocumentIndex(fixture.package, fixture.model, fixture.work, fixture.reranker)
    result = index.query("問題")
    assert [passage["chunk_id"] for passage in result["passages"]] == ["a", "b", "c"]
    scorer = fixture.worker.DocumentReranker.return_value.score_passages
    assert scorer.call_args.args == ("問題", [(row["model_text"], row["text"]) for row in records[:5]])


@pytest.mark.parametrize("legacy", [False, True])
def test_worker_initialization_failure_keeps_reason_private(document_index, monkeypatch, legacy: bool) -> None:
    """Only the explicit legacy exception adds the allowlisted private reason."""
    worker = document_index.worker
    error = worker.LegacyDocumentPackageError("private-sentinel") if legacy else ValueError("private-sentinel")
    monkeypatch.setattr(worker, "DocumentIndex", MagicMock(side_effect=error))
    for key in ("INDEX", "MODEL", "WORK", "RERANKER"):
        monkeypatch.setenv(f"REACHY_MINI_DOCUMENT_{key}_PATH", "unused")
    messages = []
    monkeypatch.setattr(worker, "_emit", messages.append)
    assert worker.main() == 1
    assert messages == [
        {"type": "failure", "error": "document_unavailable", **({"reason": "legacy_package"} if legacy else {})}
    ]
