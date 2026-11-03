import sys
import json
import threading
import subprocess
from pathlib import Path
from dataclasses import asdict

import pytest
import keyring
from keyring.errors import KeyringLocked

import reachy_mini_conversation_app.gemini_credentials as credential_mod
from reachy_mini_conversation_app.gemini_credentials import (
    CredentialError,
    GeminiCredentials,
    CredentialMetadata,
)


class FakeVault:
    """Store only isolated test credentials and simulate protected-store failures."""

    def __init__(self) -> None:
        """Initialize isolated fake storage."""
        self.entries: dict[tuple[str, str], str] = {}
        self.failure: str | None = None

    def get_password(self, service: str, username: str) -> str | None:
        """Return one fake entry or simulate a locked store."""
        if self.failure == "get":
            raise KeyringLocked("sentinel must not reach errors")
        return self.entries.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        """Save one fake entry or simulate a failed write."""
        if self.failure == "set":
            raise OSError("sentinel must not reach errors")
        self.entries[service, username] = password

    def delete_password(self, service: str, username: str) -> None:
        """Delete one fake entry or simulate a failed deletion."""
        if self.failure == "delete":
            raise OSError("sentinel must not reach errors")
        self.entries.pop((service, username), None)


def test_environment_does_not_open_vault(tmp_path: Path) -> None:
    """Legacy environment-only deployments need no available OS credential service."""

    def forbidden() -> FakeVault:
        raise AssertionError("No vault should be opened")

    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=forbidden)
    store.initialize()
    try:
        assert store.snapshot().secret == "environment-sentinel"
        assert store.status()["source"] == "environment"
        assert "sentinel" not in str(store.status())
        assert "sentinel" not in repr(store.snapshot())
        assert not store.path.exists()
    finally:
        store.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 2),
        ("version", True),
        ("revision", -1),
        ("revision", True),
        ("state", "unknown"),
        ("active_revision", "not-a-slot"),
        ("manual_reconnect_required", "false"),
        ("retired_revisions", ["invalid"]),
    ],
)
def test_invalid_journal_never_becomes_environment_fallback(tmp_path: Path, field: str, value: object) -> None:
    """Invalid persisted metadata fails closed rather than silently selecting another key."""
    payload = asdict(CredentialMetadata())
    payload[field] = value
    (tmp_path / "gemini-credential.json").write_text(json.dumps(payload), encoding="utf-8")
    store = GeminiCredentials(tmp_path, "fallback-sentinel", vault_factory=FakeVault)
    store.initialize()
    try:
        assert store.status()["source"] == "blocked"
        assert not store.snapshot().secret
    finally:
        store.close()


def test_clearing_precedes_existing_active_slot(tmp_path: Path) -> None:
    """Clearing blocks the old slot even while its identifier remains in the journal."""
    metadata = CredentialMetadata(state="clearing", active_revision="a" * 32, manual_reconnect_required=True)
    (tmp_path / "gemini-credential.json").write_text(json.dumps(asdict(metadata)), encoding="utf-8")
    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=FakeVault)
    store.initialize()
    try:
        assert store.status()["source"] == "blocked"
        assert not store.snapshot().secret
        assert store.status()["manual_reconnect_required"] is True
    finally:
        store.close()


@pytest.mark.parametrize("environment", ["", "environment-sentinel"])
def test_first_pending_value_preserves_previous_source(tmp_path: Path, environment: str) -> None:
    """A not-yet-applied first candidate does not replace the environment or absence."""
    metadata = CredentialMetadata(state="preparing", pending_revision="a" * 32)
    (tmp_path / "gemini-credential.json").write_text(json.dumps(asdict(metadata)), encoding="utf-8")
    store = GeminiCredentials(tmp_path, environment, vault_factory=FakeVault)
    store.initialize()
    try:
        assert store.snapshot().secret == environment
        assert store.status()["source"] == ("environment" if environment else "none")
    finally:
        store.close()


def test_known_slot_missing_does_not_fallback(tmp_path: Path) -> None:
    """An active pointer whose protected entry is missing is not an absent setting."""
    metadata = CredentialMetadata(state="active", active_revision="a" * 32)
    (tmp_path / "gemini-credential.json").write_text(json.dumps(asdict(metadata)), encoding="utf-8")
    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=FakeVault)
    store.initialize()
    try:
        assert store.status()["source"] == "blocked"
    finally:
        store.close()


def test_instance_lease_rejects_second_process_and_releases(tmp_path: Path) -> None:
    """Different processes cannot manage the same scope concurrently."""
    store = GeminiCredentials(tmp_path, "", vault_factory=FakeVault)
    store.initialize()
    script = (
        "from pathlib import Path; "
        "from reachy_mini_conversation_app.gemini_credentials import GeminiCredentials; "
        "import sys; s=GeminiCredentials(Path(sys.argv[1]),''); s.initialize(); "
        "print(s.status()['source']); s.close()"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, check=True
        )
        assert result.stdout.strip() == "blocked"
    finally:
        store.close()
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "none"


def test_scope_namespace_is_distinct_without_path_or_secret_labels(tmp_path: Path) -> None:
    """Namespace derivation separates instances without exposing their original paths."""
    first = GeminiCredentials(tmp_path / "first", "sentinel", vault_factory=FakeVault)
    second = GeminiCredentials(tmp_path / "second", "sentinel", vault_factory=FakeVault)
    assert first.namespace != second.namespace
    assert "sentinel" not in first.namespace and "first" not in first.namespace


def test_verified_save_survives_restart_without_plaintext(tmp_path: Path) -> None:
    """Only the active protected slot survives restart and normal queries cannot read it."""
    vault = FakeVault()
    store = GeminiCredentials(tmp_path, "env-sentinel", vault_factory=lambda: vault)
    store.initialize()
    revision = store.begin(0)
    store.save("candidate-sentinel", revision)
    assert store.snapshot().secret == "candidate-sentinel"
    assert store.status()["source"] == "settings"
    assert "sentinel" not in store.path.read_text(encoding="utf-8")
    assert "sentinel" not in str(store.status())
    store.close()
    restarted = GeminiCredentials(tmp_path, "env-sentinel", vault_factory=lambda: vault)
    restarted.initialize()
    try:
        assert restarted.snapshot().secret == "candidate-sentinel"
        assert restarted.status()["validation"] == "unverified"
        assert restarted.owner_epoch != store.owner_epoch
    finally:
        restarted.close()


def test_failed_save_keeps_original_source(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A vault write failure never applies the candidate or leaks the backend error."""
    vault = FakeVault()
    vault.failure = "set"
    store = GeminiCredentials(tmp_path, "original-sentinel", vault_factory=lambda: vault)
    store.initialize()
    try:
        revision = store.begin(0)
        with pytest.raises(CredentialError):
            store.save("candidate-sentinel", revision)
        assert store.snapshot().secret == "original-sentinel"
        assert "sentinel" not in caplog.text
    finally:
        store.close()


def test_clear_removes_all_entries_but_requires_manual_reconnect(tmp_path: Path) -> None:
    """Clear falls back to the environment only after deleting protected entries."""
    vault = FakeVault()
    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=lambda: vault)
    store.initialize()
    try:
        store.save("first-sentinel", store.begin(0))
        store.save("second-sentinel", store.begin(store.revision))
        assert len(vault.entries) == 1
        store.clear(store.begin(store.revision, clear=True))
        assert not vault.entries
        assert store.snapshot().secret == "environment-sentinel"
        assert store.status()["manual_reconnect_required"] is True
    finally:
        store.close()


def test_clear_failure_stays_blocked_across_restart(tmp_path: Path) -> None:
    """A failed deletion cannot silently revive either the old entry or environment."""
    vault = FakeVault()
    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=lambda: vault)
    store.initialize()
    store.save("first-sentinel", store.begin(0))
    vault.failure = "delete"
    with pytest.raises(CredentialError):
        store.clear(store.begin(store.revision, clear=True))
    assert store.status()["source"] == "blocked"
    assert store.status()["manual_reconnect_required"] is True
    store.close()
    restarted = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=lambda: vault)
    restarted.initialize()
    try:
        assert restarted.status()["source"] == "blocked"
        vault.failure = None
        restarted.clear(restarted.begin(restarted.revision, clear=True))
        assert not vault.entries
        assert restarted.snapshot().secret == "environment-sentinel"
    finally:
        restarted.close()


def test_superseded_candidate_cannot_apply(tmp_path: Path) -> None:
    """A later intent retires an earlier verified result before it reaches storage."""
    store = GeminiCredentials(tmp_path, "original-sentinel", vault_factory=FakeVault)
    store.initialize()
    try:
        revision = store.begin(0)
        newer = store.begin(revision, clear=True)
        with pytest.raises(CredentialError, match="superseded"):
            store.save("late-sentinel", revision)
        assert store.revision == newer
        assert store.snapshot().secret == "original-sentinel"
    finally:
        store.close()


@pytest.mark.parametrize("environment", ["", "environment-sentinel"])
@pytest.mark.parametrize("managed", [False, True])
def test_four_source_combinations_reload_and_clear(tmp_path: Path, environment: str, managed: bool) -> None:
    """Reload and clear obey UI precedence for every source combination."""
    vault = FakeVault()
    store = GeminiCredentials(tmp_path, environment, vault_factory=lambda: vault)
    store.initialize()
    if managed:
        store.save("managed-sentinel", store.begin(0))
    expected = "managed-sentinel" if managed else environment
    assert store.snapshot().secret == expected
    store.close()
    restarted = GeminiCredentials(tmp_path, environment, vault_factory=lambda: vault)
    restarted.initialize()
    try:
        assert restarted.snapshot().secret == expected
        restarted.clear(restarted.begin(restarted.revision, clear=True))
        assert restarted.snapshot().secret == environment
        assert not vault.entries and restarted.metadata.manual_reconnect_required
    finally:
        restarted.close()


@pytest.mark.parametrize(
    "platform,attribute", [("win32", "WinVaultKeyring"), ("darwin", "Keyring"), ("linux", "SecretServiceKeyring")]
)
def test_native_backend_selection_ignores_plugins(
    platform: str, attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only explicitly selected platform backends may hold managed credentials."""

    class NativeVault(FakeVault):
        persist = "enterprise"

    backend = NativeVault()
    with monkeypatch.context() as patch:
        patch.setattr(credential_mod.sys, "platform", platform)
        patch.setattr(credential_mod, attribute, lambda: backend, raising=False)
        patch.setattr(keyring, "get_keyring", lambda: pytest.fail("Plugin discovery is forbidden"))
        assert credential_mod.protected_vault() is backend
    if platform == "win32":
        assert backend.persist == "local machine"


def test_atomic_commit_failure_preserves_original_slot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed active-pointer replace cannot replace the effective key."""
    vault = FakeVault()
    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=lambda: vault)
    store.initialize()
    try:
        store.save("original-sentinel", store.begin(0))
        old_slot = store.metadata.active_revision
        original_replace = Path.replace

        def fail_new_active(path: Path, target: Path) -> Path:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["state"] == "active" and payload["active_revision"] != old_slot:
                raise OSError("private-sentinel")
            return original_replace(path, target)

        monkeypatch.setattr(Path, "replace", fail_new_active)
        with pytest.raises(CredentialError):
            store.save("candidate-sentinel", store.begin(store.revision))
        assert store.snapshot().secret == "original-sentinel"
        assert store.metadata.active_revision == old_slot
        assert len(vault.entries) == 1
    finally:
        store.close()


def test_clear_wins_over_slow_protected_write(tmp_path: Path) -> None:
    """A retired worker cannot commit after a newer clear intent arrives."""
    entered, released = threading.Event(), threading.Event()

    class SlowVault(FakeVault):
        def set_password(self, service: str, username: str, password: str) -> None:
            """Pause a vault write until the next intent is recorded."""
            entered.set()
            assert released.wait(timeout=3)
            super().set_password(service, username, password)

    vault = SlowVault()
    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=lambda: vault)
    store.initialize()
    errors: list[str] = []

    def save_candidate() -> None:
        try:
            store.save("candidate-sentinel", 1)
        except CredentialError as error:
            errors.append(error.reason)

    store.begin(0)
    worker = threading.Thread(target=save_candidate)
    worker.start()
    try:
        assert entered.wait(timeout=2)
        revision = store.begin(store.revision, clear=True)
        released.set()
        store.clear(revision)
        worker.join(timeout=3)
        assert not worker.is_alive() and errors == ["superseded"]
        assert not vault.entries and store.snapshot().secret == "environment-sentinel"
    finally:
        released.set()
        worker.join(timeout=3)
        store.close()


def test_native_backend_specific_error_is_sanitized(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Platform-specific backend exceptions cannot escape as raw credential-bearing errors."""

    class NativeBackendError(Exception):
        """Represent an OS library exception outside keyring's common hierarchy."""

    class BrokenNativeVault(FakeVault):
        def get_password(self, service: str, username: str) -> str | None:
            """Simulate an OS error containing secret material."""
            raise NativeBackendError("candidate-sentinel")

    metadata = CredentialMetadata(state="active", active_revision="a" * 32)
    (tmp_path / "gemini-credential.json").write_text(json.dumps(asdict(metadata)), encoding="utf-8")
    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=BrokenNativeVault)
    store.initialize()
    try:
        assert store.status()["source"] == "blocked"
        assert store.status()["reason"] == "storage_failed"
        assert "sentinel" not in caplog.text
    finally:
        store.close()


def test_retired_apply_cannot_release_new_clear_gate(tmp_path: Path) -> None:
    """An old completion cannot undo the reconnect gate established by a later clear."""
    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=FakeVault)
    store.initialize()
    try:
        applied = store.begin(0)
        store.save("candidate-sentinel", applied)
        store.clear(store.begin(store.revision, clear=True))
        with pytest.raises(CredentialError, match="superseded"):
            store.set_manual_reconnect(False, applied)
        assert store.metadata.manual_reconnect_required
        assert store.snapshot().secret == "environment-sentinel"
    finally:
        store.close()
