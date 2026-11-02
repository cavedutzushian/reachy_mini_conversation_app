"""Tests for persisted instance-local startup settings."""

from pathlib import Path

import pytest

from reachy_mini_conversation_app.config import config
from reachy_mini_conversation_app.prompts import get_session_instructions
from reachy_mini_conversation_app.settings_store import AppSettings, update_settings, load_settings_into_runtime
from reachy_mini_conversation_app.startup_settings import (
    StartupSettings,
    read_startup_settings,
    write_startup_settings,
    load_startup_settings_into_runtime,
)


def test_write_and_read_startup_settings(tmp_path) -> None:
    """Startup settings should round-trip through startup_settings.json."""
    write_startup_settings(tmp_path, profile="sorry_bro", voice="shimmer")

    assert read_startup_settings(tmp_path) == StartupSettings(profile="sorry_bro", voice="shimmer")


def test_load_startup_settings_into_runtime_applies_profile_when_no_env(monkeypatch, tmp_path) -> None:
    """Startup settings should seed the runtime profile when no explicit env override exists."""
    write_startup_settings(tmp_path, profile="sorry_bro", voice="shimmer")
    applied_profiles: list[str | None] = []
    monkeypatch.delenv("REACHY_MINI_CUSTOM_PROFILE", raising=False)
    monkeypatch.setattr(
        "reachy_mini_conversation_app.config.set_custom_profile",
        lambda profile: applied_profiles.append(profile),
    )

    settings = load_startup_settings_into_runtime(tmp_path)

    assert settings == StartupSettings(profile="sorry_bro", voice="shimmer")
    assert applied_profiles == ["sorry_bro"]


def test_load_startup_settings_into_runtime_saved_settings_override_instance_env(monkeypatch, tmp_path) -> None:
    """Saved startup settings should override an instance-local profile env value."""
    write_startup_settings(tmp_path, profile="sorry_bro", voice="shimmer")
    applied_profiles: list[str | None] = []
    monkeypatch.setenv("REACHY_MINI_CUSTOM_PROFILE", "env_profile")
    monkeypatch.setattr(
        "reachy_mini_conversation_app.config.set_custom_profile",
        lambda profile: applied_profiles.append(profile),
    )

    settings = load_startup_settings_into_runtime(tmp_path)

    assert settings == StartupSettings(profile="sorry_bro", voice="shimmer")
    assert applied_profiles == ["sorry_bro"]


def test_load_startup_settings_into_runtime_saved_settings_override_inherited_env(monkeypatch, tmp_path) -> None:
    """Saved startup settings should override a profile inherited from another `.env`."""
    write_startup_settings(tmp_path, profile="nature_documentarian", voice="cedar")
    applied_profiles: list[str | None] = []
    monkeypatch.setenv("REACHY_MINI_CUSTOM_PROFILE", "env_profile")
    monkeypatch.setattr(
        "reachy_mini_conversation_app.config.set_custom_profile",
        lambda profile: applied_profiles.append(profile),
    )

    settings = load_startup_settings_into_runtime(tmp_path)

    assert settings == StartupSettings(profile="nature_documentarian", voice="cedar")
    assert applied_profiles == ["nature_documentarian"]


def test_load_startup_settings_into_runtime_preserves_inherited_env_without_saved_settings(
    monkeypatch, tmp_path
) -> None:
    """Inherited env config should still apply when no startup settings have been saved."""
    applied_profiles: list[str | None] = []
    monkeypatch.setenv("REACHY_MINI_CUSTOM_PROFILE", "env_profile")
    monkeypatch.setattr(
        "reachy_mini_conversation_app.config.set_custom_profile",
        lambda profile: applied_profiles.append(profile),
    )

    settings = load_startup_settings_into_runtime(tmp_path)

    assert settings == StartupSettings()
    assert applied_profiles == []


@pytest.mark.parametrize("language", [None, "auto", "fr", "zh"])
def test_restart_rebuilds_policy_without_rewriting_saved_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str | None
) -> None:
    """Restarts preserve unset language, voice and disabled permissions in storage."""
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", None)
    monkeypatch.setattr(config, "PROFILE_LANGUAGES", {})
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", "auto")
    monkeypatch.setattr(config, "MEMORY_ENABLED", True)
    monkeypatch.setattr(config, "CAMERA_ENABLED", True)
    monkeypatch.setenv("REALTIME_TRANSCRIPTION_LANGUAGE", "auto")
    write_startup_settings(tmp_path, profile="default", voice="Kore")
    update_settings(tmp_path, AppSettings(language=language, camera_enabled=False, memory_enabled=False))
    memory_path = tmp_path / "memory.v1.json"
    memory_path.write_text('{"test":"这是保留的原文"}', encoding="utf-8")
    original = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    policies = []
    for _ in range(2):
        load_startup_settings_into_runtime(tmp_path)
        load_settings_into_runtime(tmp_path)
        policies.append(get_session_instructions(tmp_path))
    assert policies[0] == policies[1]
    assert "Traditional Chinese" in policies[0]
    assert config.REALTIME_TRANSCRIPTION_LANGUAGE == (language or "auto")
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == original
    assert config.MEMORY_ENABLED is False and config.CAMERA_ENABLED is False
