"""Tests for the instance settings store."""

import json
from pathlib import Path

import pytest

from reachy_mini_conversation_app.config import config, refresh_runtime_config_from_env
from reachy_mini_conversation_app.prompts import get_session_instructions
from reachy_mini_conversation_app.settings_store import (
    AppSettings,
    read_settings,
    update_settings,
    load_settings_into_runtime,
)


def test_absent_file_reads_as_unset(tmp_path: Path) -> None:
    """A fresh instance has no settings and keeps the environment defaults."""
    assert read_settings(tmp_path) == AppSettings()


def test_provider_selection_preserves_other_provider_settings(tmp_path: Path) -> None:
    """Selecting Gemini preserves HF connection settings and never stores a key."""
    update_settings(tmp_path, AppSettings(hf_connection_mode="local", hf_ws_url="ws://robot:8765"))
    update_settings(tmp_path, AppSettings(conversation_backend="gemini", gemini_voice="Kore"))
    saved = read_settings(tmp_path)
    assert saved.conversation_backend == "gemini"
    assert saved.hf_ws_url == "ws://robot:8765"
    assert saved.gemini_voice == "Kore"
    assert "key" not in (tmp_path / "settings.json").read_text()


def test_provider_defaults_and_saved_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Saved choices override environment defaults without adding secret storage."""
    monkeypatch.delenv("REACHY_MINI_CONVERSATION_BACKEND", raising=False)
    refresh_runtime_config_from_env()
    assert config.CONVERSATION_BACKEND == "huggingface"
    monkeypatch.setenv("REACHY_MINI_CONVERSATION_BACKEND", "gemini")
    refresh_runtime_config_from_env()
    assert config.CONVERSATION_BACKEND == "gemini"
    update_settings(tmp_path, AppSettings(conversation_backend="huggingface", gemini_model="gemini-3.8-live"))
    load_settings_into_runtime(tmp_path)
    assert config.CONVERSATION_BACKEND == "huggingface"
    (tmp_path / "settings.json").write_text('{"conversation_backend":"unknown","gemini_model":"  "}', encoding="utf-8")
    assert read_settings(tmp_path).conversation_backend == "huggingface"
    assert read_settings(tmp_path).gemini_model is None


def test_update_merges_and_round_trips(tmp_path: Path) -> None:
    """Each write changes one field and leaves the others alone."""
    update_settings(tmp_path, AppSettings(language="fr"))
    merged = update_settings(tmp_path, AppSettings(memory_enabled=False))

    assert merged == AppSettings(language="fr", memory_enabled=False)
    assert read_settings(tmp_path) == merged

    payload = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["memory_enabled"] is False


def test_booleans_survive_as_booleans(tmp_path: Path) -> None:
    """The reason for leaving .env: a switch round-trips as a real boolean."""
    update_settings(tmp_path, AppSettings(camera_enabled=False))

    assert read_settings(tmp_path).camera_enabled is False


def test_awkward_value_cannot_write_another_key(tmp_path: Path) -> None:
    """A newline in a value stays inside that value (#532 is impossible here)."""
    update_settings(tmp_path, AppSettings(hf_ws_url="ws://host\nHF_TOKEN=leaked"))

    assert read_settings(tmp_path).hf_ws_url == "ws://host\nHF_TOKEN=leaked"
    payload = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert set(payload) == {"version", "hf_ws_url"}


def test_profile_languages_round_trip_and_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-personality languages are stored next to the shared one and win at runtime."""
    monkeypatch.setattr(config, "PROFILE_LANGUAGES", {})
    update_settings(tmp_path, AppSettings(language="en", profile_languages={"sorry_bro": "fr"}))

    load_settings_into_runtime(tmp_path)

    assert read_settings(tmp_path).profile_languages == {"sorry_bro": "fr"}
    assert config.PROFILE_LANGUAGES == {"sorry_bro": "fr"}


def test_unusable_profile_language_entries_are_dropped(tmp_path: Path) -> None:
    """One bad entry must not cost the user the languages saved for other personalities."""
    (tmp_path / "settings.json").write_text(
        json.dumps({"profile_languages": {"sorry_bro": "fr", "chess_coach": 3, "hype_bot": " "}}), encoding="utf-8"
    )

    assert read_settings(tmp_path).profile_languages == {"sorry_bro": "fr"}


@pytest.mark.parametrize("content", ["{ not json", '"a string"', '{"memory_enabled": "false"}'])
def test_unusable_file_is_ignored(tmp_path: Path, content: str) -> None:
    """A corrupt or wrongly-typed file must not stop the app from starting."""
    (tmp_path / "settings.json").write_text(content, encoding="utf-8")

    assert read_settings(tmp_path) == AppSettings()


@pytest.mark.parametrize("language", ["auto", "en", "fr", "zh"])
def test_load_applies_over_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str) -> None:
    """Stored settings win over the env-derived defaults."""
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", "auto")
    monkeypatch.setattr(config, "MEMORY_ENABLED", True)
    update_settings(tmp_path, AppSettings(language=language, memory_enabled=False))

    load_settings_into_runtime(tmp_path)

    assert config.REALTIME_TRANSCRIPTION_LANGUAGE == language
    assert config.MEMORY_ENABLED is False


@pytest.mark.parametrize("raw_language, expected_language", [(None, "auto"), ("de", "de")])
def test_load_leaves_unset_fields_to_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw_language: str | None, expected_language: str
) -> None:
    """A setting the user never changed keeps its environment value."""
    if raw_language is None:
        monkeypatch.delenv("REALTIME_TRANSCRIPTION_LANGUAGE", raising=False)
    else:
        monkeypatch.setenv("REALTIME_TRANSCRIPTION_LANGUAGE", raw_language)
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", "stale")
    monkeypatch.setattr(config, "MEMORY_ENABLED", True)
    refresh_runtime_config_from_env()
    update_settings(tmp_path, AppSettings(memory_enabled=False))

    load_settings_into_runtime(tmp_path)

    assert config.REALTIME_TRANSCRIPTION_LANGUAGE == expected_language


@pytest.mark.parametrize("language", ["auto", "en", "zh"])
def test_loading_language_does_not_migrate_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    """Loading a language preserves settings bytes and disabled permissions."""
    monkeypatch.setattr(config, "PROFILE_LANGUAGES", {})
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", "auto")
    monkeypatch.setattr(config, "MEMORY_ENABLED", True)
    monkeypatch.setattr(config, "CAMERA_ENABLED", True)
    update_settings(
        tmp_path,
        AppSettings(
            language=language, profile_languages={"default": "fr"}, camera_enabled=False, memory_enabled=False
        ),
    )
    settings_path = tmp_path / "settings.json"
    original = settings_path.read_bytes()

    load_settings_into_runtime(tmp_path)

    assert settings_path.read_bytes() == original
    assert config.REALTIME_TRANSCRIPTION_LANGUAGE == language
    assert config.PROFILE_LANGUAGES == {"default": "fr"}
    assert config.CAMERA_ENABLED is False
    assert config.MEMORY_ENABLED is False
    assert json.loads(original)["version"] == 1


@pytest.mark.parametrize("language", ["auto", "fr", "zh"])
def test_temporary_language_policy_does_not_write_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    """Building temporary exception instructions leaves persisted language and content untouched."""
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", None)
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", language)
    monkeypatch.setattr(config, "PROFILE_LANGUAGES", {})
    monkeypatch.setattr(config, "MEMORY_ENABLED", False)
    update_settings(tmp_path, AppSettings(language=language, memory_enabled=False, camera_enabled=False))
    original = (tmp_path / "settings.json").read_bytes()

    instructions = get_session_instructions(tmp_path)

    assert "this response only" in instructions
    assert "then return to the default language policy" in instructions
    assert config.REALTIME_TRANSCRIPTION_LANGUAGE == language
    assert config.PROFILE_LANGUAGES == {}
    assert (tmp_path / "settings.json").read_bytes() == original
    assert list(tmp_path.iterdir()) == [tmp_path / "settings.json"]
