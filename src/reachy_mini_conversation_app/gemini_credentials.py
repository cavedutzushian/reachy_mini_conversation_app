import os
import re
import sys
import json
import uuid
import hashlib
import logging
import threading
from typing import BinaryIO, Protocol
from pathlib import Path
from dataclasses import field, asdict, replace, dataclass
from collections.abc import Callable

from keyring.errors import KeyringError, KeyringLocked


if sys.platform == "win32":
    import msvcrt

    from keyring.backends.Windows import WinVaultKeyring
elif sys.platform == "darwin":
    import fcntl

    from keyring.backends.macOS import Keyring
else:
    import fcntl

    from keyring.backends.SecretService import Keyring as SecretServiceKeyring


logger = logging.getLogger(__name__)
SLOT_PATTERN = re.compile(r"[0-9a-f]{32}")


class CredentialError(RuntimeError):
    """Expose only a safe credential failure reason."""

    def __init__(self, reason: str) -> None:
        """Retain a fixed reason without the original exception or credential."""
        self.reason = reason
        super().__init__(reason)


class CredentialVault(Protocol):
    """Provide protected storage without exposing backend-specific details."""

    def get_password(self, service: str, username: str) -> str | None:
        """Read one protected entry."""
        ...

    def set_password(self, service: str, username: str, password: str) -> None:
        """Save one protected entry."""
        ...

    def delete_password(self, service: str, username: str) -> None:
        """Delete one protected entry."""
        ...


def protected_vault() -> CredentialVault:
    """Select an OS-native backend without plugin discovery or plaintext fallback."""
    try:
        if sys.platform == "win32":
            windows_factory: Callable[[], WinVaultKeyring] = WinVaultKeyring
            windows = windows_factory()
            windows.persist = "local machine"
            backend: CredentialVault = windows
        elif sys.platform == "darwin":
            macos_factory: Callable[[], CredentialVault] = Keyring
            backend = macos_factory()
        elif sys.platform.startswith("linux"):
            linux_factory: Callable[[], CredentialVault] = SecretServiceKeyring
            backend = linux_factory()
        else:
            raise CredentialError("storage_unavailable")
        return backend
    except (ImportError, KeyringError, OSError, RuntimeError) as error:
        logger.warning("Credential backend unavailable: %s", type(error).__name__)
        raise CredentialError("storage_unavailable") from None


@dataclass(frozen=True)
class CredentialMetadata:
    """Describe a credential transaction without storing credential material."""

    version: int = 1
    revision: int = 0
    state: str = "cleared"
    active_revision: str | None = None
    pending_revision: str | None = None
    retired_revisions: tuple[str, ...] = ()
    manual_reconnect_required: bool = False

    @classmethod
    def decode(cls, text: str) -> "CredentialMetadata":
        """Reject malformed or contradictory metadata instead of treating it as absent."""
        try:
            payload: object = json.loads(text)
            if not isinstance(payload, dict) or set(payload) != set(cls.__dataclass_fields__):
                raise ValueError
            version, revision, state = payload["version"], payload["revision"], payload["state"]
            active, pending = payload["active_revision"], payload["pending_revision"]
            retired, manual = payload["retired_revisions"], payload["manual_reconnect_required"]
            if type(version) is not int or version != 1 or type(revision) is not int or revision < 0:
                raise ValueError
            if not isinstance(state, str) or state not in ("active", "preparing", "clearing", "cleared"):
                raise ValueError
            if active is not None and (not isinstance(active, str) or not SLOT_PATTERN.fullmatch(active)):
                raise ValueError
            if pending is not None and (not isinstance(pending, str) or not SLOT_PATTERN.fullmatch(pending)):
                raise ValueError
            if not isinstance(retired, list) or not all(
                isinstance(slot, str) and SLOT_PATTERN.fullmatch(slot) for slot in retired
            ):
                raise ValueError
            if not isinstance(manual, bool) or len(retired) != len(set(retired)):
                raise ValueError
            if state == "active" and (active is None or pending is not None):
                raise ValueError
            if state == "preparing" and pending is None:
                raise ValueError
            if state == "cleared" and (active is not None or pending is not None or retired):
                raise ValueError
            if state == "clearing" and not manual:
                raise ValueError
            slots = [slot for slot in (active, pending) if slot is not None] + retired
            if len(slots) != len(set(slots)):
                raise ValueError
            return cls(version, revision, state, active, pending, tuple(retired), manual)
        except (ValueError, TypeError, KeyError):
            raise CredentialError("storage_failed") from None


@dataclass(frozen=True, repr=False)
class CredentialSnapshot:
    """Keep an effective credential out of repr and public status."""

    secret: str = field(repr=False)
    revision: int
    source: str


class GeminiCredentials:
    """Own one instance's protected credential and nonsecret transaction journal."""

    def __init__(
        self,
        scope: Path,
        environment_key: str,
        *,
        vault_factory: Callable[[], CredentialVault] = protected_vault,
    ) -> None:
        """Bind an instance scope and isolated environment snapshot."""
        self.scope = scope.expanduser().resolve()
        self.owner_epoch = uuid.uuid4().hex
        self.namespace = hashlib.sha256(os.path.normcase(str(self.scope)).encode()).hexdigest()
        self.path = self.scope / "gemini-credential.json"
        self._environment_key = environment_key.strip()
        self._vault_factory = vault_factory
        self._vault: CredentialVault | None = None
        self._lease: BinaryIO | None = None
        self._commit_lock = threading.RLock()
        self._intent_lock = threading.RLock()
        self.metadata = CredentialMetadata()
        self.revision = 0
        self.operation_id: str | None = None
        self.validation = "unverified"
        self.apply = "idle"
        self.reason: str | None = None
        self.storage = "available"
        self._blocked = False
        self._secret = ""
        self._source = "none"

    def initialize(self) -> None:
        """Acquire the instance lease and resolve the saved source without reading unrelated entries."""
        with self._commit_lock:
            try:
                self.scope.mkdir(parents=True, exist_ok=True)
                lease = (self.scope / "gemini-credential.lock").open("a+b")
                try:
                    lease.seek(0)
                    if sys.platform == "win32":
                        if not lease.read(1):
                            lease.write(b"0")
                            lease.flush()
                        lease.seek(0)
                        msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    lease.close()
                    raise CredentialError("storage_busy") from None
                self._lease = lease
                try:
                    self.metadata = CredentialMetadata.decode(self.path.read_text(encoding="utf-8"))
                except FileNotFoundError:
                    self.metadata = CredentialMetadata()
                self.revision = self.metadata.revision
                self._resolve()
                if self.metadata.state != "clearing":
                    try:
                        self._cleanup()
                    except CredentialError:
                        self.reason = "cleanup_pending"
                        logger.warning("Credential recovery cleanup pending")
            except (CredentialError, OSError, UnicodeError) as error:
                self._blocked = True
                self.reason = error.reason if isinstance(error, CredentialError) else "storage_failed"
                self.storage = "busy" if self.reason == "storage_busy" else "error"
                self._secret, self._source = "", "blocked"
                logger.warning("Credential initialization failed: %s", self.reason)

    def close(self) -> None:
        """Release the process lease and credential references."""
        with self._commit_lock:
            self._secret = ""
            if self._lease is not None:
                self._lease.close()
                self._lease = None

    def snapshot(self) -> CredentialSnapshot:
        """Return the effective credential only to the conversation transport."""
        with self._intent_lock:
            return CredentialSnapshot(self._secret, self.revision, self._source)

    def status(self) -> dict[str, object]:
        """Return nonsecret source, validation and operation state."""
        return {
            "owner_epoch": self.owner_epoch,
            "configured": bool(self._secret) and not self._blocked,
            "managed_presence": "unknown"
            if self._blocked
            else ("present" if self.metadata.active_revision is not None else "absent"),
            "environment_available": bool(self._environment_key),
            "source": "blocked" if self._blocked else self._source,
            "storage": self.storage,
            "validation": self.validation,
            "apply": self.apply,
            "manual_reconnect_required": self.metadata.manual_reconnect_required,
            "revision": self.revision,
            "operation_id": self.operation_id,
            "reason": self.reason,
        }

    def _entry(self, slot: str, operation: str, secret: str = "") -> str | None:
        try:
            if self._vault is None:
                self._vault = self._vault_factory()
            service = "reachy-mini-conversation-gemini-" + self.namespace + "-" + slot
            if operation == "get":
                return self._vault.get_password(service, "gemini")
            if operation == "set":
                self._vault.set_password(service, "gemini", secret)
            elif operation == "delete":
                if self._vault.get_password(service, "gemini") is not None:
                    self._vault.delete_password(service, "gemini")
                if self._vault.get_password(service, "gemini") is not None:
                    raise CredentialError("storage_failed")
            return None
        except CredentialError:
            raise
        except Exception as error:
            # Native backends use different exception types and may include secrets in their messages.
            reason = "storage_locked" if isinstance(error, KeyringLocked) else "storage_failed"
            self.storage = "locked" if reason == "storage_locked" else "error"
            logger.warning("Credential storage failed: %s (%s)", reason, type(error).__name__)
            raise CredentialError(reason) from None

    def _resolve(self) -> None:
        if self._blocked or self.metadata.state == "clearing":
            self._secret, self._source = "", "blocked"
        elif self.metadata.active_revision is not None:
            secret = self._entry(self.metadata.active_revision, "get")
            if not secret:
                raise CredentialError("storage_failed")
            self._secret, self._source = secret, "settings"
        else:
            self._secret = self._environment_key
            self._source = "environment" if self._secret else "none"

    def _write(self, metadata: CredentialMetadata) -> None:
        temporary = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
        serialized = json.dumps(asdict(metadata), sort_keys=True) + "\n"
        try:
            with temporary.open("x", encoding="utf-8") as target:
                target.write(serialized)
                target.flush()
                os.fsync(target.fileno())
            temporary.replace(self.path)
        except OSError:
            try:
                observed = CredentialMetadata.decode(self.path.read_text(encoding="utf-8"))
            except (OSError, CredentialError, UnicodeError):
                self._blocked = True
                self._secret, self._source = "", "blocked"
                raise CredentialError("result_unknown") from None
            if observed != metadata:
                raise CredentialError("storage_failed") from None
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("Credential metadata temporary cleanup failed")
        self.metadata = metadata

    def begin(self, expected_revision: int, *, clear: bool = False) -> int:
        """Accept one explicit intent and retire results from earlier operations."""
        with self._intent_lock:
            if expected_revision != self.revision:
                raise CredentialError("revision_conflict")
            if self._blocked or self._lease is None:
                raise CredentialError(self.reason or "storage_unavailable")
            if self.metadata.state == "clearing" and not clear:
                raise CredentialError("storage_failed")
            self.revision += 1
            self.operation_id = uuid.uuid4().hex
            self.reason = None
            self.validation = "unverified" if clear else "validating"
            self.apply = "clearing" if clear else "idle"
            return self.revision

    def invalidate(self) -> None:
        """Retire pending validation when the selected connection configuration changes."""
        with self._intent_lock:
            self.revision += 1
            self.validation = "unverified"
            if self.apply != "clearing":
                self.reason = "superseded"

    def failure(self, reason: str, revision: int) -> None:
        """Publish a sanitized failure only if the operation still owns current state."""
        with self._intent_lock:
            if revision == self.revision:
                self.reason = reason
                self.validation = "failed"
                self.apply = "failed"
                logger.warning("Credential operation failed: %s", reason)

    def set_manual_reconnect(self, required: bool, expected_revision: int | None = None) -> None:
        """Persist whether a fresh explicit retry is required before connecting Gemini."""
        with self._commit_lock, self._intent_lock:
            if expected_revision is not None and expected_revision != self.revision:
                raise CredentialError("superseded")
            if not required and (self._blocked or self._source == "blocked"):
                raise CredentialError(self.reason or "storage_failed")
            self._write(replace(self.metadata, revision=self.revision, manual_reconnect_required=required))

    def save(self, candidate: str, revision: int) -> None:
        """Commit a verified candidate only after protected write and readback succeed."""
        with self._commit_lock:
            slot = uuid.uuid4().hex
            try:
                with self._intent_lock:
                    if revision != self.revision:
                        raise CredentialError("superseded")
                    if self.metadata.state == "clearing":
                        raise CredentialError("storage_failed")
                    self.apply = "saving"
                if self.metadata.pending_revision is not None:
                    self._cleanup()
                with self._intent_lock:
                    if revision != self.revision:
                        raise CredentialError("superseded")
                    self._write(replace(self.metadata, state="preparing", revision=revision, pending_revision=slot))
                self._entry(slot, "set", candidate)
                if self._entry(slot, "get") != candidate:
                    raise CredentialError("storage_failed")
                with self._intent_lock:
                    if revision != self.revision:
                        raise CredentialError("superseded")
                    retired = self.metadata.retired_revisions
                    if self.metadata.active_revision is not None:
                        retired += (self.metadata.active_revision,)
                    self._write(
                        replace(
                            self.metadata,
                            state="active",
                            active_revision=slot,
                            pending_revision=None,
                            retired_revisions=retired,
                        )
                    )
                    self._secret, self._source = candidate, "settings"
                    self.storage, self.validation, self.apply = "available", "validated", "applied"
                try:
                    self._cleanup()
                except CredentialError:
                    with self._intent_lock:
                        if revision == self.revision:
                            self.reason = "cleanup_pending"
            except CredentialError as error:
                self.failure(error.reason, revision)
                if not self._blocked and self.metadata.pending_revision == slot:
                    try:
                        self._cleanup()
                    except CredentialError:
                        logger.warning("Uncommitted credential cleanup pending")
                raise

    def _cleanup(self) -> None:
        pending = self.metadata.pending_revision
        for slot in self.metadata.retired_revisions + ((pending,) if pending is not None else ()):
            self._entry(slot, "delete")
        if self.metadata.retired_revisions or pending is not None:
            state = "active" if self.metadata.active_revision is not None else "cleared"
            self._write(replace(self.metadata, state=state, pending_revision=None, retired_revisions=()))

    def clear(self, revision: int) -> None:
        """Delete all tracked protected entries before selecting an environment fallback."""
        with self._commit_lock:
            try:
                with self._intent_lock:
                    if revision != self.revision:
                        raise CredentialError("superseded")
                    self._secret, self._source = "", "blocked"
                    self._write(
                        replace(self.metadata, state="clearing", revision=revision, manual_reconnect_required=True)
                    )
                slots = self.metadata.retired_revisions + tuple(
                    slot
                    for slot in (self.metadata.active_revision, self.metadata.pending_revision)
                    if slot is not None
                )
                for slot in slots:
                    self._entry(slot, "delete")
                with self._intent_lock:
                    if revision != self.revision:
                        raise CredentialError("superseded")
                    self._write(CredentialMetadata(revision=revision, manual_reconnect_required=True))
                    self._resolve()
                    self.apply, self.validation, self.reason = "idle", "unverified", None
            except CredentialError as error:
                self.failure(error.reason, revision)
                raise
