import sys
import json
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest

from reachy_mini_conversation_app.document_assets import (
    PAYLOAD_FILES,
    AssetOperation,
    PreparationError,
    file_inventory,
    validate_paths,
    validate_receipt,
    run_preparation_worker,
)


def test_preparation_directories_are_ignored_without_hiding_product_sources() -> None:
    """Only the two asset destinations and their owned siblings are ignored."""
    repository = Path(__file__).resolve().parents[1]
    ignored = [
        f"external_content/{name}/probe"
        for stem in ("bge-m3-model", "document-package")
        for name in (stem, f".{stem}.stage-operation", f".{stem}.backup-operation", f".{stem}.lock")
    ]
    visible = [
        "src/reachy_mini_conversation_app/document_assets.py",
        "external_content/unrelated/probe",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        input="\0".join([*ignored, *visible]) + "\0",
        text=True,
        capture_output=True,
        cwd=repository,
        check=True,
    )
    assert result.stdout.rstrip("\0").split("\0") == ignored


def test_validated_stage_replaces_destination_and_releases_lock(tmp_path: Path) -> None:
    """Publication replaces the old payload only after an explicitly owned stage is ready."""
    destination = tmp_path / "package"
    destination.mkdir()
    (destination / "old").write_bytes(b"old")
    with AssetOperation(destination, "package", replace=True) as operation:
        (operation.stage / "new").write_bytes(b"new")
        operation.record("validated")
        operation.publish()
        assert operation.published
    assert (destination / "new").read_bytes() == b"new"
    assert not (destination / "old").exists()
    assert not operation.lock.exists()


def test_busy_and_unapproved_replacement_preserve_existing_material(tmp_path: Path) -> None:
    """A competing writer or an unapproved replacement never touches the active payload."""
    destination = tmp_path / "package"
    destination.mkdir()
    (destination / "old").write_bytes(b"old")
    with pytest.raises(PreparationError, match="destination_exists"):
        with AssetOperation(destination, "package", replace=False):
            pytest.fail("Existing destination was accepted")
    with AssetOperation(destination, "package", replace=True) as operation:
        with pytest.raises(PreparationError, match="destination_busy"):
            with AssetOperation(destination, "package", replace=True):
                pytest.fail("Competing writer was accepted")
        assert json.loads((operation.lock / "operation.json").read_text())["phase"] == "preparing"
    assert (destination / "old").read_bytes() == b"old"


def test_overlapping_and_protected_paths_are_rejected(tmp_path: Path) -> None:
    """Unsafe ancestor relationships fail before directories are created."""
    with pytest.raises(PreparationError, match="unsafe_path"):
        validate_paths(tmp_path / "model/output", [tmp_path / "model"])
    with pytest.raises(PreparationError, match="unsafe_path"):
        validate_paths(Path(__file__).resolve().parents[1] / "src", [])


def test_receipt_verifies_all_payload_bytes_and_rejects_tampering(tmp_path: Path) -> None:
    """Matching revision labels cannot hide changed payloads or duplicate inventory paths."""
    for name in PAYLOAD_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"synthetic model payload, never loaded")
    receipt = {
        "schema_version": 1,
        "model_id": "BAAI/bge-m3",
        "revision": "a" * 40,
        "resolved_revision": "a" * 40,
        "files": [
            {**entry, "size_bytes": (tmp_path / str(entry["path"])).stat().st_size}
            for entry in file_inventory(tmp_path)
        ],
        "runtime": {
            "sentence_transformers_version": "6.2.0",
            "torch_version": "2.15.0+cpu",
            "transformers_version": "5.21.0",
        },
        "verification": {"query": "這份文件主要說明什麼？", "embedding": [1.0] + [0.0] * 1023},
    }
    (tmp_path / "model-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    assert validate_receipt(tmp_path)["revision"] == "a" * 40
    (tmp_path / "model.safetensors").write_bytes(b"tampered")
    with pytest.raises(PreparationError, match="model_incompatible"):
        validate_receipt(tmp_path)


def test_failed_second_rename_restores_old_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An ordinary prepublication failure leaves the previous payload in its original location."""
    destination = tmp_path / "package"
    destination.mkdir()
    (destination / "old").write_bytes(b"old")
    original_rename = Path.rename
    with pytest.raises(PermissionError):
        with AssetOperation(destination, "package", replace=True) as operation:
            (operation.stage / "new").write_bytes(b"new")
            operation.record("validated")

            def fail_stage_rename(source: Path, target: Path) -> Path:
                if source == operation.stage:
                    raise PermissionError("synthetic locked stage")
                return original_rename(source, target)

            monkeypatch.setattr(Path, "rename", fail_stage_rename)
            operation.publish()
    assert (destination / "old").read_bytes() == b"old"
    assert not operation.lock.exists()


def test_cleanup_failure_preserves_published_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Postpublication cleanup cannot roll back or report an unpublished candidate."""
    destination = tmp_path / "package"
    destination.mkdir()
    (destination / "old").write_bytes(b"old")
    with pytest.raises(PreparationError, match="cleanup_incomplete") as failure:
        with AssetOperation(destination, "package", replace=True) as operation:
            (operation.stage / "new").write_bytes(b"new")
            operation.record("validated")
            operation.publish()

            def fail_cleanup(path: Path) -> None:
                raise PermissionError("synthetic locked backup")

            monkeypatch.setattr("reachy_mini_conversation_app.document_assets.shutil.rmtree", fail_cleanup)
    assert failure.value.exit_code == 8 and operation.published
    assert (destination / "new").read_bytes() == b"new"
    assert (operation.backup / "old").read_bytes() == b"old"
    assert operation.lock.exists()


@pytest.mark.parametrize("phase", ["preparing", "validating", "validated", "backed_up"])
def test_cancel_before_publication_preserves_old_payload(tmp_path: Path, phase: str) -> None:
    """Cancellation in every prepublication phase restores the old material."""
    destination = tmp_path / "package"
    destination.mkdir()
    (destination / "old").write_bytes(b"old")
    with pytest.raises(KeyboardInterrupt):
        with AssetOperation(destination, "package", replace=True) as operation:
            (operation.stage / "new").write_bytes(b"new")
            if phase == "backed_up":
                destination.rename(operation.backup)
            operation.record(phase)
            raise KeyboardInterrupt
    assert not operation.published and (destination / "old").read_bytes() == b"old"
    assert not operation.lock.exists()


def test_cancel_during_postpublication_cleanup_reports_exit_eight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupted cleanup cannot make the completed publication look cancelled."""
    with pytest.raises(PreparationError, match="cleanup_incomplete") as failure:
        with AssetOperation(tmp_path / "package", "package", replace=False) as operation:
            (operation.stage / "new").write_bytes(b"new")
            operation.record("validated")
            operation.publish()

            def interrupt_cleanup(path: Path) -> None:
                raise KeyboardInterrupt

            monkeypatch.setattr("reachy_mini_conversation_app.document_assets.shutil.rmtree", interrupt_cleanup)
    assert failure.value.exit_code == 8 and operation.published
    assert (operation.destination / "new").read_bytes() == b"new"


def test_failed_phase_record_after_rename_does_not_roll_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The filesystem commit remains authoritative if the published journal update fails."""
    destination = tmp_path / "package"
    with pytest.raises(PreparationError, match="cleanup_incomplete"):
        with AssetOperation(destination, "package", replace=False) as operation:
            (operation.stage / "new").write_bytes(b"new")
            operation.record("validated")
            original_record = operation.record

            def fail_published_record(phase: str) -> None:
                if phase == "published":
                    raise PermissionError("synthetic journal failure")
                original_record(phase)

            monkeypatch.setattr(operation, "record", fail_published_record)
            operation.publish()
    assert operation.published and (destination / "new").read_bytes() == b"new"


def test_an_independent_process_cannot_acquire_owned_destination(tmp_path: Path) -> None:
    """The directory lock excludes another interpreter rather than only another object."""
    import_code = """
import sys
from pathlib import Path
from reachy_mini_conversation_app.document_assets import AssetOperation, PreparationError
try:
    with AssetOperation(Path(sys.argv[1]), "package", True):
        raise AssertionError("Concurrent operation acquired the lock")
except PreparationError as error:
    assert error.code == "destination_busy" and error.exit_code == 4
"""
    with AssetOperation(tmp_path / "package", "package", replace=False) as operation:
        subprocess.run(
            [sys.executable, "-c", import_code, str(operation.destination)], check=True, capture_output=True
        )


def test_worker_pipe_is_summary_only_and_uses_an_isolated_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Private source and credentials never enter request contents or inherited model caches."""
    source = tmp_path / "source.txt"
    source.write_text("private-source-sentinel", encoding="utf-8")
    monkeypatch.setenv("HF_TOKEN", "private-key-sentinel")
    monkeypatch.setenv("HF_TOKEN_PATH", "private-token-path-sentinel")
    monkeypatch.setattr("reachy_mini_conversation_app.document_assets.find_spec", lambda name: object())
    requests: list[dict[str, object]] = []

    def fake_process(command, **kwargs):
        environment = kwargs["env"]
        assert "HF_TOKEN" not in environment and "HF_TOKEN_PATH" not in environment
        assert environment["HF_HUB_OFFLINE"] == "1" and environment["REACHY_MINI_SKIP_DOTENV"] == "1"
        assert environment["HF_HOME"].startswith(str(tmp_path))

        def communicate(payload):
            requests.append(json.loads(payload))
            assert b"private-source-sentinel" not in payload and b"private-key-sentinel" not in payload
            return b'{"status":"ok","count":1,"source_sha256":"summary"}', b""

        return SimpleNamespace(returncode=0, communicate=communicate)

    with AssetOperation(tmp_path / "package", "package", replace=False) as operation:
        monkeypatch.setattr("reachy_mini_conversation_app.document_assets.subprocess.Popen", fake_process)
        result = run_preparation_worker({"operation": "produce", "source": str(source)}, operation)
    assert result["count"] == 1 and requests[0]["source"] == str(source)


def test_worker_content_in_result_is_rejected_without_logging_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An invalid worker response cannot leak a passage through controller diagnostics."""
    monkeypatch.setattr("reachy_mini_conversation_app.document_assets.find_spec", lambda name: object())
    with AssetOperation(tmp_path / "package", "package", replace=False) as operation:
        monkeypatch.setattr(
            "reachy_mini_conversation_app.document_assets.subprocess.Popen",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0, communicate=lambda payload: (b'{"status":"ok","text":"private-passage-sentinel"}', b"")
            ),
        )
        with pytest.raises(PreparationError, match="validation_failed"):
            run_preparation_worker({"operation": "produce"}, operation)
    assert "private-passage-sentinel" not in caplog.text


def test_unconfirmed_worker_exit_keeps_owned_material(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cleanup cannot delete a candidate whose worker may still hold files open."""
    monkeypatch.setattr("reachy_mini_conversation_app.document_assets.find_spec", lambda name: object())
    calls: list[str] = []

    def interrupted(payload):
        raise KeyboardInterrupt

    def timed_out(timeout):
        raise subprocess.TimeoutExpired("synthetic worker", timeout)

    with pytest.raises(PreparationError, match="recovery_required"):
        with AssetOperation(tmp_path / "package", "package", replace=False) as operation:
            monkeypatch.setattr(
                "reachy_mini_conversation_app.document_assets.subprocess.Popen",
                lambda *args, **kwargs: SimpleNamespace(
                    communicate=interrupted,
                    terminate=lambda: calls.append("terminate"),
                    kill=lambda: calls.append("kill"),
                    wait=timed_out,
                ),
            )
            run_preparation_worker({"operation": "produce"}, operation)
    assert calls == ["terminate", "kill"] and operation.lock.exists() and operation.stage.exists()


def test_hard_interruption_retains_backup_and_rejects_a_new_writer(tmp_path: Path) -> None:
    """An abruptly exited writer leaves recognizable ownership and an untouched old backup."""
    destination = tmp_path / "package"
    destination.mkdir()
    (destination / "old").write_bytes(b"old")
    command = """
import os,sys
from pathlib import Path
from reachy_mini_conversation_app.document_assets import AssetOperation
with AssetOperation(Path(sys.argv[1]), "package", True) as operation:
    (operation.stage / "new").write_bytes(b"new")
    operation.record("validated")
    operation.destination.rename(operation.backup)
    operation.record("backed_up")
    os._exit(9)
"""
    result = subprocess.run([sys.executable, "-c", command, str(destination)], capture_output=True, check=False)
    assert result.returncode == 9
    record = json.loads((tmp_path / ".package.lock/operation.json").read_text(encoding="utf-8"))
    assert record["phase"] == "backed_up" and record["previous_files"]
    assert (tmp_path / record["backup_name"] / "old").read_bytes() == b"old"
    with pytest.raises(PreparationError, match="destination_busy"):
        with AssetOperation(destination, "package", replace=True):
            pytest.fail("A hard-crashed operation was automatically recovered")
