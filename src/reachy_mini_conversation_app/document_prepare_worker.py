import sys
import json
import hashlib
import logging
from pathlib import Path
from collections import Counter
from dataclasses import asdict
from importlib.metadata import version

import torch
import chromadb
from chromadb.config import Settings
from chromadb.api.client import Client
from chromadb.api.models.Collection import Collection

from reachy_mini_conversation_app.document_model import DocumentModel, DocumentReranker, object_value
from reachy_mini_conversation_app.document_assets import (
    MODEL_ID,
    RERANKER_ID,
    PAYLOAD_FILES,
    MODEL_REVISION,
    REFERENCE_QUERY,
    REFERENCE_PASSAGE,
    RERANKER_REVISION,
    RERANKER_PAYLOAD_FILES,
    PreparationError,
    read_object,
    parse_object,
    write_object,
    lexical_terms,
    file_inventory,
    source_identity,
    validate_receipt,
    load_preparation_scheme,
    validate_preparation_request,
)
from reachy_mini_conversation_app.document_worker import DocumentIndex, runtime_target
from reachy_mini_conversation_app.build_document_package import source_chunks


logger = logging.getLogger(__name__)


def verify_model(directory: Path, revision: str, role: str) -> dict[str, object]:
    """Verify a downloaded safe snapshot and write its receipt inside the private candidate."""
    if role not in ("embedding", "reranker"):
        raise PreparationError("invalid_arguments", 2)
    embedding = role == "embedding"
    if revision != (MODEL_REVISION if embedding else RERANKER_REVISION):
        raise PreparationError("model_incompatible", 3)
    before = file_inventory(directory)
    payload_files = PAYLOAD_FILES if embedding else RERANKER_PAYLOAD_FILES
    if {entry["path"] for entry in before} != set(payload_files):
        raise PreparationError("model_incompatible", 3)
    runtime = {
        "sentence_transformers_version": version("sentence-transformers"),
        "torch_version": version("torch"),
        "transformers_version": version("transformers"),
    }
    verification: dict[str, object] = {
        "kind": role,
        "query": REFERENCE_QUERY,
        "device": "cpu",
        "precision": "float32",
    }
    if embedding:
        model = DocumentModel(directory, {"files": before}, None)
        verification["embedding"] = model.encode(REFERENCE_QUERY).tolist()
    else:
        reranker = DocumentReranker(directory, {"files": before})
        verification.update(
            passage=REFERENCE_PASSAGE,
            logit=reranker.score(REFERENCE_QUERY, [REFERENCE_PASSAGE])[0],
            activation="identity",
            max_pair_tokens=512,
        )
    if file_inventory(directory) != before:
        raise PreparationError("model_incompatible", 3)
    write_object(
        directory / "model-receipt.json",
        {
            "schema_version": 2,
            "role": role,
            "model_id": MODEL_ID if embedding else RERANKER_ID,
            "revision": revision,
            "resolved_revision": revision,
            "files": [{**entry, "size_bytes": (directory / str(entry["path"])).stat().st_size} for entry in before],
            "runtime": runtime,
            "verification": verification,
        },
    )
    return {"status": "ok", "verified": True}


def produce_package(request: dict[str, object]) -> dict[str, object]:
    """Persist original source passages using the verified public Chroma operation sequence."""
    source, model_path, stage = (Path(str(request[key])) for key in ("source", "model", "stage"))
    if request.get("scheme") != "bge-base-final-selection-20261109" or request.get("policy") != "chapter-source-v1":
        raise PreparationError("invalid_scheme", 2)
    reranker_path = Path(str(request["reranker_model"]))
    reranker_receipt = validate_receipt(reranker_path)
    if reranker_receipt["role"] != "reranker":
        raise PreparationError("model_incompatible", 3)
    reranker_inventory = file_inventory(reranker_path)
    receipt = validate_receipt(model_path)
    if receipt["role"] != "embedding":
        raise PreparationError("model_incompatible", 3)
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
    alias_value: dict[str, object] | None = None
    alias_record: dict[str, object] | None = None
    if "aliases" in request:
        alias_path = Path(str(request["aliases"]))
        alias_identity = source_identity(alias_path)
        with alias_path.open("rb") as stream:
            alias_bytes = stream.read(16 * 1024 * 1024 + 1)
        if source_identity(alias_path) != alias_identity:
            raise PreparationError("invalid_aliases", 2)
        try:
            alias_value = parse_object(alias_bytes)
        except (UnicodeError, ValueError, PreparationError) as error:
            logger.warning("Invalid alias source: %s", type(error).__name__)
            raise PreparationError("invalid_aliases", 2) from None
        alias_record = {"identity": alias_identity, "sha256": hashlib.sha256(alias_bytes).hexdigest()}
    chunks = source_chunks(
        text,
        model,
        str(request["document_id"]),
        str(request["document_version"]),
        digest,
        source_name=source.name,
        markdown=source.suffix.lower() != ".txt",
        aliases=alias_value,
    )
    retrieval_directory = stage / "retrieval"
    retrieval_directory.mkdir()
    with (retrieval_directory / "chunks.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for chunk in chunks:
            stream.write(json.dumps(asdict(chunk), ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    frequencies = [dict(Counter(lexical_terms(chunk.model_text))) for chunk in chunks]
    lengths = [sum(frequency.values()) for frequency in frequencies]
    document_frequencies: Counter[str] = Counter()
    for frequency in frequencies:
        document_frequencies.update(frequency.keys())
    write_object(
        retrieval_directory / "bm25.json",
        {
            "version": "bm25-prebuilt-v1",
            "chunk_ids": [chunk.chunk_id for chunk in chunks],
            "term_frequencies": frequencies,
            "document_lengths": lengths,
            "document_frequencies": dict(document_frequencies),
            "average_document_length": sum(lengths) / len(chunks),
        },
    )
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
                embeddings=[model.encode(chunk.model_text).tolist() for chunk in batch],
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
            embeddings=[model.encode(last.model_text).tolist()],
        )
        rows_digest = collection_digest(collection)
    finally:
        client.close()
    if file_inventory(model_path) != inventory or file_inventory(reranker_path) != reranker_inventory:
        raise PreparationError("model_incompatible", 3)
    engine_files = file_inventory(stage / "chroma")
    if any(str(entry["path"]).endswith(("-wal", "-shm", "-journal")) for entry in engine_files):
        raise PreparationError("snapshot_incomplete", 6)
    scheme = load_preparation_scheme()
    embedding = {**object_value(scheme["embedding"]), "files": inventory, **runtime}
    reranking = {
        **object_value(scheme["reranking"]),
        "files": reranker_inventory,
        **object_value(reranker_receipt["runtime"]),
    }
    manifest = {
        **scheme,
        "schema_version": 2,
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
        "reranking": reranking,
        "assets": {"files": file_inventory(retrieval_directory)},
        "reference": {key: object_value(receipt["verification"])[key] for key in ("query", "embedding")},
    }
    write_object(stage / "manifest.json", manifest)
    record = stage.parent / (stage.name.split(".stage-")[0] + ".lock") / "source.json"
    write_object(
        record,
        {
            "source_sha256": digest,
            "identity": initial,
            "policy": "chapter-source-v1",
            "aliases": alias_record,
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
    reranker = Path(str(request["reranker_model"]))
    model_before, reranker_before = file_inventory(model), file_inventory(reranker)
    index = DocumentIndex(stage, model, work, reranker_path=reranker)
    client = index.client
    if not isinstance(client, Client):
        raise PreparationError("snapshot_incomplete", 6)
    try:
        if collection_digest(index.collection) != record["rows_sha256"]:
            raise PreparationError("snapshot_incomplete", 6)
        result = index.query(REFERENCE_QUERY)
        if result.get("error") not in (None, "document_no_evidence"):
            raise PreparationError("validation_failed", 6)
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
    if file_inventory(model) != model_before or file_inventory(reranker) != reranker_before:
        raise PreparationError("model_incompatible", 3)
    alias_record = record.get("aliases")
    if alias_record is not None:
        saved = object_value(alias_record)
        alias_path = Path(str(request["aliases"]))
        alias_initial = source_identity(alias_path)
        with alias_path.open("rb") as stream:
            alias_digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if (
            alias_initial != source_identity(alias_path)
            or alias_initial != saved["identity"]
            or alias_digest != saved["sha256"]
        ):
            raise PreparationError("invalid_aliases", 2)
    return {"status": "ok", "verified": True, "source_sha256": digest}


def main() -> int:
    """Serve exactly one bounded preparation request without returning source content."""
    try:
        payload = sys.stdin.buffer.read(65537)
        if len(payload) > 65536:
            raise PreparationError("invalid_arguments", 2)
        request = object_value(json.loads(payload))
        validate_preparation_request(request)
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        if request.get("operation") == "produce":
            result = produce_package(request)
        elif request.get("operation") == "verify-package":
            result = verify_package(request)
        elif request.get("operation") == "verify-model":
            result = verify_model(Path(str(request["model"])), str(request["revision"]), str(request["role"]))
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
