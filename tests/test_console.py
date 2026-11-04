"""Tests for the headless console stream."""

import time
import asyncio
import threading
from types import SimpleNamespace
from typing import Any
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from collections.abc import Callable, Iterator

import httpx
import numpy as np
import pytest
from fastapi import FastAPI, Request, HTTPException
from numpy.typing import NDArray
from fastapi.testclient import TestClient
from test_gemini_credentials import FakeVault

import reachy_mini_conversation_app.console as console_mod
from reachy_mini_conversation_app.config import HF_AVAILABLE_VOICES, config
from reachy_mini_conversation_app.console import LocalStream
from reachy_mini_conversation_app.prompts import get_session_instructions
from reachy_mini_conversation_app.streaming import AdditionalOutputs
from reachy_mini_conversation_app.settings_store import read_settings
from reachy_mini_conversation_app.gemini_realtime import GeminiRealtimeHandler
from reachy_mini_conversation_app.startup_settings import (
    StartupSettings,
    load_startup_settings_into_runtime,
)
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.gemini_credentials import CredentialError, GeminiCredentials
from reachy_mini_conversation_app.personality_routes import (
    RouteError,
    build_personality_ops,
)
from reachy_mini_conversation_app.conversation_handler import ConversationHandler
from reachy_mini_conversation_app.huggingface_realtime import ToolInvocation, HuggingFaceRealtimeHandler


CredentialClient = tuple[TestClient, LocalStream, GeminiCredentials, FakeVault]


def _rpc_call(app: FastAPI, method: str, params: Any = None) -> dict[str, Any]:
    """Send one JSON-RPC request over /rpc and return the response envelope."""
    with TestClient(app).websocket_connect("/rpc") as ws:
        ws.send_json({"jsonrpc": "2.0", "id": "1", "method": method, "params": params or {}})
        return ws.receive_json()


async def _wait_until(predicate: Any, timeout: float = 1.0) -> None:
    """Wait until a test predicate becomes true."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Timed out waiting for condition")


def test_gemini_selection_preserves_hf_and_rejects_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Persist explicit provider selection without accepting credentials."""
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", "huggingface")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "private-token")
    app = FastAPI()
    stream = LocalStream(
        MagicMock(),
        MagicMock(),
        settings_app=app,
        instance_path=str(tmp_path),
        handler_factory=lambda _voice: MagicMock(),
    )
    stream._init_settings_ui_if_needed()
    result = _rpc_call(app, "backend.config", {"backend": "gemini", "gemini_voice": "Kore"})
    assert result["result"]["backend"] == "gemini"
    assert result["result"]["gemini_key_configured"] is True
    assert "private-token" not in str(result)
    assert read_settings(str(tmp_path)).conversation_backend == "gemini"
    error = _rpc_call(app, "backend.config", {"backend": "gemini", "api_key": "forbidden"})
    assert error["error"]["code"] == -32602


def test_retry_requests_coalesce_without_new_handlers() -> None:
    """Repeated Retry requests use the existing scheduler."""
    app = FastAPI()
    factory = MagicMock()
    stream = LocalStream(MagicMock(), MagicMock(), settings_app=app, handler_factory=factory)
    stream._init_settings_ui_if_needed()
    assert _rpc_call(app, "backend.retry")["result"]["ok"]
    assert _rpc_call(app, "backend.retry")["result"]["ok"]
    assert stream._retry_requested.is_set()
    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["huggingface", "gemini"])
async def test_ten_recoverable_attempts_share_capped_schedule(provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both providers retry indefinitely with the same capped backoff."""
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", provider)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(console_mod, "has_hf_realtime_target", lambda: True)
    monkeypatch.setattr(console_mod, "get_tool_specs", lambda: [])
    monkeypatch.setattr(console_mod, "get_session_instructions", lambda _path: "personality")
    handler = MagicMock(
        connection=None, start_up=AsyncMock(side_effect=ConnectionError("raw-secret")), shutdown=AsyncMock()
    )
    stream = LocalStream(handler, MagicMock())
    delays: list[float | None] = []

    async def wait(delay: float | None) -> None:
        delays.append(delay)
        if len(delays) == 10:
            stream._stop_event.set()

    monkeypatch.setattr(stream, "_sleep_or_restart_requested", wait)
    await stream._run_handler_startup_loop()
    assert delays == [1, 2, 4, 8, 16, 30, 30, 30, 30, 30]
    assert "raw-secret" not in str(stream._backend_connection_status())


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["huggingface", "gemini"])
async def test_permanent_failure_waits_for_manual_correction(
    provider: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Authentication failures do not create an automatic retry schedule."""
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", provider)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(console_mod, "has_hf_realtime_target", lambda: True)
    request = httpx.Request("GET", "https://service.invalid")
    error = (
        httpx.HTTPStatusError("private-api-key", request=request, response=httpx.Response(401, request=request))
        if provider == "huggingface"
        else console_mod.GeminiConnectionError("authentication_failed", recoverable=False)
    )
    handler = MagicMock(
        connection=None,
        shutdown=AsyncMock(),
        start_up=AsyncMock(side_effect=error),
    )
    stream = LocalStream(handler, MagicMock())
    waits: list[float | None] = []

    async def wait(delay: float | None) -> None:
        waits.append(delay)
        stream._stop_event.set()

    monkeypatch.setattr(stream, "_sleep_or_restart_requested", wait)
    await stream._run_handler_startup_loop()
    assert waits == [None]
    assert stream._backend_connection_state == "waiting_for_config"
    assert stream._retry_attempt == 0
    assert "private-api-key" not in caplog.text


@pytest.mark.asyncio
async def test_missing_gemini_key_preserves_configuration_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unconfigured saved selection waits without touching the paid transport."""
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    app = FastAPI()
    handler = MagicMock(connection=None, start_up=AsyncMock(), shutdown=AsyncMock())
    stream = LocalStream(handler, MagicMock(), settings_app=app)
    stream._init_settings_ui_if_needed()

    async def wait(_delay: float | None) -> None:
        stream._stop_event.set()

    monkeypatch.setattr(stream, "_sleep_or_restart_requested", wait)
    await stream._run_handler_startup_loop()
    handler.start_up.assert_not_called()
    status = _rpc_call(app, "status.get")["result"]
    assert status["backend"] == "gemini" and status["backend_error_reason"] == "missing_gemini_key"
    assert status["backend_connection_state"] == "waiting_for_config"
    assert _rpc_call(app, "backend.config", {"backend": "huggingface"})["result"]["ok"]


@pytest.mark.asyncio
async def test_slow_cleanup_cannot_keep_ownership_or_freeze_switching(monkeypatch: pytest.MonkeyPatch) -> None:
    """The owner retires a socket before abandoning cleanup at its deadline."""
    released = asyncio.Event()

    async def slow_shutdown() -> None:
        try:
            await released.wait()
        except asyncio.CancelledError:
            await released.wait()

    handler = MagicMock(shutdown=slow_shutdown)
    stream = LocalStream(handler, MagicMock())
    previous_generation = stream.session_state.generation
    stream.session_state.invocations["running"] = ToolInvocation("move_head", "running")
    monkeypatch.setattr(console_mod, "CLOSE_TIMEOUT_S", 0.01)
    try:
        await asyncio.wait_for(stream._shutdown_active_handler(), timeout=0.2)
        assert stream.session_state.generation > previous_generation
        assert any("結果不明" in str(event) for event in stream._conversation_history)
    finally:
        released.set()
        await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["huggingface", "gemini"])
async def test_only_completed_exchange_resets_retry_delay(provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Replacement handlers retain backoff until one acknowledged exchange completes."""
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", provider)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(console_mod, "has_hf_realtime_target", lambda: True)
    monkeypatch.setattr(console_mod, "get_tool_specs", lambda: [])
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    attempt = 0

    def factory(_voice: str | None):
        handler = GeminiRealtimeHandler(deps) if provider == "gemini" else HuggingFaceRealtimeHandler(deps)

        async def start() -> None:
            nonlocal attempt
            attempt += 1
            handler.connection = MagicMock(close=AsyncMock())
            if isinstance(handler, GeminiRealtimeHandler):
                handler._ready = True
            if attempt == 3:
                handler.notify_exchange_completed()
            raise ConnectionError("simulated connection loss")

        monkeypatch.setattr(handler, "start_up", start)
        return handler

    stream = LocalStream(factory(None), MagicMock(), handler_factory=factory)
    delays: list[float | None] = []

    async def wait(delay: float | None) -> None:
        delays.append(delay)
        if len(delays) == 4:
            stream._stop_event.set()

    monkeypatch.setattr(stream, "_sleep_or_restart_requested", wait)
    await stream._run_handler_startup_loop()
    assert delays == [1, 2, 1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["huggingface", "gemini"])
async def test_owner_setup_budget_expires_at_fifteen_seconds(provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The owner bounds an unacknowledged transport without terminating the settings loop."""
    loop = asyncio.get_running_loop()
    elapsed = [loop.time()]
    monkeypatch.setattr(loop, "time", lambda: elapsed[0])
    monkeypatch.setattr(console_mod, "time", SimpleNamespace(monotonic=lambda: elapsed[0], time=time.time))
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", provider)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(console_mod, "has_hf_realtime_target", lambda: True)
    started = asyncio.Event()

    async def silent_setup() -> None:
        started.set()
        await asyncio.Event().wait()

    handler = MagicMock(connection=None, start_up=silent_setup, shutdown=AsyncMock())
    stream = LocalStream(handler, MagicMock())
    delays: list[float | None] = []

    async def wait(delay: float | None) -> None:
        delays.append(delay)
        stream._stop_event.set()

    monkeypatch.setattr(stream, "_sleep_or_restart_requested", wait)
    task = asyncio.create_task(stream._run_handler_startup_loop())
    try:
        await started.wait()
        elapsed[0] += 14.9
        for _step in range(10):
            await asyncio.sleep(0)
        assert not task.done()
        elapsed[0] += 0.2
        for _step in range(40):
            await asyncio.sleep(0)
        assert task.done()
        await task
        assert stream._backend_error_reason == "setup_timeout" and delays == [1]
        assert stream.session_state.generation > 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_ten_switches_and_rapid_requests_keep_one_media_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switching and coalesced requests never let a retired handler regain media ownership."""
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", "huggingface")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(console_mod, "has_hf_realtime_target", lambda: True)
    monkeypatch.setattr(console_mod, "get_tool_specs", lambda: [])
    state = console_mod.RealtimeSessionState()
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    handlers = []
    started: asyncio.Queue[HuggingFaceRealtimeHandler | GeminiRealtimeHandler] = asyncio.Queue()
    ownership_counts: list[int] = []
    motion_clears_at_start: list[int] = []

    def factory(_voice: str | None):
        handler = (
            GeminiRealtimeHandler(deps, session_state=state)
            if config.CONVERSATION_BACKEND == "gemini"
            else HuggingFaceRealtimeHandler(deps, session_state=state)
        )
        handlers.append(handler)

        async def start() -> None:
            handler.connection = MagicMock(close=AsyncMock())
            if isinstance(handler, GeminiRealtimeHandler):
                handler._ready = True
            ownership_counts.append(
                sum(active._owns_connection() and active.connection is not None for active in handlers)
            )
            motion_clears_at_start.append(deps.movement_manager.clear_move_queue.call_count)
            started.put_nowait(handler)
            try:
                await asyncio.Event().wait()
            finally:
                handler.connection = None

        monkeypatch.setattr(handler, "start_up", start)
        return handler

    stream = LocalStream(factory(None), MagicMock(), handler_factory=factory, tool_deps=deps)
    monitor = asyncio.create_task(stream._run_handler_startup_loop())
    try:
        current = await asyncio.wait_for(started.get(), 1)
        for index in range(10):
            previous = current
            config.CONVERSATION_BACKEND = "gemini" if index % 2 == 0 else "huggingface"
            await stream.request_backend_restart("provider_selected")
            current = await asyncio.wait_for(started.get(), 1)
            assert motion_clears_at_start[-1] == index + 1
            assert not previous._owns_connection() and current._owns_connection()
            assert current.session_state is state
            previous._emit_transcript("assistant", "private old-session fragment", True)
            stream._retry_attempt = 7
            previous.notify_exchange_completed()
            assert stream._retry_attempt == 7
        config.CONVERSATION_BACKEND = "gemini"
        await asyncio.gather(*(stream.request_backend_restart("rapid_selection") for _request in range(10)))
        await _wait_until(lambda: isinstance(stream.handler, GeminiRealtimeHandler) and stream._backend_connected())
        assert deps.movement_manager.clear_move_queue.call_count == 11
        assert max(ownership_counts) == 1
        assert all(not handler._owns_connection() for handler in handlers if handler is not stream.handler)
        assert "private old-session fragment" not in str(stream._conversation_history)
    finally:
        stream._stop_event.set()
        monitor.cancel()
        await stream._shutdown_active_handler()
        await asyncio.gather(monitor, return_exceptions=True)


@pytest.mark.asyncio
async def test_manual_retry_and_shutdown_cancel_pending_waits() -> None:
    """Repeated Retry signals expedite one wait; shutdown cancels an indefinite wait."""
    stream = LocalStream(MagicMock(), MagicMock())
    waiting = asyncio.create_task(stream._sleep_or_restart_requested(30))
    await asyncio.sleep(0)
    stream._retry_requested.set()
    stream._retry_requested.set()
    await asyncio.wait_for(waiting, 1)
    assert not stream._retry_requested.is_set()
    following = asyncio.create_task(stream._sleep_or_restart_requested(None))
    await asyncio.sleep(0)
    assert not following.done()
    stream._stop_event.set()
    await asyncio.wait_for(following, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["model", "voice", "profile", "tools", "memory"])
async def test_changed_configuration_never_reuses_checkpoint(changed: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every prompt or provider revision invalidates the retained checkpoint before replacement setup."""
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config, "GEMINI_MODEL", "gemini-3.8-live")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", None)
    instructions = ["personality"]
    specs: list[dict[str, object]] = []
    monkeypatch.setattr(console_mod, "get_tool_specs", lambda: specs)
    monkeypatch.setattr(console_mod, "get_session_instructions", lambda _path: instructions[0])
    state = console_mod.RealtimeSessionState(provider="gemini")
    initial_id = state.logical_session_id
    observed: list[str | None] = []
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())

    def factory(_voice: str | None):
        handler = GeminiRealtimeHandler(deps, session_state=state)

        async def start() -> None:
            observed.append(state.resumption_handle)
            state.resumption_handle = "private-checkpoint"
            state.resumable = True
            raise ConnectionError("simulated loss")

        monkeypatch.setattr(handler, "start_up", start)
        return handler

    stream = LocalStream(factory(None), MagicMock(), handler_factory=factory)

    async def wait(_delay: float | None) -> None:
        if len(observed) == 2:
            stream._stop_event.set()
        elif changed == "model":
            config.GEMINI_MODEL = "gemini-next-live"
        elif changed == "voice":
            config.GEMINI_VOICE_OVERRIDE = "Puck"
        elif changed == "profile":
            config.REACHY_MINI_CUSTOM_PROFILE = "new-profile"
            instructions[0] = "new personality"
        elif changed == "tools":
            specs.append(
                {"name": "move_head", "type": "function", "description": "Move", "parameters": {"type": "object"}}
            )
        else:
            instructions[0] = "personality with changed saved memories"

    monkeypatch.setattr(stream, "_sleep_or_restart_requested", wait)
    await stream._run_handler_startup_loop()
    assert observed == [None, None]
    assert state.logical_session_id != initial_id


@pytest.mark.asyncio
async def test_retired_cleanup_cannot_abort_replacement_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """A delayed close belongs to its captured transport even after a new handler is installed."""
    loop = asyncio.get_running_loop()
    elapsed = [loop.time()]
    monkeypatch.setattr(loop, "time", lambda: elapsed[0])
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    old = HuggingFaceRealtimeHandler(deps)
    old_socket = MagicMock()
    old.connection = old_socket
    closing = asyncio.Event()
    released = asyncio.Event()
    old_socket._connection.transport.abort.side_effect = released.set

    async def close() -> None:
        closing.set()
        try:
            await released.wait()
        except asyncio.CancelledError:
            await released.wait()

    monkeypatch.setattr(old, "shutdown", close)
    stream = LocalStream(old, MagicMock())
    cleanup = asyncio.create_task(stream._shutdown_active_handler())
    replacement = None
    try:
        await closing.wait()
        replacement = GeminiRealtimeHandler(deps, session_state=stream.session_state)
        replacement_socket = MagicMock(close=AsyncMock())
        replacement.connection = replacement_socket
        replacement._ready = True
        stream._install_handler(replacement)
        elapsed[0] += 5.1
        for _step in range(40):
            await asyncio.sleep(0)
        assert cleanup.done()
        await cleanup
        old_socket._connection.transport.abort.assert_called_once()
        replacement_socket.transport.abort.assert_not_called()
        assert replacement._is_connected()
    finally:
        released.set()
        cleanup.cancel()
        await asyncio.gather(cleanup, return_exceptions=True)
        if replacement is not None:
            await replacement.shutdown()


def test_retired_observers_cannot_publish_or_retain_old_fragments() -> None:
    """Replacing the handler invalidates every captured notification callback."""
    old = MagicMock()
    stream = LocalStream(old, MagicMock())
    transcript = old.set_transcript_observer.call_args.args[0]
    latency = old.set_latency_observer.call_args.args[0]
    vad = old.set_vad_observer.call_args.args[0]
    interrupted = old.transcript_interrupted
    completed = old.exchange_completed
    stream._rpc = MagicMock()
    stream._install_handler(MagicMock())
    stream._retry_attempt = 4
    transcript("assistant", "prior-provider-live-fragment", True)
    latency({"e2e_ms": 10})
    vad({})
    interrupted()
    completed()
    assert stream._retry_attempt == 4
    assert not stream._conversation_history
    stream._rpc.broadcast_threadsafe.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["revision", "factory"])
async def test_local_setup_failure_keeps_status_and_selection_available(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed local configuration cannot terminate the recovery/settings owner."""
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", "huggingface")
    monkeypatch.setattr(console_mod, "has_hf_realtime_target", lambda: True)
    app = FastAPI()
    stream = LocalStream(
        MagicMock(connection=None, shutdown=AsyncMock()),
        MagicMock(),
        settings_app=app,
        handler_factory=lambda _voice: MagicMock(),
    )
    stream._init_settings_ui_if_needed()

    def invalid() -> None:
        raise ValueError("private malformed configuration")

    if failure == "revision":
        monkeypatch.setattr(console_mod, "get_tool_specs", invalid)
    else:
        stream._restart_requested.set()
        monkeypatch.setattr(stream, "_build_handler_for_current_backend", invalid)

    async def wait(delay: float | None) -> None:
        assert delay is None
        stream._stop_event.set()

    monkeypatch.setattr(stream, "_sleep_or_restart_requested", wait)
    await stream._run_handler_startup_loop()
    status = _rpc_call(app, "status.get")["result"]
    assert status["backend_connection_state"] == "waiting_for_config"
    assert "private malformed configuration" not in str(status)


@pytest.mark.asyncio
async def test_clear_audio_queue_flushes_the_sdk_player() -> None:
    """clear_player() flushes SDK playback and the pending output is dropped."""
    handler = MagicMock()
    handler.output_queue = asyncio.Queue()
    handler.output_queue.put_nowait((24000, np.zeros(4, dtype=np.int16)))
    audio = SimpleNamespace(clear_player=MagicMock())
    robot = SimpleNamespace(media=SimpleNamespace(audio=audio))
    stream = LocalStream(handler, robot)

    await stream.clear_audio_queue()

    audio.clear_player.assert_called_once()
    assert handler.output_queue.empty()


@pytest.mark.asyncio
async def test_clear_audio_queue_drains_queue_in_place() -> None:
    """The output queue is drained in place, not replaced with a new object."""
    handler = MagicMock()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    queue.put_nowait((24000, np.zeros(4, dtype=np.int16)))
    queue.put_nowait((24000, np.zeros(4, dtype=np.int16)))
    handler.output_queue = queue
    audio = SimpleNamespace(clear_player=MagicMock())
    robot = SimpleNamespace(media=SimpleNamespace(audio=audio))
    stream = LocalStream(handler, robot)

    await stream.clear_audio_queue()

    assert handler.output_queue is queue  # same object, not replaced
    assert queue.empty()


def test_mic_reports_and_toggles_mute_state_over_rpc() -> None:
    """The mic starts live; conversation.mic exposes and flips the pause state."""
    app = FastAPI()
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(MagicMock(), robot, settings_app=app)
    stream._init_settings_ui_if_needed()

    assert _rpc_call(app, "conversation.mic")["result"] == {"muted": False}
    assert _rpc_call(app, "conversation.mic", {"muted": True})["result"] == {"muted": True}
    assert stream._mic_muted is True
    assert _rpc_call(app, "conversation.mic", {"muted": False})["result"] == {"muted": False}
    assert stream._mic_muted is False

    # headless streams keep the mic live
    assert LocalStream(MagicMock(), robot)._mic_muted is False


def test_rest_api_is_removed_in_favor_of_rpc() -> None:
    """The /api/v1 REST + SSE surface is gone; control is JSON-RPC over /rpc."""
    app = FastAPI()
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(MagicMock(), robot, settings_app=app)
    stream._init_settings_ui_if_needed()
    client = TestClient(app)

    for path in (
        "/api/v1/status",
        "/api/v1/mic",
        "/api/v1/personalities",
        "/api/v1/voices",
        "/api/v1/tool_spaces",
        "/api/v1/profile_tools",
    ):
        assert client.get(path).status_code == 404
    assert client.get("/api/v1/conversation_events").status_code == 404

    # ...but /rpc drives it fine.
    assert _rpc_call(app, "conversation.status")["result"]["backend"]


def test_settings_ui_detaches_framework_catch_all_before_own_routes() -> None:
    """Framework fallback routes should not shadow the UI or the /rpc endpoint."""
    app = FastAPI()

    @app.get("/{path:path}")
    def _framework_fallback(path: str) -> None:
        raise HTTPException(status_code=404)

    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(MagicMock(), robot, settings_app=app)
    stream._init_settings_ui_if_needed()
    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.get("/static/js/api.js").status_code == 200
    assert _rpc_call(app, "conversation.status")["result"]["backend"]


@pytest.mark.asyncio
async def test_activity_from_rebuilt_handler_reaches_rpc_clients() -> None:
    """Activity from a rebuilt handler must still reach /rpc subscribers."""

    class FakeHandler:
        set_vad_observer = MagicMock()

        def __init__(self) -> None:
            """Initialize the connection state."""
            self.observer: Any = None

        def set_activity_observer(self, observer: Any) -> None:
            self.observer = observer

    rebuilt = FakeHandler()
    app = FastAPI()
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(FakeHandler(), robot, settings_app=app, handler_factory=lambda voice: rebuilt)
    stream._init_settings_ui_if_needed()
    stream._build_handler_for_current_backend()  # rebuild re-wires the observer

    with TestClient(app).websocket_connect("/rpc") as ws:
        rebuilt.observer("assistant_audio_delta")
        # First frame is conversation.activity (raw reason).
        msg = ws.receive_json()
    assert msg["method"] == "conversation.activity"
    assert msg["params"] == {"reason": "assistant_audio_delta"}


def test_backend_config_requests_in_process_restart_with_handler_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rebuild-capable LocalStream should reconnect in process after a connection change."""
    monkeypatch.setattr(config, "HF_REALTIME_CONNECTION_MODE", "deployed")
    monkeypatch.setattr(config, "HF_REALTIME_WS_URL", None)
    monkeypatch.delenv("HF_REALTIME_CONNECTION_MODE", raising=False)
    monkeypatch.delenv("HF_REALTIME_WS_URL", raising=False)

    app = FastAPI()
    handler = MagicMock()
    handler.shutdown = AsyncMock()
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(
        handler,
        robot,
        settings_app=app,
        instance_path=str(tmp_path),
        handler_factory=lambda _voice: handler,
    )
    stream._init_settings_ui_if_needed()

    data = _rpc_call(app, "backend.config", {"hf_mode": "local", "hf_host": "localhost", "hf_port": 8765})["result"]

    assert data["ok"] is True
    assert data["message"] == "連線已儲存，正在重新連接後端。"
    assert data["backend"] == "huggingface"
    assert data["requires_restart"] is False
    assert data["can_proceed"] is True
    assert data["backend_connection_state"] == "connecting"
    assert stream._restart_requested.is_set()


def test_backend_config_persists_local_hf_selection_and_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings API should persist a direct Hugging Face websocket target."""
    monkeypatch.setattr(config, "HF_REALTIME_CONNECTION_MODE", "deployed")
    monkeypatch.setattr(config, "HF_REALTIME_SESSION_URL", None)
    monkeypatch.setattr(config, "HF_REALTIME_WS_URL", None)
    monkeypatch.delenv("HF_REALTIME_CONNECTION_MODE", raising=False)
    monkeypatch.delenv("HF_REALTIME_SESSION_URL", raising=False)
    monkeypatch.delenv("HF_REALTIME_WS_URL", raising=False)

    app = FastAPI()
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(MagicMock(), robot, settings_app=app, instance_path=str(tmp_path))
    stream._init_settings_ui_if_needed()

    data = _rpc_call(app, "backend.config", {"hf_mode": "local", "hf_host": "localhost", "hf_port": 8765})["result"]

    assert data["ok"] is True
    assert data["backend"] == "huggingface"
    assert data["has_hf_ws_url"] is True
    assert data["has_hf_connection"] is True
    assert data["hf_connection_mode"] == "local"
    assert data["hf_direct_host"] == "localhost"
    assert data["hf_direct_port"] == 8765

    stored = read_settings(tmp_path)
    assert stored.hf_connection_mode == "local"
    assert stored.hf_ws_url == "ws://localhost:8765/v1/realtime"


def test_language_saved_for_one_profile_then_for_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A profile language overrides the shared one until a language is saved for all personalities."""
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", "sorry_bro")
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", "en")
    monkeypatch.setattr(config, "PROFILE_LANGUAGES", {"chess_coach": "de"})
    app = FastAPI()
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(MagicMock(), robot, settings_app=app, instance_path=str(tmp_path))
    stream._init_settings_ui_if_needed()

    result = _rpc_call(app, "language.set", {"language": "fr", "scope": "profile"})["result"]

    assert (result["language"], result["default_language"], result["profile_language"]) == ("fr", "en", "fr")
    assert read_settings(tmp_path).profile_languages == {"chess_coach": "de", "sorry_bro": "fr"}
    assert _rpc_call(app, "conversation.status")["result"]["language"] == "fr"

    result = _rpc_call(app, "language.set", {"language": "es", "scope": "all"})["result"]

    assert (result["language"], result["default_language"], result["profile_language"]) == ("es", "es", None)
    stored = read_settings(tmp_path)
    assert (stored.language, stored.profile_languages) == ("es", {})
    assert config.PROFILE_LANGUAGES == {}


def test_backend_config_persists_deployed_mode_without_clearing_local_hf_ws_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Saving deployed mode should make env selection explicit and remove stale allocator URLs."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "HF_REALTIME_SESSION_URL=https://lb.example.test/session\n"
        "HF_REALTIME_WS_URL=ws://localhost:8765/v1/realtime\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config, "HF_REALTIME_CONNECTION_MODE", "deployed")
    monkeypatch.setattr(config, "HF_REALTIME_SESSION_URL", "https://lb.example.test/session")
    monkeypatch.setattr(config, "HF_REALTIME_WS_URL", "ws://localhost:8765/v1/realtime")
    monkeypatch.delenv("HF_REALTIME_CONNECTION_MODE", raising=False)
    monkeypatch.setenv("HF_REALTIME_SESSION_URL", "https://lb.example.test/session")
    monkeypatch.setenv("HF_REALTIME_WS_URL", "ws://localhost:8765/v1/realtime")

    app = FastAPI()
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(MagicMock(), robot, settings_app=app, instance_path=str(tmp_path))
    stream._init_settings_ui_if_needed()

    data = _rpc_call(app, "backend.config", {"hf_mode": "deployed"})["result"]

    assert data["ok"] is True
    assert data["has_hf_session_url"] is True
    assert data["has_hf_ws_url"] is True
    assert data["hf_connection_mode"] == "deployed"

    assert read_settings(tmp_path).hf_connection_mode == "deployed"
    env_text = env_path.read_text(encoding="utf-8")
    assert "HF_REALTIME_SESSION_URL=" not in env_text
    assert "HF_REALTIME_WS_URL=ws://localhost:8765/v1/realtime" in env_text


def test_backend_config_switches_to_saved_local_hf_connection_without_payload_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switching back to a saved local Hugging Face backend should reuse the persisted target."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "HF_REALTIME_CONNECTION_MODE=local\nHF_REALTIME_WS_URL=ws://192.168.1.42:8766/v1/realtime\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config, "HF_REALTIME_CONNECTION_MODE", "local")
    monkeypatch.setattr(config, "HF_REALTIME_SESSION_URL", None)
    monkeypatch.setattr(config, "HF_REALTIME_WS_URL", "ws://192.168.1.42:8766/v1/realtime")
    monkeypatch.setenv("HF_REALTIME_CONNECTION_MODE", "local")
    monkeypatch.setenv("HF_REALTIME_WS_URL", "ws://192.168.1.42:8766/v1/realtime")

    app = FastAPI()
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(MagicMock(), robot, settings_app=app, instance_path=str(tmp_path))
    stream._init_settings_ui_if_needed()

    data = _rpc_call(app, "backend.config", {})["result"]

    assert data["ok"] is True
    assert data["backend"] == "huggingface"
    assert data["hf_connection_mode"] == "local"
    assert data["hf_direct_host"] == "192.168.1.42"
    assert data["hf_direct_port"] == 8766

    env_text = env_path.read_text(encoding="utf-8")
    assert "HF_REALTIME_CONNECTION_MODE=local" in env_text
    assert "HF_REALTIME_WS_URL=ws://192.168.1.42:8766/v1/realtime" in env_text


def test_backend_config_rejects_invalid_hf_port_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings API should reject invalid local Hugging Face ports from direct callers."""
    monkeypatch.setattr(config, "HF_REALTIME_CONNECTION_MODE", "deployed")
    monkeypatch.setattr(config, "HF_REALTIME_SESSION_URL", None)
    monkeypatch.setattr(config, "HF_REALTIME_WS_URL", None)

    app = FastAPI()
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(MagicMock(), robot, settings_app=app, instance_path=str(tmp_path))
    stream._init_settings_ui_if_needed()

    resp = _rpc_call(
        app,
        "backend.config",
        {"backend": "huggingface", "hf_mode": "local", "hf_host": "localhost", "hf_port": 0},
    )

    assert resp["error"]["data"]["reason"] == "invalid_hf_port"


def test_status_reports_direct_hf_ws_url_as_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings API should treat a direct Hugging Face websocket as a valid configuration."""
    monkeypatch.setattr(config, "HF_REALTIME_CONNECTION_MODE", "local")
    monkeypatch.setattr(config, "HF_REALTIME_SESSION_URL", None)
    monkeypatch.setattr(config, "HF_REALTIME_WS_URL", "ws://127.0.0.1:8765/v1/realtime")

    app = FastAPI()
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(MagicMock(), robot, settings_app=app, instance_path=str(tmp_path))
    stream._init_settings_ui_if_needed()

    data = _rpc_call(app, "conversation.status")["result"]

    assert data["backend"] == "huggingface"
    assert data["has_hf_session_url"] is False
    assert data["has_hf_ws_url"] is True
    assert data["has_hf_connection"] is True
    assert data["hf_connection_mode"] == "local"
    assert data["can_proceed_with_hf"] is True


def test_status_reports_backend_connection_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings API should expose backend connection failures without hiding controls."""
    monkeypatch.setattr(config, "HF_REALTIME_CONNECTION_MODE", "local")
    monkeypatch.setattr(config, "HF_REALTIME_SESSION_URL", None)
    monkeypatch.setattr(config, "HF_REALTIME_WS_URL", "ws://127.0.0.1:8765/v1/realtime")

    app = FastAPI()
    handler = MagicMock()
    handler.connection = None
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(handler, robot, settings_app=app, instance_path=str(tmp_path))
    stream._set_backend_connection_state("disconnected", RuntimeError("connect failed"))
    stream._init_settings_ui_if_needed()

    data = _rpc_call(app, "conversation.status")["result"]
    assert data["backend"] == "huggingface"
    assert data["backend_connected"] is False
    assert data["backend_connection_state"] == "disconnected"
    assert data["backend_error"] == "後端連線失敗，請檢查設定後重試。"
    assert data["can_proceed"] is True
    assert data["can_proceed_with_hf"] is True


def test_backend_startup_failure_is_recorded_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backend startup failures should become status state instead of killing LocalStream."""
    monkeypatch.setattr(config, "HF_REALTIME_CONNECTION_MODE", "local")
    monkeypatch.setattr(config, "HF_REALTIME_SESSION_URL", None)
    monkeypatch.setattr(config, "HF_REALTIME_WS_URL", "ws://127.0.0.1:8765/v1/realtime")

    app = FastAPI()
    handler = MagicMock()
    handler.connection = None
    handler.shutdown = AsyncMock()
    media = SimpleNamespace(
        audio=None,
        backend=None,
        start_recording=MagicMock(),
        start_playing=MagicMock(),
    )
    robot = SimpleNamespace(media=media)
    stream = LocalStream(handler, robot, settings_app=app, instance_path=str(tmp_path))
    stream._backend_retry_delay = 0
    stream.record_loop = AsyncMock(return_value=None)  # type: ignore[method-assign]
    stream.play_loop = AsyncMock(return_value=None)  # type: ignore[method-assign]
    monkeypatch.setattr("reachy_mini_conversation_app.console.apply_audio_startup_config", MagicMock())

    async def fail_and_stop() -> None:
        stream._stop_event.set()
        raise RuntimeError("local server unavailable")

    handler.start_up = AsyncMock(side_effect=fail_and_stop)

    try:
        stream.launch()
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())

    handler.start_up.assert_awaited_once()
    data = _rpc_call(app, "conversation.status")["result"]
    assert data["backend_connected"] is False
    assert data["backend_connection_state"] == "disconnected"
    assert data["backend_error"] == "後端連線失敗，請檢查設定後重試。"


def test_media_warmup_overlaps_audio_startup_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audio configuration should run while the media pipelines warm up."""
    monkeypatch.setattr("reachy_mini_conversation_app.console.has_hf_realtime_target", lambda: True)

    handler = MagicMock()
    handler.shutdown = AsyncMock()
    media = SimpleNamespace(
        audio=None,
        backend=None,
        start_recording=MagicMock(),
        start_playing=MagicMock(),
    )
    stream = LocalStream(handler, SimpleNamespace(media=media))
    stream.record_loop = AsyncMock(return_value=None)  # type: ignore[method-assign]
    stream.play_loop = AsyncMock(return_value=None)  # type: ignore[method-assign]

    startup_barrier = threading.Barrier(2)

    async def wait_for_audio_config(_delay: float) -> None:
        await asyncio.to_thread(startup_barrier.wait, 5.0)

    def apply_audio_config(*_args: Any, **_kwargs: Any) -> bool:
        startup_barrier.wait(5.0)
        return True

    async def start_and_stop() -> None:
        stream._stop_event.set()

    handler.start_up = AsyncMock(side_effect=start_and_stop)
    monkeypatch.setattr("reachy_mini_conversation_app.console.asyncio.sleep", wait_for_audio_config)
    monkeypatch.setattr("reachy_mini_conversation_app.console.apply_audio_startup_config", apply_audio_config)

    try:
        stream.launch()
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())


def test_launch_closes_network_stream_without_callback_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conversation shutdown closes sockets without leaking event-loop callback errors."""
    monkeypatch.setattr(console_mod, "has_hf_realtime_target", lambda: True)
    monkeypatch.setattr(console_mod, "apply_audio_startup_config", MagicMock())
    media = SimpleNamespace(start_recording=MagicMock(), start_playing=MagicMock())
    stream = LocalStream(MagicMock(shutdown=AsyncMock()), SimpleNamespace(media=media))
    loop_policy = asyncio.get_event_loop_policy()
    errors: list[dict[str, object]] = []

    async def close_peer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readexactly(1)
        finally:
            writer.close()
            await writer.wait_closed()

    async def connect_and_stop() -> None:
        loop = asyncio.get_running_loop()

        def report_error(loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
            errors.append(context)
            loop.default_exception_handler(context)

        loop.set_exception_handler(report_error)
        server = await asyncio.start_server(close_peer, "127.0.0.1", 0)
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
            try:
                writer.write(b"x")
                await writer.drain()
                assert await asyncio.wait_for(reader.read(), 2) == b""
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            server.close()
            await asyncio.wait_for(server.wait_closed(), 2)
            stream._stop_event.set()

    monkeypatch.setattr(stream, "_run_handler_startup_loop", connect_and_stop)
    monkeypatch.setattr(stream, "record_loop", AsyncMock())
    monkeypatch.setattr(stream, "play_loop", AsyncMock())
    try:
        stream.launch()
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())

    assert not errors
    assert asyncio.get_event_loop_policy() is loop_policy


def test_launch_reads_microphone_while_audio_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The microphone is drained during audio configuration, so no backlog builds up before live input."""
    monkeypatch.setattr(console_mod, "has_hf_realtime_target", lambda: True)
    configuring = threading.Event()
    read_while_configuring = threading.Event()

    def read_microphone() -> None:
        if configuring.is_set():
            read_while_configuring.set()

    def configure_audio(*_args: object, **_kwargs: object) -> None:
        configuring.set()
        read_while_configuring.wait(1)
        stream.close()

    media = SimpleNamespace(
        audio=None,
        backend=None,
        start_recording=MagicMock(),
        start_playing=MagicMock(),
        stop_recording=MagicMock(),
        stop_playing=MagicMock(),
        get_input_audio_samplerate=MagicMock(return_value=16000),
        get_audio_sample=read_microphone,
    )
    stream = LocalStream(MagicMock(shutdown=AsyncMock()), SimpleNamespace(media=media))
    monkeypatch.setattr(stream, "_run_handler_startup_loop", AsyncMock())
    monkeypatch.setattr(console_mod, "apply_audio_startup_config", configure_audio)
    try:
        stream.launch()
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())

    assert read_while_configuring.is_set()


@pytest.mark.asyncio
async def test_record_loop_preserves_samples_while_receive_yields() -> None:
    """Short receive delays must not remove connected microphone samples or change their order."""
    chunks = [np.full((160, 2), index, dtype=np.int16) for index in range(10)]
    pending_chunks = iter(chunks)
    received: list[NDArray[np.int16]] = []

    def read_microphone() -> NDArray[np.int16] | None:
        chunk = next(pending_chunks, None)
        if chunk is None:
            time.sleep(0.001)
        return chunk

    async def receive(frame: tuple[int, NDArray[np.int16]]) -> None:
        await asyncio.sleep(0.01)
        assert frame[0] == 16000
        received.append(frame[1].copy())

    handler = MagicMock(connection=object(), receive=AsyncMock(side_effect=receive))
    robot = _audio_robot(get_input_audio_samplerate=MagicMock(return_value=16000), get_audio_sample=read_microphone)
    stream = LocalStream(handler, robot)
    recording = asyncio.create_task(stream.record_loop())
    try:
        await _wait_until(lambda: sum(chunk.shape[0] for chunk in received) == 1600)
    finally:
        stream._stop_event.set()
        await asyncio.wait_for(recording, timeout=2)

    np.testing.assert_array_equal(np.concatenate(received), np.concatenate(chunks))


@pytest.mark.asyncio
async def test_pending_microphone_audio_does_not_survive_a_mute_toggle() -> None:
    """A quick mute/unmute discards audio captured before the mute boundary."""
    first_received = threading.Event()
    old_audio_read = threading.Event()
    allow_current_audio = threading.Event()
    read_count = 0
    delivered: list[NDArray[np.int16]] = []
    app = FastAPI()

    def read_microphone() -> NDArray[np.int16]:
        nonlocal read_count
        read_count += 1
        if read_count == 1:
            return np.full(160, 1, dtype=np.int16)
        if read_count == 2:
            first_received.wait(1)
            return np.full(160, 2, dtype=np.int16)
        old_audio_read.set()
        allow_current_audio.wait(1)
        time.sleep(0.001)
        return np.full(160, 3, dtype=np.int16)

    async def receive(frame: tuple[int, NDArray[np.int16]]) -> None:
        delivered.append(frame[1].copy())
        if len(delivered) == 1:
            first_received.set()
            assert await asyncio.to_thread(old_audio_read.wait, 1)
            for request_id, muted in enumerate((True, False)):
                websocket.send_json(
                    {"jsonrpc": "2.0", "id": request_id, "method": "conversation.mic", "params": {"muted": muted}}
                )
                assert websocket.receive_json()["result"]["muted"] is muted
            allow_current_audio.set()
        else:
            stream._stop_event.set()

    handler = MagicMock(connection=object(), receive=AsyncMock(side_effect=receive))
    robot = _audio_robot(get_input_audio_samplerate=MagicMock(return_value=16000), get_audio_sample=read_microphone)
    stream = LocalStream(handler, robot, settings_app=app)
    stream._init_settings_ui_if_needed()
    with TestClient(app) as client, client.websocket_connect("/rpc") as websocket:
        recording = asyncio.create_task(stream.record_loop())
        try:
            await asyncio.wait_for(recording, timeout=3)
        finally:
            first_received.set()
            allow_current_audio.set()
            stream._stop_event.set()
            if not recording.done():
                await recording

    assert len(delivered) == 2
    assert np.all(delivered[0] == 1)
    assert np.all(delivered[1] == 3)


@pytest.mark.asyncio
async def test_record_loop_discards_warmup_audio() -> None:
    """Frames read while the audio board warms up never reach the handler."""
    warmup_frame = np.full(4, 1, dtype=np.int16)
    live_frame = np.full(4, 2, dtype=np.int16)
    reads: list[bool] = []
    handler = MagicMock()
    robot = _audio_robot(get_input_audio_samplerate=MagicMock(return_value=16000), get_audio_sample=MagicMock())
    stream = LocalStream(handler, robot)
    stream._audio_warming_up = True

    def read_microphone() -> np.ndarray:
        reads.append(stream._audio_warming_up)
        return warmup_frame if stream._audio_warming_up else live_frame

    robot.media.get_audio_sample.side_effect = read_microphone
    handler.connection = object()
    handler.receive = AsyncMock(side_effect=lambda _frame: stream._stop_event.set())
    recording = asyncio.create_task(stream.record_loop())
    while len(reads) < 2 and not recording.done():
        await asyncio.sleep(0)
    stream._audio_warming_up = False
    await asyncio.wait_for(recording, timeout=2)

    handler.receive.assert_awaited_once()
    delivered_samples = handler.receive.await_args.args[0][1]
    assert delivered_samples.size > 0
    assert np.all(delivered_samples == 2)


@pytest.mark.asyncio
async def test_startup_loop_rebuilds_handler_on_restart_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """LocalStream should shut down and rebuild the handler when a restart is requested."""
    monkeypatch.setattr(config, "HF_REALTIME_CONNECTION_MODE", "local")
    monkeypatch.setattr(config, "HF_REALTIME_SESSION_URL", None)
    monkeypatch.setattr(config, "HF_REALTIME_WS_URL", "ws://127.0.0.1:8765/v1/realtime")

    class FakeHandler:
        set_vad_observer = MagicMock()

        def __init__(self) -> None:
            """Initialize the connection state."""
            self.connection = None
            self.output_queue = asyncio.Queue()
            self.started = asyncio.Event()
            self.stopped = asyncio.Event()
            self.shutdown_calls = 0

        async def start_up(self) -> None:
            self.connection = object()
            self.started.set()
            await self.stopped.wait()
            self.connection = None

        async def shutdown(self) -> None:
            self.shutdown_calls += 1
            self.stopped.set()

        async def receive(self, _frame: Any) -> None:
            return None

        async def emit(self) -> None:
            return None

    handlers: list[FakeHandler] = []

    def handler_factory(_voice: str | None) -> FakeHandler:
        handler = FakeHandler()
        handlers.append(handler)
        return handler

    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    initial_handler = handler_factory(None)
    stream = LocalStream(initial_handler, robot, handler_factory=handler_factory)
    stream._backend_retry_delay = 0.01

    startup_task = asyncio.create_task(stream._run_handler_startup_loop())
    try:
        await _wait_until(lambda: initial_handler.started.is_set())

        await stream.request_backend_restart("backend_config_changed")

        await _wait_until(lambda: len(handlers) == 2 and handlers[1].started.is_set())

        assert initial_handler.shutdown_calls >= 1
        assert stream.handler is handlers[1]
        assert stream._backend_connected() is True
    finally:
        stream._stop_event.set()
        await stream._shutdown_active_handler()
        startup_task.cancel()
        try:
            await startup_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_personality_ops_return_hf_voices() -> None:
    """With no running loop, voices() falls back to the Hugging Face catalog."""
    ops = build_personality_ops(MagicMock(), lambda: None)
    assert await ops.voices() == HF_AVAILABLE_VOICES


def test_personality_ops_delete_builtin_is_not_deletable() -> None:
    """Deleting a built-in personality raises not_deletable (was REST 404)."""
    ops = build_personality_ops(MagicMock(), lambda: None)
    with pytest.raises(RouteError) as ei:
        ops.delete("mad_scientist_assistant")
    assert ei.value.reason == "not_deletable"


def test_personality_ops_load_builtin_default_profile() -> None:
    """The bulk personality API should retain the complete profile payload."""
    ops = build_personality_ops(MagicMock(), lambda: None)
    data = ops.load("default")
    assert "Reachy Mini" in data["instructions"]
    assert data["tools_text"]
    assert data["enabled_tools"]
    assert data["available_tools"]


@pytest.mark.asyncio
async def test_personality_ops_apply_voice() -> None:
    """apply_voice delegates to the handler and reports the status."""
    handler = MagicMock()
    handler.change_voice = AsyncMock(return_value="Voice changed to cedar.")
    ops = build_personality_ops(handler, lambda: asyncio.get_running_loop())

    result = await ops.apply_voice("cedar")

    assert result == {"ok": True, "status": "Voice changed to cedar."}
    handler.change_voice.assert_awaited_once_with("cedar")


@pytest.mark.asyncio
async def test_personality_ops_persist_startup_with_voice_override() -> None:
    """Applying with persist=True saves the active manual voice override."""
    handler = MagicMock()
    handler.apply_personality = AsyncMock(return_value="Applied personality and restarted realtime session.")
    handler.get_current_voice = MagicMock(return_value="shimmer")
    persist_personality = MagicMock()
    ops = build_personality_ops(handler, lambda: asyncio.get_running_loop(), persist_personality=persist_personality)

    result = await ops.apply("sorry_bro", persist=True)

    assert result["ok"] is True
    handler.apply_personality.assert_awaited_once_with("sorry_bro")
    persist_personality.assert_called_once_with("sorry_bro", "shimmer")


@pytest.mark.asyncio
async def test_personality_ops_apply_same_profile_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-applying the active personality is a no-op for the realtime handler."""
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", "sorry_bro")
    handler = MagicMock()
    handler.apply_personality = AsyncMock(return_value="should not be called")
    handler.get_current_voice = MagicMock(return_value="shimmer")
    ops = build_personality_ops(handler, lambda: None)

    result = await ops.apply("sorry_bro")

    assert result["status"] == "人格未變更。"
    handler.apply_personality.assert_not_awaited()
    handler.get_current_voice.assert_not_called()


def test_personality_ops_startup_choice_survives_runtime_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime profile switching should not redefine the saved startup personality."""
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", "captain_circuit")
    ops = build_personality_ops(MagicMock(), lambda: None)

    first = ops.get_choices()
    assert first["current"] == "captain_circuit"
    assert first["startup"] == "captain_circuit"

    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", "chess_coach")

    second = ops.get_choices()
    assert second["current"] == "chess_coach"
    assert second["startup"] == "captain_circuit"


@pytest.mark.asyncio
async def test_personality_ops_use_apply_callback() -> None:
    """Apply delegates to the injected apply_personality callback, not the handler."""
    handler = MagicMock()
    handler.apply_personality = AsyncMock(return_value="handler should not be called")
    apply_personality = AsyncMock(return_value="Applied personality and restarting backend.")
    get_current_voice = MagicMock(return_value="cedar")
    ops = build_personality_ops(
        handler,
        lambda: asyncio.get_running_loop(),
        apply_personality=apply_personality,
        get_current_voice=get_current_voice,
    )

    result = await ops.apply("sorry_bro")

    assert result["status"] == "Applied personality and restarting backend."
    apply_personality.assert_awaited_once_with("sorry_bro")
    handler.apply_personality.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_personality_propagates_restart_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancellation during backend restart should not be converted into a status string."""
    monkeypatch.setattr(console_mod, "set_custom_profile", lambda _profile: None)
    monkeypatch.setattr(console_mod, "get_session_instructions", lambda _instance_path=None: "instructions")
    monkeypatch.setattr(console_mod, "get_session_voice", lambda default: default)

    stream = LocalStream(MagicMock(), MagicMock())

    async def cancel_restart(_reason: str) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(stream, "request_backend_restart", cancel_restart)

    with pytest.raises(asyncio.CancelledError):
        await stream.apply_personality("sorry_bro")


@pytest.mark.asyncio
async def test_apply_personality_restores_profile_when_tool_initialization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed tool rebuild must not leave the rejected profile selected."""
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", "default")
    monkeypatch.setattr(
        console_mod,
        "set_custom_profile",
        lambda profile: setattr(config, "REACHY_MINI_CUSTOM_PROFILE", profile),
    )
    monkeypatch.setattr(console_mod, "get_session_instructions", lambda: "instructions")
    monkeypatch.setattr(console_mod, "get_session_voice", lambda default: default)
    monkeypatch.setattr(console_mod, "initialize_tools", MagicMock(side_effect=RuntimeError("invalid tools")))
    stream = LocalStream(MagicMock(), MagicMock())

    with pytest.raises(RuntimeError, match="invalid tools"):
        await stream.apply_personality("broken")

    assert config.REACHY_MINI_CUSTOM_PROFILE == "default"


@pytest.mark.asyncio
async def test_local_stream_change_voice_delegates_without_backend_restart() -> None:
    """LocalStream voice changes should update the active handler without rebuilding it."""
    handler = MagicMock()
    handler.change_voice = AsyncMock(return_value="Voice changed to Serena.")
    handler.get_current_voice = MagicMock(return_value="Serena")
    stream = LocalStream(handler, MagicMock())

    status = await stream.change_voice("Serena")

    assert status == "Voice changed to Serena."
    handler.change_voice.assert_awaited_once_with("Serena")
    assert stream._voice_override == "Serena"
    assert not stream._restart_requested.is_set()


def test_local_stream_persist_personality_stores_voice_override(tmp_path) -> None:
    """Persisting startup settings should write both profile and voice override."""
    stream = LocalStream(MagicMock(), MagicMock(), instance_path=str(tmp_path))

    stream._persist_personality("sorry_bro", "shimmer")

    settings_path = tmp_path / "startup_settings.json"
    assert settings_path.exists()
    assert settings_path.read_text(encoding="utf-8") == '{\n  "profile": "sorry_bro",\n  "voice": "shimmer"\n}\n'
    assert stream._read_persisted_personality() == "sorry_bro"


def test_local_stream_persist_personality_clears_legacy_startup_env_overrides(tmp_path, monkeypatch) -> None:
    """Saving startup settings should remove legacy `.env` profile and voice overrides."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "HF_TOKEN=test-token\n"
        "REACHY_MINI_CUSTOM_PROFILE=mad_scientist_assistant\n"
        "REACHY_MINI_VOICE_OVERRIDE=shimmer\n",
        encoding="utf-8",
    )
    stream = LocalStream(MagicMock(), MagicMock(), instance_path=str(tmp_path))

    stream._persist_personality(None, "Aiden")

    env_text = env_path.read_text(encoding="utf-8")
    assert "HF_TOKEN=test-token" in env_text
    assert "REACHY_MINI_CUSTOM_PROFILE=" not in env_text
    assert "REACHY_MINI_VOICE_OVERRIDE=" not in env_text

    applied_profiles: list[str | None] = []
    monkeypatch.delenv("REACHY_MINI_CUSTOM_PROFILE", raising=False)
    monkeypatch.setattr(
        "reachy_mini_conversation_app.config.set_custom_profile",
        lambda profile: applied_profiles.append(profile),
    )

    settings = load_startup_settings_into_runtime(tmp_path)

    assert settings == StartupSettings(voice="Aiden")
    assert applied_profiles == [None]


def test_local_stream_launch_waits_for_missing_hf_target_without_starting_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup should wait for settings input when the Hugging Face target is missing."""
    monkeypatch.setattr(config, "HF_REALTIME_CONNECTION_MODE", "local")
    monkeypatch.setattr(config, "HF_REALTIME_SESSION_URL", None)
    monkeypatch.setattr(config, "HF_REALTIME_WS_URL", None)

    media = SimpleNamespace(
        start_recording=MagicMock(),
        start_playing=MagicMock(),
    )
    robot = SimpleNamespace(media=media)
    stream = LocalStream(MagicMock(), robot, settings_app=FastAPI(), instance_path=str(tmp_path))

    init_settings_ui = MagicMock()
    monkeypatch.setattr(stream, "_init_settings_ui_if_needed", init_settings_ui)
    monkeypatch.setattr("reachy_mini_conversation_app.console.time.sleep", MagicMock(side_effect=KeyboardInterrupt))

    stream.launch()

    init_settings_ui.assert_called_once()
    media.start_recording.assert_not_called()
    media.start_playing.assert_not_called()


def _bare_stream() -> LocalStream:
    """Return a LocalStream with a no-audio robot, enough for helper-method tests."""
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    return LocalStream(MagicMock(), robot)


def test_seconds_since_activity_reads_handler() -> None:
    """seconds_since_activity is measured from the handler's last activity time."""
    stream = _bare_stream()
    stream.handler.last_activity_time = time.monotonic() - 5.0

    assert stream.seconds_since_activity() >= 5.0


def test_get_current_voice_prefers_override() -> None:
    """A manual voice override wins over the profile voice."""
    stream = _bare_stream()
    stream._voice_override = "Serena"

    assert stream.get_current_voice() == "Serena"


@pytest.mark.asyncio
async def test_change_voice_reports_handler_failure() -> None:
    """A failing handler voice change is surfaced as an error string, not raised."""
    handler = MagicMock()
    handler.change_voice = AsyncMock(side_effect=RuntimeError("backend down"))
    robot = SimpleNamespace(media=SimpleNamespace(audio=None, backend=None))
    stream = LocalStream(handler, robot)

    result = await stream.change_voice("Serena")

    assert "變更聲音失敗" in result


def _audio_robot(**media_attrs: Any) -> SimpleNamespace:
    """Return a robot whose media exposes only the attributes a test drives."""
    media_attrs.setdefault("get_output_audio_samplerate", MagicMock())
    return SimpleNamespace(media=SimpleNamespace(audio=None, backend=None, **media_attrs))


def _stop_after(stream: LocalStream, value: Any) -> Callable[[], Any]:
    """Return a side effect that stops the stream after one iteration, yielding `value`."""

    def _side_effect() -> Any:
        stream._stop_event.set()
        return value

    return _side_effect


@pytest.mark.asyncio
async def test_record_loop_forwards_unmuted_frames() -> None:
    """A recorded frame is forwarded to the handler with the input sample rate."""
    frame = np.zeros(4, dtype=np.int16)
    recorded = [frame]
    robot = _audio_robot(
        get_input_audio_samplerate=MagicMock(return_value=16000),
        get_audio_sample=lambda: recorded.pop() if recorded else None,
    )
    handler = MagicMock()
    stream = LocalStream(handler, robot)
    handler.connection = object()
    handler.receive = AsyncMock(side_effect=lambda _frame: stream._stop_event.set())

    await asyncio.wait_for(stream.record_loop(), timeout=2)

    handler.receive.assert_awaited_once_with((16000, frame))


@pytest.mark.asyncio
async def test_record_loop_skips_frames_while_muted() -> None:
    """No frames are forwarded while the mic is muted."""
    robot = _audio_robot(get_input_audio_samplerate=MagicMock(return_value=16000), get_audio_sample=MagicMock())
    handler = MagicMock()
    handler.receive = AsyncMock()
    stream = LocalStream(handler, robot)
    stream._mic_muted = True
    robot.media.get_audio_sample.side_effect = _stop_after(stream, np.zeros(4, dtype=np.int16))

    await stream.record_loop()

    handler.receive.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_loop_skips_missing_frames() -> None:
    """A None frame from the recorder is not forwarded."""
    robot = _audio_robot(get_input_audio_samplerate=MagicMock(return_value=16000), get_audio_sample=MagicMock())
    handler = MagicMock()
    handler.receive = AsyncMock()
    stream = LocalStream(handler, robot)
    robot.media.get_audio_sample.side_effect = _stop_after(stream, None)

    await stream.record_loop()

    handler.receive.assert_not_awaited()


@pytest.mark.asyncio
async def test_play_loop_logs_text_outputs() -> None:
    """Text outputs are logged, not pushed to the speaker."""
    robot = _audio_robot(push_audio_sample=MagicMock())
    handler = MagicMock()
    stream = LocalStream(handler, robot)
    output = AdditionalOutputs({"role": "assistant", "content": "hi"})
    handler.emit = AsyncMock(side_effect=_stop_after(stream, output))

    await stream.play_loop()

    robot.media.push_audio_sample.assert_not_called()


@pytest.mark.asyncio
async def test_play_loop_pushes_mono_audio_as_float32() -> None:
    """A mono int16 frame is pushed to the speaker as float32."""
    robot = _audio_robot(push_audio_sample=MagicMock())
    handler = MagicMock()
    handler.playback_ready = asyncio.Event()
    handler.playback_ready.set()
    stream = LocalStream(handler, robot)
    handler.playback_frame_epochs = {}
    handler.emit = AsyncMock(side_effect=_stop_after(stream, (24000, np.zeros(4, dtype=np.int16))))

    await stream.play_loop()

    robot.media.push_audio_sample.assert_called_once()
    pushed = robot.media.push_audio_sample.call_args.args[0]
    assert pushed.ndim == 1
    assert pushed.dtype == np.float32


@pytest.mark.asyncio
async def test_play_loop_downmixes_stereo_before_pushing() -> None:
    """A stereo frame is reduced to a single mono channel before playback."""
    robot = _audio_robot(push_audio_sample=MagicMock())
    handler = MagicMock()
    handler.playback_ready = asyncio.Event()
    handler.playback_ready.set()
    stream = LocalStream(handler, robot)
    stereo = np.zeros((4, 2), dtype=np.int16)
    handler.playback_frame_epochs = {}
    handler.emit = AsyncMock(side_effect=_stop_after(stream, (24000, stereo)))

    await stream.play_loop()

    pushed = robot.media.push_audio_sample.call_args.args[0]
    assert pushed.ndim == 1


@pytest.mark.asyncio
async def test_play_loop_skips_empty_audio() -> None:
    """An empty audio frame is skipped, not pushed."""
    robot = _audio_robot(push_audio_sample=MagicMock())
    handler = MagicMock()
    stream = LocalStream(handler, robot)
    handler.playback_frame_epochs = {}
    handler.emit = AsyncMock(side_effect=_stop_after(stream, (24000, np.array([], dtype=np.int16))))

    await stream.play_loop()

    robot.media.push_audio_sample.assert_not_called()


def test_close_without_running_loop_stops_media() -> None:
    """Closing without a running loop stops the media pipelines and sets the stop event."""
    robot = _audio_robot(stop_recording=MagicMock(), stop_playing=MagicMock())
    stream = LocalStream(MagicMock(), robot)
    stream._asyncio_loop = None

    stream.close()

    robot.media.stop_recording.assert_called_once()
    robot.media.stop_playing.assert_called_once()
    assert stream._stop_event.is_set()


def test_drain_output_queue_empties_in_place() -> None:
    """The output queue is drained without being replaced."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    queue.put_nowait((16000, np.zeros(512, dtype=np.int16)))
    queue.put_nowait((16000, np.zeros(512, dtype=np.int16)))
    handler = MagicMock()
    handler.output_queue = queue
    stream = LocalStream(handler, _audio_robot())

    stream._drain_output_queue()

    assert stream.handler.output_queue is queue
    assert queue.empty()


def test_drain_output_queue_tolerates_missing_queue() -> None:
    """Draining is a no-op when the handler has no output queue."""
    handler = MagicMock()
    handler.output_queue = None
    stream = LocalStream(handler, _audio_robot())

    stream._drain_output_queue()  # must not raise


def _rpc_robot() -> SimpleNamespace:
    """Return a robot mock whose audio pipeline supports clear_audio_queue()."""
    audio = SimpleNamespace(clear_player=MagicMock())
    return SimpleNamespace(media=SimpleNamespace(audio=audio))


def test_rpc_status_and_mic_over_websocket() -> None:
    """conversation.status/mic are reachable over the /rpc JSON-RPC WebSocket."""
    app = FastAPI()
    stream = LocalStream(MagicMock(), _rpc_robot(), settings_app=app)
    stream._init_settings_ui_if_needed()
    client = TestClient(app)
    with client.websocket_connect("/rpc") as ws:
        ws.send_json({"jsonrpc": "2.0", "id": "1", "method": "conversation.status"})
        resp = ws.receive_json()
        assert resp["id"] == "1"
        assert "result" in resp

        ws.send_json({"jsonrpc": "2.0", "id": "2", "method": "conversation.mic", "params": {"muted": True}})
        resp = ws.receive_json()
        assert resp["result"] == {"muted": True}
    assert stream._mic_muted is True


def test_rpc_interrupt_broadcasts_turn_listening() -> None:
    """conversation.interrupt cancels the response and pushes a turn:listening event."""
    handler = MagicMock()
    handler.output_queue = asyncio.Queue()
    handler._is_connected.return_value = True
    handler.interrupt = AsyncMock()
    app = FastAPI()
    stream = LocalStream(handler, _rpc_robot(), settings_app=app)
    stream._init_settings_ui_if_needed()
    with TestClient(app).websocket_connect("/rpc") as ws:
        ws.send_json({"jsonrpc": "2.0", "id": "1", "method": "conversation.interrupt"})
        msgs = [ws.receive_json(), ws.receive_json()]
    results = [m for m in msgs if "result" in m]
    notes = [m for m in msgs if m.get("method") == "conversation.turn"]
    assert results and results[0]["result"] == {"ok": True}
    assert notes and notes[0]["params"] == {"state": "listening", "reason": "interrupted"}
    handler.interrupt.assert_awaited_once()


def test_rpc_say_requires_active_session() -> None:
    """conversation.say fails with not_running when no session is connected."""
    handler = MagicMock()
    handler._is_connected.return_value = False
    app = FastAPI()
    stream = LocalStream(handler, _rpc_robot(), settings_app=app)
    stream._init_settings_ui_if_needed()
    with TestClient(app).websocket_connect("/rpc") as ws:
        ws.send_json({"jsonrpc": "2.0", "id": "1", "method": "conversation.say", "params": {"text": "hi"}})
        resp = ws.receive_json()
    assert resp["error"]["data"]["reason"] == "not_running"


def test_rpc_transcript_notification_broadcast() -> None:
    """The handler's transcript observer pushes conversation.transcript events."""
    app = FastAPI()
    stream = LocalStream(MagicMock(), _rpc_robot(), settings_app=app)
    stream._init_settings_ui_if_needed()
    with TestClient(app).websocket_connect("/rpc") as ws:
        stream._dispatch_transcript("assistant", "hello there", True)
        msg = ws.receive_json()
    assert msg["method"] == "conversation.transcript"
    assert isinstance(msg["params"].pop("seq"), int)
    assert msg["params"] == {"role": "assistant", "text": "hello there", "final": True}


def test_rpc_latency_notification_broadcast() -> None:
    """The handler's latency observer pushes conversation.latency events."""
    handler = MagicMock()
    app = FastAPI()
    stream = LocalStream(handler, _rpc_robot(), settings_app=app)
    stream._init_settings_ui_if_needed()
    latency_observer = handler.set_latency_observer.call_args.args[0]
    latency: dict[str, int | str | None] = {
        "stt_ms": 210,
        "llm_ms": 480,
        "tts_ttfa_ms": 100,
        "e2e_ms": None,
        "status": "completed",
    }
    with TestClient(app).websocket_connect("/rpc") as ws:
        latency_observer(latency)
        msg = ws.receive_json()
    assert msg["method"] == "conversation.latency"
    assert isinstance(msg["params"].pop("seq"), int)
    assert msg["params"] == latency


def test_rpc_conversation_history_replays_final_events() -> None:
    """conversation.history returns this run's final transcripts and latencies in order, without partials."""
    handler = MagicMock()
    app = FastAPI()
    stream = LocalStream(handler, _rpc_robot(), settings_app=app)
    stream._init_settings_ui_if_needed()
    transcript_observer = handler.set_transcript_observer.call_args.args[0]
    latency_observer = handler.set_latency_observer.call_args.args[0]
    # Emitted before any page connects, like the startup greeting.
    transcript_observer("assistant", "Hi, I'm Reachy!", True)
    transcript_observer("user", "Hel", False)
    transcript_observer("user", "Hello", True)
    latency_observer({"e2e_ms": 900, "status": "completed"})

    with TestClient(app).websocket_connect("/rpc") as ws:
        ws.send_json({"jsonrpc": "2.0", "id": "1", "method": "conversation.history"})
        events = ws.receive_json()["result"]["events"]

    seqs = [event["params"].pop("seq") for event in events]
    assert seqs == sorted(set(seqs))
    assert events == [
        {
            "method": "conversation.transcript",
            "params": {"role": "assistant", "text": "Hi, I'm Reachy!", "final": True},
        },
        {"method": "conversation.transcript", "params": {"role": "user", "text": "Hello", "final": True}},
        {"method": "conversation.latency", "params": {"e2e_ms": 900, "status": "completed"}},
    ]


def test_rpc_settings_methods() -> None:
    """Personality, voice, and tool settings are reachable over /rpc."""
    app = FastAPI()
    stream = LocalStream(MagicMock(), _rpc_robot(), settings_app=app)
    stream._init_settings_ui_if_needed()
    with TestClient(app).websocket_connect("/rpc") as ws:
        ws.send_json({"jsonrpc": "2.0", "id": "1", "method": "personalities.list"})
        r1 = ws.receive_json()
        ws.send_json({"jsonrpc": "2.0", "id": "2", "method": "voices.list"})
        r2 = ws.receive_json()
        ws.send_json({"jsonrpc": "2.0", "id": "3", "method": "tool_spaces.list"})
        r3 = ws.receive_json()
        ws.send_json({"jsonrpc": "2.0", "id": "4", "method": "profile_tools.get"})
        r4 = ws.receive_json()
    assert "choices" in r1["result"] and "current" in r1["result"]
    assert isinstance(r2["result"], list)
    assert "spaces" in r3["result"]
    assert "enabled_tools" in r4["result"]


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, True])
async def test_paced_playback_changes_gain_and_preserves_or_discards_remaining_audio(confirm: bool) -> None:
    """Ducking is reversible; clearing invalidates a partially submitted frame."""
    handler = MagicMock()
    handler.paced_playback = True
    handler.playback_pending_frames = 1
    handler.playback_epoch = 0
    handler.playback_frame_epochs = {}
    handler.playback_gain = 1.0
    handler.playback_ready = asyncio.Event()
    handler.playback_ready.set()
    handler.output_queue = asyncio.Queue()
    frame = np.full(960, 16384, dtype=np.int16)
    handler.emit = AsyncMock(return_value=(16000, frame))
    pushed: list[np.ndarray] = []
    second_chunk = asyncio.Event()
    robot = _audio_robot()
    robot.media.audio = SimpleNamespace(clear_player=MagicMock())
    stream = LocalStream(handler, robot)

    def push(chunk: np.ndarray) -> None:
        pushed.append(chunk.copy())
        if len(pushed) == 1:
            handler.playback_gain = 0.25
        elif len(pushed) == 2:
            handler.playback_gain = 1.0
            if confirm:
                handler.playback_ready.clear()
            second_chunk.set()
        else:
            stream._stop_event.set()

    robot.media.push_audio_sample = push

    playback = asyncio.create_task(stream.play_loop())
    await asyncio.wait_for(second_chunk.wait(), timeout=1)
    if confirm:
        await stream.clear_audio_queue()
        stream._stop_event.set()
    await asyncio.wait_for(playback, timeout=1)
    assert [chunk.size for chunk in pushed] == ([320, 320] if confirm else [320, 320, 320])
    np.testing.assert_array_equal(pushed[0], 0.5)
    np.testing.assert_array_equal(pushed[1], 0.125)
    if not confirm:
        np.testing.assert_array_equal(pushed[2], 0.5)


@pytest.mark.asyncio
async def test_clear_audio_queue_keeps_transcripts_and_does_not_block_event_loop() -> None:
    """A slow SDK flush does not erase metadata or stall microphone/event processing."""
    handler = MagicMock()
    handler.output_queue = asyncio.Queue()
    transcript = AdditionalOutputs({"role": "user", "content": "hello"})
    handler.output_queue.put_nowait(transcript)
    handler.output_queue.put_nowait((16000, np.zeros(512, dtype=np.int16)))
    flush_started = threading.Event()
    release_flush = threading.Event()

    def flush() -> None:
        flush_started.set()
        assert release_flush.wait(timeout=2)

    stream = LocalStream(handler, SimpleNamespace(media=SimpleNamespace(audio=SimpleNamespace(clear_player=flush))))
    clearing = asyncio.create_task(stream.clear_audio_queue())
    try:
        await _wait_until(flush_started.is_set)
        assert not clearing.done()
        assert handler.output_queue.get_nowait() is transcript
        assert handler.output_queue.empty()
    finally:
        release_flush.set()
        await clearing


@pytest.mark.asyncio
@pytest.mark.parametrize("stale", [False, True])
async def test_playback_waiting_during_flush_keeps_only_current_frames(stale: bool) -> None:
    """A flush during emit must reject old audio without dropping the next response's first frame."""
    handler = MagicMock()
    handler.paced_playback = False
    handler.playback_epoch = 0
    handler.playback_frame_epochs = {}
    handler.playback_ready = asyncio.Event()
    handler.output_queue = asyncio.Queue()
    frame = np.ones(320, dtype=np.int16)
    waiting = asyncio.Event()
    release = asyncio.Event()
    robot = _audio_robot(push_audio_sample=MagicMock())
    stream = LocalStream(handler, robot)

    async def emit() -> tuple[int, np.ndarray]:
        waiting.set()
        await release.wait()
        handler.playback_frame_epochs[id(frame)] = 0 if stale else handler.playback_epoch
        stream._stop_event.set()
        return 16000, frame

    handler.emit = emit
    playback = asyncio.create_task(stream.play_loop())
    await asyncio.wait_for(waiting.wait(), timeout=1)
    await stream.clear_audio_queue()
    release.set()
    await asyncio.wait_for(playback, timeout=1)
    assert robot.media.push_audio_sample.call_count == (0 if stale else 1)


@pytest.mark.asyncio
async def test_unpaced_playback_waits_for_flush_to_finish() -> None:
    """Without pacing, a frame of the new epoch is not pushed while the SDK flush is running."""
    flushing = threading.Event()
    release = threading.Event()

    def clear_player() -> None:
        flushing.set()
        assert release.wait(timeout=2)

    pushed: list[np.ndarray] = []
    robot = _audio_robot(push_audio_sample=pushed.append)
    robot.media.audio = SimpleNamespace(clear_player=clear_player)
    handler = MagicMock()
    handler.paced_playback = False
    handler.playback_epoch = 0
    handler.playback_frame_epochs = {}
    handler.playback_ready = asyncio.Event()
    handler.playback_ready.set()
    handler.output_queue = asyncio.Queue()
    stream = LocalStream(handler, robot)
    flush = asyncio.create_task(stream.clear_audio_queue())
    assert await asyncio.to_thread(flushing.wait, 1)

    async def emit() -> tuple[int, np.ndarray]:
        stream._stop_event.set()
        return 16000, np.ones(320, dtype=np.int16)

    handler.emit = emit
    playback = asyncio.create_task(stream.play_loop())
    await asyncio.sleep(0.05)
    assert not pushed
    release.set()
    await asyncio.wait_for(asyncio.gather(flush, playback), timeout=2)
    assert len(pushed) == 1


@pytest.mark.asyncio
async def test_paced_playback_keeps_one_schedule_across_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    """A slow emit between frames is absorbed by the lead instead of pushing later chunks past their slot."""
    clock = [100.0]

    async def fake_sleep(delay: float) -> None:
        clock[0] += max(0.0, delay)

    monkeypatch.setattr(console_mod, "time", SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 123.0))
    monkeypatch.setattr(console_mod.asyncio, "sleep", fake_sleep)
    handler = MagicMock()
    handler.paced_playback = True
    handler.playback_pending_frames = 2
    handler.playback_epoch = 0
    handler.playback_frame_epochs = {}
    handler.playback_gain = 1.0
    handler.playback_ready = asyncio.Event()
    handler.playback_ready.set()
    frames = [(16000, np.ones(3200, dtype=np.int16)) for _ in range(2)]
    push_times: list[float] = []
    robot = _audio_robot(push_audio_sample=lambda _chunk: push_times.append(clock[0]))
    stream = LocalStream(handler, robot)

    async def emit() -> tuple[int, np.ndarray]:
        if not frames:
            stream._stop_event.set()
            return 16000, np.zeros(0, dtype=np.int16)
        if len(frames) == 1:
            clock[0] += 0.05  # slow delta between the two frames
        return frames.pop(0)

    handler.emit = emit
    await stream.play_loop()

    assert len(push_times) == 20
    assert all(pushed <= 100.0 + 0.02 * slot for slot, pushed in enumerate(push_times))
    assert stream._playback_clock == pytest.approx(100.4)


@pytest.mark.asyncio
async def test_paced_playback_continues_while_microphone_read_blocks() -> None:
    """Waiting for the next SDK microphone buffer cannot stall scheduled playback chunks."""
    handler = MagicMock()
    handler.paced_playback = True
    handler.playback_pending_frames = 1
    handler.playback_epoch = 0
    handler.playback_frame_epochs = {}
    handler.playback_gain = 1.0
    handler.playback_ready = asyncio.Event()
    handler.playback_ready.set()
    handler.receive = AsyncMock()
    handler.emit = AsyncMock(return_value=(16000, np.ones(960, dtype=np.int16)))
    read_started = threading.Event()
    release_read = threading.Event()

    def read_microphone() -> None:
        read_started.set()
        assert release_read.wait(timeout=2)

    pushed: list[np.ndarray] = []
    robot = _audio_robot(get_input_audio_samplerate=lambda: 16000, get_audio_sample=read_microphone)
    stream = LocalStream(handler, robot)

    def push(chunk: np.ndarray) -> None:
        pushed.append(chunk)
        if len(pushed) == 3:
            stream._stop_event.set()

    robot.media.push_audio_sample = push
    recording = asyncio.create_task(stream.record_loop())
    playback: asyncio.Task[None] | None = None
    try:
        await _wait_until(read_started.is_set)
        playback = asyncio.create_task(stream.play_loop())
        await asyncio.wait_for(playback, timeout=1)
        assert not recording.done()
        assert [chunk.size for chunk in pushed] == [320, 320, 320]
    finally:
        release_read.set()
        stream._stop_event.set()
        await recording
        if playback is not None:
            await playback


def test_rpc_vad_notification_broadcast() -> None:
    """Local VAD diagnostics reach browser clients through the handler observer."""
    handler = MagicMock()
    app = FastAPI()
    stream = LocalStream(handler, _rpc_robot(), settings_app=app)
    stream._init_settings_ui_if_needed()
    status = {
        "timestamp": 123.0,
        "available": True,
        "probability": 0.8,
        "local_speech": True,
        "server_speech": False,
        "listening": True,
        "barge_in_candidate": True,
        "playback_gain": 0.25,
    }
    observer = handler.set_vad_observer.call_args.args[0]
    with TestClient(app).websocket_connect("/rpc") as ws:
        observer(status)
        notification = ws.receive_json()
    assert notification["method"] == "conversation.vad"
    assert notification["params"] == status


def test_unchanged_speech_setting_keeps_the_conversation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Saving the current speech switch does not reconnect the conversation."""
    monkeypatch.setattr(config, "LOCAL_VAD_ENABLED", True)
    app = FastAPI()
    stream = LocalStream(
        MagicMock(), _rpc_robot(), settings_app=app, instance_path=tmp_path, handler_factory=lambda _voice: MagicMock()
    )
    stream._init_settings_ui_if_needed()
    assert _rpc_call(app, "speech.config", {"local_vad_enabled": True})["result"]["local_vad_enabled"] is True
    assert not stream._restart_requested.is_set()


@pytest.mark.parametrize("local_vad", [False, True])
@pytest.mark.parametrize("barge_in", [False, True])
def test_saved_speech_switches_reconnect_and_control_new_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, local_vad: bool, barge_in: bool
) -> None:
    """Both saved switches reconnect the conversation, survive reload and gate barge-in on the new handler."""
    monkeypatch.setattr(config, "LOCAL_VAD_ENABLED", not local_vad)
    monkeypatch.setattr(config, "LOCAL_BARGE_IN_ENABLED", not barge_in)
    app = FastAPI()
    stream = LocalStream(
        MagicMock(), _rpc_robot(), settings_app=app, instance_path=tmp_path, handler_factory=lambda _voice: MagicMock()
    )
    stream._init_settings_ui_if_needed()
    result = _rpc_call(app, "speech.config", {"local_vad_enabled": local_vad, "local_barge_in_enabled": barge_in})[
        "result"
    ]
    assert result["local_vad_enabled"] is local_vad and result["local_barge_in_enabled"] is barge_in
    assert not result["requires_restart"]
    assert stream._restart_requested.is_set()
    assert _rpc_call(app, "conversation.status")["result"]["local_vad_enabled"] is local_vad
    config.LOCAL_VAD_ENABLED = not local_vad
    config.LOCAL_BARGE_IN_ENABLED = not barge_in
    console_mod.load_settings_into_runtime(tmp_path)
    assert config.LOCAL_VAD_ENABLED is local_vad
    assert config.LOCAL_BARGE_IN_ENABLED is barge_in
    handler = HuggingFaceRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    assert handler.paced_playback is (local_vad and barge_in)


@pytest.mark.parametrize("invalid", ["false", 0, None, []])
@pytest.mark.parametrize("field", ["local_vad_enabled", "local_barge_in_enabled"])
def test_invalid_speech_switch_saves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, invalid: object
) -> None:
    """An invalid switch value leaves both preferences and the live configuration untouched."""
    monkeypatch.setattr(config, "LOCAL_VAD_ENABLED", True)
    monkeypatch.setattr(config, "LOCAL_BARGE_IN_ENABLED", True)
    app = FastAPI()
    stream = LocalStream(MagicMock(), _rpc_robot(), settings_app=app, instance_path=tmp_path)
    stream._init_settings_ui_if_needed()
    params = {"local_vad_enabled": False, "local_barge_in_enabled": False, field: invalid}
    error = _rpc_call(app, "speech.config", params)["error"]
    assert error["data"]["reason"] == "invalid_params"
    assert config.LOCAL_VAD_ENABLED and config.LOCAL_BARGE_IN_ENABLED
    assert read_settings(tmp_path).local_vad_enabled is None
    assert read_settings(tmp_path).local_barge_in_enabled is None
    assert not stream._restart_requested.is_set()


RAW_TRANSCRIPT_CASES = [
    ("user", ["这是服务返回的简体文字。"]),
    ("assistant", ["繁體與简体混合。"]),
    ("user", ["即时", "即时片段", "即时片段完成。"]),
    ("assistant", ["服务正常更", "服务正常更新文字。"]),
    ("assistant", ["原文：‘请保留这个句子。’"]),
    ("user", ["Robot 版本 3.12，数量 42。"]),
    ("assistant", ["https://example.test/路径?q=简体&count=12"]),
    ("assistant", ['<script>window.transcriptExecuted = true</script> `print("简体")`']),
    ("user", [r"C:\测试\文件.txt /tmp/简体.txt"]),
    ("assistant", ["指定名称：小米；memory_id=badge-紫色-01"]),
    ("user", ["你好 123 😊🌟"]),
    ("assistant", ["模型没有遵守偏好，仍返回简体。"]),
]


@pytest.mark.parametrize("role, fragments", RAW_TRANSCRIPT_CASES)
def test_rpc_transcripts_preserve_service_text(role: str, fragments: list[str]) -> None:
    """Live fragments and replayed history retain service text and event identity."""
    app = FastAPI()
    handler = MagicMock()
    stream = LocalStream(handler, _rpc_robot(), settings_app=app)
    stream._init_settings_ui_if_needed()
    with TestClient(app).websocket_connect("/rpc") as websocket:
        sequences = []
        for index, text in enumerate(fragments):
            final = index == len(fragments) - 1
            stream._dispatch_transcript(role, text, final)
            event = websocket.receive_json()
            assert event["method"] == "conversation.transcript"
            params = event["params"]
            if final:
                sequences.append(params.pop("seq"))
            else:
                assert "seq" not in params
            assert params == {"role": role, "text": text, "final": final}
        websocket.send_json({"jsonrpc": "2.0", "id": "history", "method": "conversation.history"})
        history = websocket.receive_json()["result"]["events"]
    assert sequences == sorted(set(sequences))
    assert len(history) == 1
    assert history[0]["params"] == {"role": role, "text": fragments[-1], "final": True, "seq": sequences[-1]}
    handler.generate_response.assert_not_called()


def test_settings_page_declares_traditional_chinese() -> None:
    """The page language describes the fixed UI independently of reply language."""
    app = FastAPI()
    stream = LocalStream(MagicMock(), _rpc_robot(), settings_app=app)
    stream._init_settings_ui_if_needed()
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert '<html lang="zh-Hant">' in response.text


def test_rebuilt_providers_keep_language_policy_and_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider rebuilds resolve profile language without rewriting text or permissions."""
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", "auto")
    monkeypatch.setattr(config, "PROFILE_LANGUAGES", {"default": "zh"})
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", None)
    monkeypatch.setattr(config, "MEMORY_ENABLED", False)
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", "huggingface")
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock(), camera_enabled=False)
    policies: list[str] = []

    def factory(_voice: str | None) -> ConversationHandler:
        policies.append(get_session_instructions())
        if config.CONVERSATION_BACKEND == "gemini":
            return GeminiRealtimeHandler(deps)
        return HuggingFaceRealtimeHandler(deps)

    stream = LocalStream(factory(None), deps.reachy_mini, handler_factory=factory, tool_deps=deps)
    stream._dispatch_transcript("user", "这是未经修改的历史。", True)
    history = list(stream._conversation_history)
    for provider in ("huggingface", "gemini", "gemini", "huggingface"):
        monkeypatch.setattr(config, "CONVERSATION_BACKEND", provider)
        stream._build_handler_for_current_backend()
    assert len(set(policies)) == 1
    assert "Default to Chinese" in policies[0]
    assert "Traditional Chinese" in policies[0]
    assert config.REALTIME_TRANSCRIPTION_LANGUAGE == "auto"
    assert config.PROFILE_LANGUAGES == {"default": "zh"}
    assert list(stream._conversation_history) == history
    assert deps.camera_enabled is False and config.MEMORY_ENABLED is False


@pytest.mark.parametrize(
    "headers,peer",
    [
        ({"host": "evil.local:7860"}, "127.0.0.1"),
        ({"host": "127.0.0.1:7860"}, "192.0.2.1"),
        ({"host": "127.0.0.1:7860", "x-forwarded-for": "127.0.0.1"}, "127.0.0.1"),
        ({"host": "127.0.0.1:7860", "origin": "https://evil.invalid", "sec-fetch-site": "cross-site"}, "127.0.0.1"),
    ],
)
def test_credential_access_rejects_untrusted_requests(headers: dict[str, str], peer: str) -> None:
    """Secret management must not inherit the ordinary RPC's remote access."""
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/api/gemini-credential",
            "headers": [(name.encode(), value.encode()) for name, value in headers.items()],
            "server": ("127.0.0.1", 7860),
            "client": (peer, 1234),
            "query_string": b"",
        }
    )
    with pytest.raises(CredentialError):
        LocalStream._check_credential_request(request)


@pytest.mark.asyncio
async def test_credential_stop_does_not_touch_active_hf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Managing another provider's key does not interrupt HF audio or movements."""
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", "huggingface")
    handler = MagicMock(shutdown=AsyncMock())
    stream = LocalStream(handler, MagicMock())
    generation = stream.session_state.generation
    await stream._stop_gemini_for_credentials()
    assert stream.session_state.generation == generation
    assert not stream._restart_requested.is_set()
    handler.shutdown.assert_not_called()


@pytest.fixture
def credential_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[CredentialClient]:
    """Exercise the real HTTP boundary with isolated storage and no cloud access."""
    vault = FakeVault()
    credentials = GeminiCredentials(tmp_path, "", vault_factory=lambda: vault)
    credentials.initialize()
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", "huggingface")
    monkeypatch.setattr(console_mod, "validate_gemini_candidate", AsyncMock(), raising=False)
    app = FastAPI()
    stream = LocalStream(MagicMock(), MagicMock(), settings_app=app, credentials=credentials)
    stream._init_settings_ui_if_needed()
    with TestClient(app, base_url="http://127.0.0.1:7860", client=("127.0.0.1", 1234)) as client:
        yield client, stream, credentials, vault
    credentials.close()


def test_credential_http_apply_is_redacted_and_preserves_hf(credential_client: CredentialClient) -> None:
    """A local explicit apply preserves HF and exposes only safe status."""
    client, stream, store, _vault = credential_client
    bootstrap = client.get(
        "/api/gemini-credential", headers={"Sec-Fetch-Site": "same-origin", "X-Credential-Request": "1"}
    )
    assert bootstrap.status_code == 200
    payload = bootstrap.json()
    headers = {
        "Origin": "http://127.0.0.1:7860",
        "Sec-Fetch-Site": "same-origin",
        "X-Credential-CSRF": payload["csrf_token"],
    }
    reply = client.post(
        "/api/gemini-credential",
        json={"candidate": "candidate-sentinel", "expected_revision": payload["revision"]},
        headers=headers,
    )
    assert reply.status_code == 200
    assert reply.json()["source"] == "settings"
    assert "sentinel" not in reply.text
    assert not stream._restart_requested.is_set()
    assert store.snapshot().secret == "candidate-sentinel"
    console_mod.validate_gemini_candidate.assert_awaited_once()


@pytest.mark.parametrize("candidate", ["", "   ", 17, None])
def test_credential_http_input_is_not_deletion_or_echo(credential_client: CredentialClient, candidate: object) -> None:
    """Malformed candidates never reach the validator or credential storage."""
    client, _stream, _store, vault = credential_client
    bootstrap = client.get(
        "/api/gemini-credential", headers={"Sec-Fetch-Site": "same-origin", "X-Credential-Request": "1"}
    ).json()
    reply = client.post(
        "/api/gemini-credential",
        json={"candidate": candidate, "expected_revision": bootstrap["revision"]},
        headers={
            "Origin": "http://127.0.0.1:7860",
            "Sec-Fetch-Site": "same-origin",
            "X-Credential-CSRF": bootstrap["csrf_token"],
        },
    )
    assert reply.status_code == 400
    assert "input" not in reply.json()
    assert not vault.entries
    console_mod.validate_gemini_candidate.assert_not_awaited()


def test_credential_page_is_removed_without_restricting_settings(credential_client: CredentialClient) -> None:
    """Remove the old key page while preserving ordinary embedded settings."""
    client, _stream, _store, _vault = credential_client
    for destination in ("document", "iframe"):
        page = client.get("/settings/gemini-key", headers={"Sec-Fetch-Dest": destination})
        assert page.status_code == 404
        assert "location" not in page.headers
    assert client.get("/static/gemini-key.html").status_code == 404
    general = client.get("/", headers={"Sec-Fetch-Dest": "iframe"})
    assert general.status_code == 200
    assert "x-frame-options" not in general.headers
    assert "frame-ancestors" not in general.headers.get("content-security-policy", "")


@pytest.mark.parametrize(
    "header,value",
    [
        ("Origin", "https://evil.invalid"),
        ("Sec-Fetch-Site", "cross-site"),
        ("X-Forwarded-For", "127.0.0.1"),
        ("X-Credential-CSRF", "wrong"),
        ("Content-Type", "text/plain"),
    ],
)
def test_credential_write_refuses_untrusted_origin_or_headers(
    credential_client: CredentialClient, header: str, value: str
) -> None:
    """The secret mutation boundary rejects spoofing before any validation or storage."""
    client, _stream, store, vault = credential_client
    bootstrap = client.get(
        "/api/gemini-credential", headers={"Sec-Fetch-Site": "same-origin", "X-Credential-Request": "1"}
    ).json()
    headers = {
        "Origin": "http://127.0.0.1:7860",
        "Sec-Fetch-Site": "same-origin",
        "Content-Type": "application/json",
        "X-Credential-CSRF": bootstrap["csrf_token"],
        header: value,
    }
    response = client.post(
        "/api/gemini-credential", content='{"candidate":"private-sentinel","expected_revision":0}', headers=headers
    )
    assert response.status_code == 403
    assert "sentinel" not in response.text
    assert store.revision == 0 and not vault.entries
    console_mod.validate_gemini_candidate.assert_not_awaited()


def test_credential_malformed_requests_and_expired_token_are_sanitized(credential_client: CredentialClient) -> None:
    """Oversized and invalid bodies never become reflected input errors."""
    client, stream, store, _vault = credential_client
    boot = client.get(
        "/api/gemini-credential", headers={"Sec-Fetch-Site": "same-origin", "X-Credential-Request": "1"}
    ).json()
    headers = {
        "Origin": "http://127.0.0.1:7860",
        "Sec-Fetch-Site": "same-origin",
        "Content-Type": "application/json",
        "X-Credential-CSRF": boot["csrf_token"],
    }
    bodies = [
        "private-sentinel",
        '{"candidate":"private-sentinel","expected_revision":true}',
        '{"candidate":"private-sentinel","expected_revision":0,"unknown":"secret"}',
        "x" * 17000,
    ]
    for body in bodies:
        response = client.post("/api/gemini-credential", content=body, headers=headers)
        assert response.status_code == 400 and "private-sentinel" not in response.text
    stream._credential_csrf_expires = 0
    assert (
        client.post(
            "/api/gemini-credential", json={"candidate": "private-sentinel", "expected_revision": 0}, headers=headers
        ).status_code
        == 403
    )
    assert store.revision == 0


@pytest.mark.parametrize("provider", ["huggingface", "gemini"])
def test_credential_failure_preserves_setting_and_does_not_resume(
    credential_client: CredentialClient, provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Authentication failure preserves the protected source and leaves affected Gemini stopped."""
    client, stream, store, vault = credential_client
    store.save("original-sentinel", store.begin(0))
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", provider)
    monkeypatch.setattr(
        console_mod,
        "validate_gemini_candidate",
        AsyncMock(side_effect=console_mod.GeminiConnectionError("authentication_failed", recoverable=False)),
    )
    stream.handler.shutdown = AsyncMock()
    boot = client.get(
        "/api/gemini-credential", headers={"Sec-Fetch-Site": "same-origin", "X-Credential-Request": "1"}
    ).json()
    response = client.post(
        "/api/gemini-credential",
        json={"candidate": "candidate-sentinel", "expected_revision": boot["revision"]},
        headers={
            "Origin": "http://127.0.0.1:7860",
            "Sec-Fetch-Site": "same-origin",
            "X-Credential-CSRF": boot["csrf_token"],
        },
    )
    assert response.status_code == 422 and "sentinel" not in response.text
    assert store.snapshot().secret == "original-sentinel" and len(vault.entries) == 1
    assert store.metadata.manual_reconnect_required == (provider == "gemini")
    if provider == "gemini":
        assert not stream._configuration_ready()
    else:
        stream.handler.shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_clear_retires_slow_validation_without_waiting_for_cloud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clear intent closes a pending validation and cannot be overwritten by its result."""
    vault = FakeVault()
    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=lambda: vault)
    store.initialize()
    entered = asyncio.Event()
    closed = asyncio.Event()

    async def slow_validation(*_args: str) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(config, "CONVERSATION_BACKEND", "huggingface")
    monkeypatch.setattr(console_mod, "validate_gemini_candidate", slow_validation)
    stream = LocalStream(MagicMock(), MagicMock(), credentials=store)
    pending = asyncio.create_task(stream._change_credential("late-sentinel", store.begin(0), False))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        clear_revision = store.begin(store.revision, clear=True)
        await asyncio.wait_for(stream._change_credential("", clear_revision, True), timeout=1)
        with pytest.raises(CredentialError, match="superseded"):
            await pending
        assert closed.is_set() and not vault.entries
        assert store.snapshot().secret == "environment-sentinel"
        assert store.revision == clear_revision
        assert store.metadata.manual_reconnect_required
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        store.close()


@pytest.mark.asyncio
async def test_retired_operation_does_not_validate_after_slow_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed intent during owner shutdown retires validation before it reaches the cloud."""
    store = GeminiCredentials(tmp_path, "environment-sentinel", vault_factory=FakeVault)
    store.initialize()
    monkeypatch.setattr(config, "CONVERSATION_BACKEND", "gemini")
    validator = AsyncMock()
    monkeypatch.setattr(console_mod, "validate_gemini_candidate", validator)
    stream = LocalStream(MagicMock(), MagicMock(), credentials=store)
    monkeypatch.setattr(stream, "_stop_gemini_for_credentials", AsyncMock(side_effect=store.invalidate))
    try:
        with pytest.raises(CredentialError, match="superseded"):
            await stream._change_credential("candidate-sentinel", store.begin(0), False)
        validator.assert_not_called()
        assert store.snapshot().secret == "environment-sentinel"
    finally:
        store.close()
