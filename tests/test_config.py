"""Tests for configuration helpers."""

import sys
import subprocess
from pathlib import Path

import pytest

from reachy_mini_conversation_app import config


def test_document_paths_default_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Document retrieval requires two explicitly configured local paths."""
    monkeypatch.delenv("REACHY_MINI_DOCUMENT_INDEX_PATH", raising=False)
    monkeypatch.delenv("REACHY_MINI_DOCUMENT_MODEL_PATH", raising=False)
    assert config.resolve_document_paths() == (None, None)


@pytest.mark.parametrize("missing", ["INDEX", "MODEL"])
def test_document_paths_preserve_missing_configuration(
    missing: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial configuration remains incomplete rather than supplying an implicit path."""
    monkeypatch.setenv("REACHY_MINI_DOCUMENT_INDEX_PATH", str(tmp_path / "package"))
    monkeypatch.setenv("REACHY_MINI_DOCUMENT_MODEL_PATH", str(tmp_path / "model"))
    monkeypatch.delenv(f"REACHY_MINI_DOCUMENT_{missing}_PATH")
    paths = config.resolve_document_paths()
    assert paths[0 if missing == "INDEX" else 1] is None


def test_document_paths_resolve_once_at_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime environment refresh does not change the instance's document selection."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REACHY_MINI_DOCUMENT_INDEX_PATH", "designated-package")
    monkeypatch.setenv("REACHY_MINI_DOCUMENT_MODEL_PATH", "local-model")
    paths = config.resolve_document_paths()
    assert paths == (tmp_path / "designated-package", tmp_path / "local-model")
    monkeypatch.setattr(config.config, "DOCUMENT_INDEX_PATH", paths[0], raising=False)
    monkeypatch.setattr(config.config, "DOCUMENT_MODEL_PATH", paths[1], raising=False)
    monkeypatch.setenv("REACHY_MINI_DOCUMENT_INDEX_PATH", "another-package")
    config.refresh_runtime_config_from_env()
    assert (config.config.DOCUMENT_INDEX_PATH, config.config.DOCUMENT_MODEL_PATH) == paths


@pytest.mark.parametrize("value", ["https://example.test/index", "file:///private/index", "ssh://host/index"])
def test_document_paths_reject_urls_without_logging_path(
    value: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Remote document locations are rejected without disclosing their contents."""
    monkeypatch.setenv("REACHY_MINI_DOCUMENT_INDEX_PATH", value)
    monkeypatch.delenv("REACHY_MINI_DOCUMENT_MODEL_PATH", raising=False)
    assert config.resolve_document_paths() == (None, None)
    assert value not in caplog.text


@pytest.mark.parametrize(
    "raw_value, expected",
    [
        ("45", 45.0),
        ("", config.DEFAULT_APP_TIMEOUT_MINUTES),  # unset/blank falls back to the default
        ("soon", config.DEFAULT_APP_TIMEOUT_MINUTES),  # unparseable falls back to the default
        ("0", None),  # non-positive disables the watchdog
        ("-1", None),
    ],
)
def test_resolve_app_timeout_minutes(monkeypatch, raw_value, expected) -> None:
    """The env timeout parses to minutes, falls back to the default, or disables on non-positive."""
    monkeypatch.setenv(config.APP_TIMEOUT_MINUTES_ENV, raw_value)

    assert config.resolve_app_timeout_minutes() == expected


@pytest.mark.parametrize(
    "raw_language, expected_language",
    [(None, "auto"), ("", "auto"), (" \t ", "auto"), ("auto", "auto"), ("en", "en"), (" zh ", "zh")],
)
def test_transcription_language_at_startup_and_reload(
    monkeypatch: pytest.MonkeyPatch, raw_language: str | None, expected_language: str
) -> None:
    """Startup and environment reloads default to auto while preserving explicit languages."""
    if raw_language is None:
        monkeypatch.delenv(config.REALTIME_TRANSCRIPTION_LANGUAGE_ENV, raising=False)
    else:
        monkeypatch.setenv(config.REALTIME_TRANSCRIPTION_LANGUAGE_ENV, raw_language)
    monkeypatch.setenv("PYTHONPATH", str(config.PROJECT_ROOT / "src"))

    subprocess.run(
        [
            sys.executable,
            "-c",
            "from reachy_mini_conversation_app.config import config; "
            f"assert config.REALTIME_TRANSCRIPTION_LANGUAGE == {expected_language!r}",
        ],
        check=True,
    )

    monkeypatch.setattr(config.config, "REALTIME_TRANSCRIPTION_LANGUAGE", "stale")
    config.refresh_runtime_config_from_env()

    assert config.config.REALTIME_TRANSCRIPTION_LANGUAGE == expected_language


@pytest.mark.parametrize("name", ["LOCAL_VAD_ENABLED", "LOCAL_BARGE_IN_ENABLED"])
@pytest.mark.parametrize("raw_value, expected", [(None, True), ("true", True), ("false", False)])
def test_local_speech_flags_default_on_and_follow_environment(
    monkeypatch: pytest.MonkeyPatch, name: str, raw_value: str | None, expected: bool
) -> None:
    """Local detection and barge-in are on by default and follow an explicit environment value."""
    if raw_value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, raw_value)
    monkeypatch.setattr(config.config, name, not expected)
    config.refresh_runtime_config_from_env()
    assert getattr(config.config, name) is expected
