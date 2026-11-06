import sys
import json
import hashlib
import logging
from pathlib import Path
from importlib.metadata import version

import chromadb
from chromadb.config import Settings
from chromadb.api.client import Client
from chromadb.api.models.Collection import Collection

from reachy_mini_conversation_app.document_model import DocumentModel, object_value
from reachy_mini_conversation_app.document_assets import (
    MODEL_ID,
    PAYLOAD_FILES,
    REFERENCE_QUERY,
    PreparationError,
    read_object,
    write_object,
    file_inventory,
    source_identity,
    validate_receipt,
)
from reachy_mini_conversation_app.document_worker import DocumentIndex, runtime_target
from reachy_mini_conversation_app.build_document_package import source_chunks


logger = logging.getLogger(__name__)


def verify_model(directory: Path, revision: str) -> dict[str, object]:
    """Verify a downloaded safe snapshot and write its receipt inside the private candidate."""
    before = file_inventory(directory)
    if {entry["path"] for entry in before} != set(PAYLOAD_FILES):
        raise PreparationError("model_incompatible", 3)
    runtime = {
        "sentence_transformers_version": version("sentence-transformers"),
        "torch_version": version("torch"),
        "transformers_version": version("transformers"),
    }
    model = DocumentModel(directory, {"files": before}, None)
    reference = model.encode(REFERENCE_QUERY).tolist()
    if file_inventory(directory) != before:
        raise PreparationError("model_incompatible", 3)
    write_object(
        directory / "model-receipt.json",
        {
            "schema_version": 1,
            "model_id": MODEL_ID,
            "revision": revision,
            "resolved_revision": revision,
            "files": [{**entry, "size_bytes": (directory / str(entry["path"])).stat().st_size} for entry in before],
            "runtime": runtime,
            "verification": {"query": REFERENCE_QUERY, "embedding": reference},
        },
    )
    return {"status": "ok", "verified": True}


def produce_package(request: dict[str, object]) -> dict[str, object]:
    """Persist original source passages using the verified public Chroma operation sequence."""
    source, model_path, stage = (Path(str(request[key])) for key in ("source", "model", "stage"))
    receipt = validate_receipt(model_path)
    runtime = object_value(receipt["runtime"])
    for package, key in (
        ("sentence-transformers", "sentence_transformers_version"),
        ("torch", "torch_version"),
        ("transformers", "transformers_version"),
    ):
        if version(package) != runtime[key]:
            raise PreparationError("model_incompatible", 3)
    initial = source_identity(source)
    source_bytes = source.read_bytes()
    if source_identity(source) != initial:
        raise PreparationError("invalid_document", 2)
    try:
        text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        logger.warning("Document source is not valid UTF-8")
        raise PreparationError("invalid_document", 2) from None
    digest = hashlib.sha256(source_bytes).hexdigest()
    inventory = file_inventory(model_path)
    model = DocumentModel(model_path, {"files": inventory}, object_value(receipt["verification"]))
    chunks = source_chunks(text, model, str(request["document_id"]), str(request["document_version"]), digest)
    client = chromadb.PersistentClient(path=str(stage / "chroma"), settings=Settings(anonymized_telemetry=False))
    if not isinstance(client, Client):
        raise PreparationError("snapshot_incomplete", 6)
    try:
        collection = client.create_collection(
            name="source-document",
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine", "batch_size": 2, "sync_threshold": 2, "num_threads": 2}},
        )
        maximum = client.get_max_batch_size()
        for start in range(0, len(chunks), maximum):
            batch = chunks[start : start + maximum]
            collection.add(
                ids=[chunk.chunk_id for chunk in batch],
                documents=[chunk.text for chunk in batch],
                metadatas=[
                    {
                        "document_id": str(request["document_id"]),
                        "document_version": str(request["document_version"]),
                        "locator": chunk.locator,
                    }
                    for chunk in batch
                ],
                embeddings=[model.encode(chunk.text).tolist() for chunk in batch],
            )
        last = chunks[-1]
        collection.update(
            ids=[last.chunk_id],
            documents=[last.text],
            metadatas=[
                {
                    "document_id": str(request["document_id"]),
                    "document_version": str(request["document_version"]),
                    "locator": last.locator,
                }
            ],
            embeddings=[model.encode(last.text).tolist()],
        )
        rows_digest = collection_digest(collection)
    finally:
        client.close()
    if file_inventory(model_path) != inventory:
        raise PreparationError("model_incompatible", 3)
    engine_files = file_inventory(stage / "chroma")
    if any(str(entry["path"]).endswith(("-wal", "-shm", "-journal")) for entry in engine_files):
        raise PreparationError("snapshot_incomplete", 6)
    embedding = {
        "model_id": MODEL_ID,
        "revision": receipt["revision"],
        "files": inventory,
        **runtime,
        "mode": "dense",
        "dimension": 1024,
        "precision": "float32",
        "pooling": "cls",
        "normalize": True,
        "query_prefix": "",
        "document_prefix": "",
        "max_seq_length": 8192,
        "metric": "cosine",
    }
    write_object(
        stage / "manifest.json",
        {
            "schema_version": 1,
            "index_version": request["index_version"],
            "document": {
                "id": request["document_id"],
                "title": request["title"],
                "version": request["document_version"],
                "source_sha256": digest,
            },
            "engine": {"name": "chromadb", "version": version("chromadb"), "collection": "source-document"},
            "producer": runtime_target(),
            "validated_targets": [runtime_target()],
            "snapshot_complete": True,
            "chunk_count": len(chunks),
            "files": engine_files,
            "embedding": embedding,
            "retrieval": {"max_distance": request["max_distance"]},
            "reference": receipt["verification"],
        },
    )
    record = stage.parent / (stage.name.split(".stage-")[0] + ".lock") / "source.json"
    write_object(
        record,
        {
            "source_sha256": digest,
            "identity": initial,
            "policy": "source-window-v1",
            "rows_sha256": rows_digest,
        },
    )
    return {"status": "ok", "count": len(chunks), "source_sha256": digest}


def collection_digest(collection: Collection) -> str:
    """Hash all logical rows in identifier order without sending contents over IPC."""
    rows: list[tuple[str, object, object, list[float]]] = []
    for start in range(0, collection.count(), 256):
        batch = collection.get(limit=256, offset=start, include=["documents", "metadatas", "embeddings"])
        documents, metadata, vectors = batch["documents"], batch["metadatas"], batch["embeddings"]
        if documents is None or metadata is None or vectors is None:
            raise PreparationError("snapshot_incomplete", 6)
        for identifier, text, labels, vector in zip(batch["ids"], documents, metadata, vectors, strict=True):
            rows.append((identifier, text, labels, vector.tolist()))
    payload = json.dumps(sorted(rows), sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_package(request: dict[str, object]) -> dict[str, object]:
    """Reject fresh-reader rebuilds, logical changes or source mutation before publication."""
    source, model, stage = (Path(str(request[key])) for key in ("source", "model", "stage"))
    before = file_inventory(stage)
    owned_lock = stage.parent / (stage.name.split(".stage-")[0] + ".lock")
    work = owned_lock / "verify-work"
    work.mkdir()
    persistent_before = [entry for entry in file_inventory(stage / "chroma") if entry["path"] != "chroma.sqlite3"]
    record = read_object(owned_lock / "source.json")
    index = DocumentIndex(stage, model, work)
    client = index.client
    if not isinstance(client, Client):
        raise PreparationError("snapshot_incomplete", 6)
    try:
        if collection_digest(index.collection) != record["rows_sha256"]:
            raise PreparationError("snapshot_incomplete", 6)
        index.query(REFERENCE_QUERY)
        if collection_digest(index.collection) != record["rows_sha256"]:
            raise PreparationError("snapshot_incomplete", 6)
    finally:
        client.close()
    reopened = chromadb.PersistentClient(
        path=str(work / "chroma"),
        settings=Settings(migrations="validate", anonymized_telemetry=False, allow_reset=False),
    )
    if not isinstance(reopened, Client):
        raise PreparationError("snapshot_incomplete", 6)
    try:
        if (
            collection_digest(reopened.get_collection("source-document", embedding_function=None))
            != record["rows_sha256"]
        ):
            raise PreparationError("snapshot_incomplete", 6)
    finally:
        reopened.close()
    after = file_inventory(work / "chroma")
    if not persistent_before or [entry for entry in after if entry["path"] != "chroma.sqlite3"] != persistent_before:
        raise PreparationError("snapshot_incomplete", 6)
    if (
        any(str(entry["path"]).endswith(("-wal", "-shm", "-journal")) for entry in after)
        or file_inventory(stage) != before
    ):
        raise PreparationError("snapshot_incomplete", 6)
    initial = source_identity(source)
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    final = source_identity(source)
    if initial != final or final != record["identity"] or digest != record["source_sha256"]:
        raise PreparationError("invalid_document", 2)
    return {"status": "ok", "verified": True, "source_sha256": digest}


def main() -> int:
    """Serve exactly one bounded preparation request without returning source content."""
    try:
        payload = sys.stdin.buffer.read(65537)
        if len(payload) > 65536:
            raise PreparationError("invalid_arguments", 2)
        request = object_value(json.loads(payload))
        if request.get("operation") == "produce":
            result = produce_package(request)
        elif request.get("operation") == "verify-package":
            result = verify_package(request)
        elif request.get("operation") == "verify-model":
            result = verify_model(Path(str(request["model"])), str(request["revision"]))
        else:
            raise PreparationError("invalid_arguments", 2)
    except PreparationError as error:
        logger.warning("Preparation outcome: %s", error.code)
        sys.stdout.write(json.dumps({"status": "failed", "code": error.code}))
        return error.exit_code
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as error:
        logger.warning("Preparation failed: %s", type(error).__name__)
        sys.stdout.write(json.dumps({"status": "failed", "code": "validation_failed"}))
        return 1
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
