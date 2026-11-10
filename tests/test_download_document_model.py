import os
import sys
import json
import hashlib
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest
from httpx import ConnectError

from reachy_mini_conversation_app import download_document_model as download
from reachy_mini_conversation_app.document_assets import (
    PAYLOAD_FILES,
    MODEL_REVISION,
    RERANKER_REVISION,
    RERANKER_PAYLOAD_FILES,
    file_inventory,
)


def test_download_help_does_not_import_inference_or_configuration() -> None:
    """The lightweight entry point can explain setup without loading robot or inference modules."""
    command = """
import sys
from reachy_mini_conversation_app.download_document_model import main
try:
    main(["--help"])
except SystemExit as error:
    assert error.code == 0
assert not {"torch", "chromadb", "sentence_transformers", "reachy_mini_conversation_app.config"}.intersection(sys.modules)
"""
    subprocess.run([sys.executable, "-c", command], check=True, capture_output=True)


def test_floating_revision_is_rejected_before_network() -> None:
    """An unpinned revision cannot reach Hub preflight or create asset directories."""
    command = """
from reachy_mini_conversation_app.download_document_model import main
assert main(["--role", "embedding", "--revision", "main"]) == 2
"""
    subprocess.run([sys.executable, "-c", command], check=True, capture_output=True)


@pytest.mark.parametrize("role", ["embedding", "reranker"])
def test_download_validates_then_reuses_the_same_complete_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    """Anonymous allowlisted transport and worker validation precede publication and zero-network reuse."""
    revision = MODEL_REVISION if role == "embedding" else RERANKER_REVISION
    model_id = "BAAI/bge-m3" if role == "embedding" else "BAAI/bge-reranker-base"
    names = PAYLOAD_FILES if role == "embedding" else RERANKER_PAYLOAD_FILES
    payloads = dict.fromkeys(names, b"synthetic safe payload, never loaded")
    payloads["modules.json"] = json.dumps([{"path": ""}, {"path": "1_Pooling"}, {"path": "2_Normalize"}]).encode()
    payloads["1_Pooling/config.json"] = b'{"pooling_mode_cls_token":true}'
    payloads["sentence_bert_config.json"] = b'{"max_seq_length":8192}'
    if role == "reranker":
        payloads = {name: payloads[name] for name in names}
        payloads["config.json"] = (
            b'{"model_type":"xlm-roberta","architectures":["XLMRobertaForSequenceClassification"]}'
        )
    requests: list[str] = []

    def fake_api(**kwargs):
        assert kwargs == {"endpoint": "https://huggingface.co", "token": False}
        requests.append("metadata")
        return SimpleNamespace(
            model_info=lambda *args, **options: SimpleNamespace(
                sha=revision,
                siblings=[
                    SimpleNamespace(
                        rfilename=name,
                        size=len(content),
                        blob_id=None,
                        lfs=SimpleNamespace(sha256=hashlib.sha256(content).hexdigest()),
                    )
                    for name, content in payloads.items()
                ],
            )
        )

    def provide_file(repo_id, filename, **kwargs):
        assert repo_id == model_id and kwargs["token"] is False and kwargs["revision"] == revision
        assert kwargs["endpoint"] == "https://huggingface.co"
        path = kwargs["local_dir"] / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payloads[filename])
        requests.append(filename)
        return str(path)

    def fake_snapshot(repo_id, **kwargs):
        assert kwargs.pop("allow_patterns") == list(names)
        for name in names:
            provide_file(repo_id, name, **kwargs)

    def fake_worker(request, operation):
        stage = operation.stage
        receipt = {
            "schema_version": 2,
            "role": role,
            "model_id": model_id,
            "revision": revision,
            "resolved_revision": revision,
            "files": [
                {**entry, "size_bytes": (stage / entry["path"]).stat().st_size} for entry in file_inventory(stage)
            ],
            "runtime": {
                "sentence_transformers_version": "6.2.0",
                "torch_version": "2.15.0+cpu",
                "transformers_version": "5.21.0",
            },
            "verification": {
                "kind": "embedding",
                "device": "cpu",
                "precision": "float32",
                "query": "這份文件主要說明什麼？",
                "embedding": [1.0] + [0.0] * 1023,
            },
        }
        if role == "reranker":
            receipt["verification"] = {
                "kind": "reranker",
                "device": "cpu",
                "precision": "float32",
                "query": "這份文件主要說明什麼？",
                "passage": "這是一份提供文件查詢的示範說明。",
                "logit": -3.25,
                "activation": "identity",
                "max_pair_tokens": 512,
            }
        (stage / "model-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        return {"status": "ok", "verified": True}

    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(download, "HfApi", fake_api)
    monkeypatch.setattr(download, "hf_hub_download", provide_file)
    monkeypatch.setattr(download, "snapshot_download", fake_snapshot)
    monkeypatch.setattr(download, "run_preparation_worker", fake_worker)
    arguments = ["--role", role, "--revision", revision, "--output", str(tmp_path / "model")]
    assert download.main(arguments) == 0
    calls = requests.copy()
    assert download.main(arguments) == 0 and requests == calls
    assert (tmp_path / "model/model-receipt.json").exists()
    assert not (tmp_path / ".model.lock").exists()


def test_snapshot_without_safe_weights_is_rejected_before_file_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An immutable but unsupported revision cannot trigger a weight download or fallback."""
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(
        download,
        "HfApi",
        lambda **kwargs: SimpleNamespace(
            model_info=lambda *args, **options: SimpleNamespace(sha=MODEL_REVISION, siblings=[])
        ),
    )
    assert (
        download.main(["--role", "embedding", "--revision", MODEL_REVISION, "--output", str(tmp_path / "model")]) == 3
    )
    assert not (tmp_path / "model").exists()


def test_interrupted_download_preserves_previous_bytes_and_redacts_provider_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A transport failure before publication cannot damage or expose the previous model."""
    destination = tmp_path / "model"
    destination.mkdir()
    (destination / "old").write_bytes(b"old bytes")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(
        download,
        "HfApi",
        lambda **kwargs: SimpleNamespace(
            model_info=lambda *args, **options: SimpleNamespace(
                sha=MODEL_REVISION, siblings=[SimpleNamespace(rfilename=name) for name in PAYLOAD_FILES]
            )
        ),
    )

    def fail_transport(*args, **kwargs):
        raise ConnectError("private-provider-body-sentinel")

    monkeypatch.setattr(download, "hf_hub_download", fail_transport)
    assert (
        download.main(["--role", "embedding", "--revision", MODEL_REVISION, "--output", str(destination), "--replace"])
        == 5
    )
    assert (destination / "old").read_bytes() == b"old bytes"
    assert "private-provider-body-sentinel" not in capsys.readouterr().out + caplog.text
    assert not (tmp_path / ".model.lock").exists()


def test_source_checkout_default_is_independent_of_working_directory(tmp_path: Path) -> None:
    """A public CLI launched elsewhere still discovers the same source checkout."""
    command = "from reachy_mini_conversation_app.document_assets import checkout_root; print(checkout_root())"
    outputs = [
        subprocess.check_output([sys.executable, "-c", command], cwd=directory, text=True).strip()
        for directory in [tmp_path, Path(__file__).resolve().parents[1]]
    ]
    assert outputs[0] == outputs[1] == str(Path(__file__).resolve().parents[1])


@pytest.mark.skipif(os.environ.get("RUN_DOCUMENT_MODEL_ACCEPTANCE") != "1", reason="Explicit approved model download")
@pytest.mark.parametrize("role", ["embedding", "reranker"])
def test_approved_snapshot_loads_offline_and_reuses_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    """A deployment-approved immutable snapshot must pass the actual CPU worker before reuse."""
    revision = MODEL_REVISION if role == "embedding" else RERANKER_REVISION
    arguments = ["--role", role, "--revision", revision, "--output", str(tmp_path / "model")]
    assert download.main(arguments) == 0
    before = file_inventory(tmp_path / "model")

    def unexpected_network(**kwargs):
        pytest.fail("A complete model reuse attempted metadata access")

    monkeypatch.setattr(download, "HfApi", unexpected_network)
    assert download.main(arguments) == 0
    assert file_inventory(tmp_path / "model") == before


@pytest.mark.parametrize("role,revision", [("embedding", "a" * 40), ("reranker", MODEL_REVISION)])
def test_wrong_role_revision_fails_before_any_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, revision: str
) -> None:
    """A valid-looking SHA from the wrong role never reaches the public hub."""

    def unexpected_transport(**kwargs):
        pytest.fail("Invalid fixed role/version reached transport")

    monkeypatch.setattr(download, "HfApi", unexpected_transport)
    assert download.main(["--role", role, "--revision", revision, "--output", str(tmp_path / "model")]) == 3
    assert not (tmp_path / "model").exists()
