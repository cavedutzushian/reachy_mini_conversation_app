"""Tests for app-level runtime behavior."""

import threading
from types import SimpleNamespace
from pathlib import Path
from argparse import Namespace
from unittest.mock import MagicMock

import pytest

import reachy_mini_conversation_app.main as main_mod
import reachy_mini_conversation_app.moves as moves_mod
import reachy_mini_conversation_app.console as console_mod
from reachy_mini_conversation_app.config import config


@pytest.fixture(autouse=True)
def isolated_credential_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runtime initialization away from the user's daily credential scope."""
    monkeypatch.setenv("REACHY_MINI_INSTANCE_PATH", str(tmp_path / "credential-scope"))


@pytest.mark.parametrize("provider", ["huggingface", "gemini"])
def test_factory_keeps_owner_state_across_handler_replacement(provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The existing factory selects only the configured provider and retains owner state."""
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", provider)
    monkeypatch.setattr(main_mod, "start_import_warmup", MagicMock())
    monkeypatch.setattr(main_mod.app_lifecycle, "wake_up_if_sleeping", MagicMock())
    monkeypatch.setattr(main_mod.app_lifecycle, "initialize_tools_with_default_fallback", MagicMock())
    monkeypatch.setattr(moves_mod, "MovementManager", MagicMock())
    monkeypatch.setattr("reachy_mini_conversation_app.config.resolve_app_timeout_minutes", lambda: None)
    monkeypatch.setattr("reachy_mini_conversation_app.settings_store.load_settings_into_runtime", MagicMock())
    monkeypatch.setattr(main_mod.time, "sleep", MagicMock())
    stream_factory = MagicMock()
    monkeypatch.setattr(console_mod, "LocalStream", stream_factory)
    main_mod.run(Namespace(debug=False, ui=False, no_camera=True, robot_name=None), robot=MagicMock())
    initial = stream_factory.call_args.args[0]
    factory = stream_factory.call_args.kwargs["handler_factory"]
    replacement = factory(None)
    assert isinstance(
        initial, main_mod.GeminiRealtimeHandler if provider == "gemini" else main_mod.HuggingFaceRealtimeHandler
    )
    assert replacement.session_state is initial.session_state


def test_inactivity_timeout_thread_goes_to_sleep() -> None:
    """The watchdog should use the shared sleep shutdown path once activity is too old."""
    stream_manager = SimpleNamespace(seconds_since_activity=lambda: 10.0, close=MagicMock())
    go_to_sleep = MagicMock(return_value={"status": "sleeping"})

    thread = main_mod._start_inactivity_timeout_thread(
        timeout_minutes=0.0001,
        stream_manager=stream_manager,
        logger=MagicMock(),
        app_stop_event=threading.Event(),
        go_to_sleep=go_to_sleep,
    )

    thread.join(timeout=1.0)
    assert not thread.is_alive()
    go_to_sleep.assert_called_once_with()
    stream_manager.close.assert_not_called()


def test_inactivity_timeout_thread_closes_stream_manager_without_sleep_callback() -> None:
    """The watchdog should still close the stream when no sleep callback is available."""
    stream_manager = SimpleNamespace(seconds_since_activity=lambda: 10.0, close=MagicMock())

    thread = main_mod._start_inactivity_timeout_thread(
        timeout_minutes=0.0001,
        stream_manager=stream_manager,
        logger=MagicMock(),
        app_stop_event=threading.Event(),
    )

    thread.join(timeout=1.0)
    assert not thread.is_alive()
    stream_manager.close.assert_called_once_with()
