import os
import sys
import json
import shutil
import hashlib
import subprocess
from pathlib import Path

import pytest

from reachy_mini_conversation_app.build_document_package import main as build_main


CHROMA_PROBE = """
import sys
import json
from pathlib import Path

import chromadb
from chromadb.config import Settings

mode, directory, count_text, update_text = sys.argv[1:]
count = int(count_text)
client = chromadb.PersistentClient(
    path=directory,
    settings=Settings(anonymized_telemetry=False, migrations="apply" if mode == "produce" else "validate"),
)
if mode == "produce":
    collection = client.create_collection(
        name="probe-document", embedding_function=None,
        configuration={"hnsw": {"space": "cosine", "batch_size": 2, "sync_threshold": 2, "num_threads": 2}},
    )
    maximum = client.get_max_batch_size()
    if count == 0:
        count = maximum + 1
    for start in range(0, count, maximum):
        stop = min(start + maximum, count)
        collection.add(
            ids=[f"c-{i:08}" for i in range(start, stop)],
            documents=[f"synthetic passage {i}" for i in range(start, stop)],
            metadatas=[{"document_id": "probe", "document_version": "v1", "locator": f"L{i+1}"} for i in range(start, stop)],
            embeddings=[[1.0] + [0.0] * 1023 for i in range(start, stop)],
        )
    if update_text == "yes":
        collection.update(
            ids=[f"c-{count-1:08}"],
            documents=[f"synthetic passage {count-1}"],
            metadatas=[{"document_id": "probe", "document_version": "v1", "locator": f"L{count}"}],
            embeddings=[[1.0] + [0.0] * 1023],
        )
else:
    collection = client.get_collection(name="probe-document", embedding_function=None)
    assert collection.configuration["hnsw"]["space"] == "cosine"
    assert len(client.list_collections()) == 1
    assert collection.count() == count
    seen = set()
    for start in range(0, count, 256):
        rows = collection.get(limit=256, offset=start, include=["documents", "metadatas", "embeddings"])
        for identifier, text, metadata, vector in zip(
            rows["ids"], rows["documents"], rows["metadatas"], rows["embeddings"], strict=True,
        ):
            position = int(identifier[2:])
            assert identifier not in seen and 0 <= position < count
            seen.add(identifier)
            assert text == f"synthetic passage {position}"
            assert metadata == {"document_id": "probe", "document_version": "v1", "locator": f"L{position+1}"}
            assert vector.tolist() == [1.0] + [0.0] * 1023
    assert len(seen) == count
    matches = collection.query(query_embeddings=[[1.0] + [0.0] * 1023], n_results=1)
    assert len(matches["ids"][0]) == 1 and matches["ids"][0][0] in seen
client.close()
print(json.dumps({"count": count, "mode": mode}))
"""

PACKAGE_PROBE = """
import sys
import json
from pathlib import Path
import numpy as np
from types import ModuleType
sentence = ModuleType("sentence_transformers")
sentence.SentenceTransformer = object
sys.modules["sentence_transformers"] = sentence

def deny_network(event, arguments):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise AssertionError("Offline package probe attempted network access")

sys.addaudithook(deny_network)
from reachy_mini_conversation_app import document_prepare_worker as worker
from reachy_mini_conversation_app import document_worker as reader
from reachy_mini_conversation_app.document_assets import PAYLOAD_FILES

class SyntheticEncoder:
    def __init__(self, *arguments):
        pass
    def encode(self, text):
        return np.array([1.0] + [0.0] * 1023, dtype=np.float32)
    def offsets(self, text):
        return [(i, i+1) for i in range(len(text))]
    def encoded_count(self, text):
        return len(text)+2

worker.DocumentModel = SyntheticEncoder
reader.DocumentModel = SyntheticEncoder
root = Path(sys.argv[2])
request_path = root / "request.json"
if sys.argv[1] == "produce":
    source = root / "source.md"
    source.write_bytes(sys.argv[3].encode("utf-8"))
    model = root / "model"
    model.mkdir()
    for name in PAYLOAD_FILES:
        path = model / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic placeholder, never loaded")
    worker.verify_model(model, "a"*40)
    stage = root / ".package.stage-test"
    stage.mkdir()
    (root / ".package.lock").mkdir()
    request = {"source": str(source), "model": str(model), "stage": str(stage), "document_id": "manual",
        "title": "Synthetic manual", "document_version": "v1", "index_version": "build-1", "max_distance": 0.3}
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result = worker.produce_package(request)
else:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = worker.verify_package(request)
print(json.dumps(result))
"""


def snapshot_inventory(directory: Path) -> dict[str, str]:
    """Hash every persistent file without opening or modifying the database."""
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


@pytest.mark.skipif(os.environ.get("RUN_DOCUMENT_CHROMA_PROBE") != "1", reason="Explicit real Chroma gate")
@pytest.mark.parametrize("count", [1, 2, 3, 5, 0])
@pytest.mark.parametrize("identical_update", [False, True])
def test_real_chroma_snapshot_is_sealed(tmp_path: Path, count: int, identical_update: bool) -> None:
    """A fresh reader must not rebuild any persistent HNSW file, including tiny tails."""
    environment = {
        **os.environ,
        "HF_HUB_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "SKIP_DOTENV": "1",
        "ANONYMIZED_TELEMETRY": "False",
    }
    original, replica = tmp_path / "original", tmp_path / "replica"
    producer = subprocess.run(
        [
            sys.executable,
            "-c",
            CHROMA_PROBE,
            "produce",
            str(original),
            str(count),
            "yes" if identical_update else "no",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    produced_count = json.loads(producer.stdout)["count"]
    before = snapshot_inventory(original)
    assert before and not any(name.endswith(("-wal", "-shm", "-journal")) for name in before)
    shutil.copytree(original, replica)
    assert snapshot_inventory(replica) == before
    subprocess.run(
        [sys.executable, "-c", CHROMA_PROBE, "verify", str(replica), str(produced_count), "no"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    after = snapshot_inventory(replica)
    assert snapshot_inventory(original) == before
    assert not any(name.endswith(("-wal", "-shm", "-journal")) for name in after)
    persistent_before = {name: digest for name, digest in before.items() if name != "chroma.sqlite3"}
    persistent_after = {name: digest for name, digest in after.items() if name != "chroma.sqlite3"}
    assert persistent_before, "No persistent HNSW files were produced"
    if count == 1 and not identical_update:
        assert persistent_after != persistent_before, "The negative control unexpectedly became sealed"
    else:
        assert persistent_after == persistent_before, "Fresh open/query/close changed persistent HNSW files"


@pytest.mark.skipif(os.environ.get("RUN_DOCUMENT_CHROMA_PROBE") != "1", reason="Explicit real Chroma gate")
@pytest.mark.parametrize(
    "source",
    [
        "繁體中文原文。",
        "An English manual.",
        "不可按紅色按鈕。",
        "| 名稱 | 數值 |\r\n| A | 1 |",
        "```python\nprint('do not run')\n```\nhttps://example.invalid",
    ],
    ids=["zh", "en", "negation", "table", "code"],
)
def test_real_package_producer_and_fresh_reader_preserve_source(
    tmp_path: Path, source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthetic inference exercises the real format and engine across independent processes."""
    environment = {**os.environ, "HF_HUB_OFFLINE": "1", "SKIP_DOTENV": "1", "ANONYMIZED_TELEMETRY": "False"}
    produced = subprocess.run(
        [sys.executable, "-c", PACKAGE_PROBE, "produce", str(tmp_path), source],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=True,
        timeout=120,
    )
    assert json.loads(produced.stdout)["count"] >= 1
    before = snapshot_inventory(tmp_path / ".package.stage-test")
    verified = subprocess.run(
        [sys.executable, "-c", PACKAGE_PROBE, "verify", str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=True,
        timeout=120,
    )
    assert json.loads(verified.stdout)["verified"] is True
    assert snapshot_inventory(tmp_path / ".package.stage-test") == before
    assert (tmp_path / "source.md").read_bytes() == source.encode("utf-8")
    if source == "繁體中文原文。":
        work = (tmp_path / ".package.lock/verify-work").resolve()
        assert work.is_relative_to(tmp_path.resolve())
        shutil.rmtree(work)
        (tmp_path / "source.md").write_text("changed synthetic source", encoding="utf-8")
        rejected = subprocess.run(
            [sys.executable, "-c", PACKAGE_PROBE, "verify", str(tmp_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
            timeout=120,
        )
        assert rejected.returncode != 0 and "invalid_document" in rejected.stderr
        assert snapshot_inventory(tmp_path / ".package.stage-test") == before
        (tmp_path / "source.md").write_bytes(source.encode("utf-8"))
        original_popen = subprocess.Popen
        bootstrap = PACKAGE_PROBE.split("root = Path(sys.argv[2])")[0] + "\nraise SystemExit(worker.main())"

        def start_synthetic_worker(command, **kwargs):
            if command[-1] == "reachy_mini_conversation_app.document_prepare_worker":
                command = [sys.executable, "-c", bootstrap]
            return original_popen(command, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", start_synthetic_worker)
        assert (
            build_main(
                [
                    "--input",
                    str(tmp_path / "source.md"),
                    "--model",
                    str(tmp_path / "model"),
                    "--output",
                    str(tmp_path / "cli-package"),
                    "--document-id",
                    "manual",
                    "--title",
                    "Synthetic manual",
                    "--document-version",
                    "v1",
                    "--index-version",
                    "build-1",
                    "--max-distance",
                    "0.3",
                ]
            )
            == 0
        )
        first_manifest = json.loads((tmp_path / ".package.stage-test/manifest.json").read_text(encoding="utf-8"))
        second_manifest = json.loads((tmp_path / "cli-package/manifest.json").read_text(encoding="utf-8"))
        assert first_manifest["document"] == second_manifest["document"]
        assert first_manifest["chunk_count"] == second_manifest["chunk_count"]
        assert not (tmp_path / ".cli-package.lock").exists()
        (tmp_path / "source.md").write_bytes(b"\xffinvalid utf8")
        assert (
            build_main(
                [
                    "--input",
                    str(tmp_path / "source.md"),
                    "--model",
                    str(tmp_path / "model"),
                    "--output",
                    str(tmp_path / "invalid-package"),
                    "--document-id",
                    "manual",
                    "--title",
                    "Synthetic manual",
                    "--document-version",
                    "v1",
                    "--index-version",
                    "build-1",
                    "--max-distance",
                    "0.3",
                ]
            )
            == 2
        )
        assert not (tmp_path / "invalid-package").exists()
