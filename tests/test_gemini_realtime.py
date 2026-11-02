import json
import base64
import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from websockets.frames import Close
from websockets.exceptions import ConnectionClosedError

import reachy_mini_conversation_app.gemini_realtime as gemini
import reachy_mini_conversation_app.huggingface_realtime as realtime
from reachy_mini_conversation_app.tools import core_tools
from reachy_mini_conversation_app.config import config
from reachy_mini_conversation_app.prompts import get_session_instructions
from reachy_mini_conversation_app.streaming import AdditionalOutputs
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.huggingface_realtime import ToolInvocation, RealtimeSessionState


class FakeConnection:
    """Replay remote messages and capture outgoing payloads."""

    def __init__(self, messages: list[object]) -> None:
        """Initialize the connection state."""
        self.messages = iter(messages)
        self.sent: list[dict[str, object]] = []
        self.transport = MagicMock()

    async def send(self, message: str) -> None:
        """Record one outgoing message."""
        self.sent.append(json.loads(message))

    async def recv(self) -> str:
        """Return the next remote message."""
        try:
            return json.dumps(next(self.messages))
        except StopIteration:
            raise ConnectionError("simulated connection loss") from None

    async def close(self) -> None:
        """Close the fake transport."""
        return None


class FakeConnect:
    """Provide a fake websocket connection context."""

    def __init__(self, socket: FakeConnection) -> None:
        """Initialize the connection state."""
        self.socket = socket

    async def __aenter__(self) -> FakeConnection:
        """Return the fake connection."""
        return self.socket

    async def __aexit__(self, *_args: object) -> None:
        """Leave the fake connection context."""
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("language, language_name", [("zh", "Chinese"), ("auto", None), ("fr", "French")])
async def test_language_policy_reaches_gemini_replacement_setup(
    monkeypatch: pytest.MonkeyPatch, language: str, language_name: str | None
) -> None:
    """Replacement connections rebuild the shared policy without changing voice or model."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(config, "LOCAL_VAD_ENABLED", False)
    monkeypatch.setattr(config, "MEMORY_ENABLED", False)
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", None)
    monkeypatch.setattr(config, "PROFILE_LANGUAGES", {})
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", language)
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [])
    setups = []
    for _ in range(2):
        socket = FakeConnection([{"setupComplete": {}}])
        monkeypatch.setattr(gemini, "connect", lambda *_args, **_kwargs: FakeConnect(socket))
        handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
        try:
            with pytest.raises(ConnectionError, match="simulated"):
                await handler.start_up()
            setup = socket.sent[0]["setup"]
            instructions = setup["systemInstruction"]["parts"][0]["text"]
            assert instructions == get_session_instructions()
            assert "When replying in Chinese, prefer Traditional Chinese" in instructions
            assert "Speak only" not in instructions
            if language_name is None:
                assert "Default to " not in instructions
            else:
                assert f"Default to {language_name}" in instructions
            assert "zh-TW" not in json.dumps(setup) and "zh-Hant" not in json.dumps(setup)
            setups.append(setup)
        finally:
            await handler.shutdown()
    assert setups[0] == setups[1]


@pytest.mark.asyncio
async def test_gemini_explicit_language_exceptions_keep_raw_transcripts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Service text stays raw across turns without automatic regeneration or tool replay."""
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", None)
    monkeypatch.setattr(config, "MEMORY_ENABLED", False)
    monkeypatch.setattr(config, "PROFILE_LANGUAGES", {})
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", "zh")
    instructions = get_session_instructions()
    assert "explicit request" in instructions and "this response only" in instructions
    assert "Simplified Chinese" in instructions and "code, URLs, paths, identifiers" in instructions
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    socket = FakeConnection([])
    handler.connection = socket
    observed: list[tuple[str, str, bool]] = []
    handler.set_transcript_observer(lambda role, value, final: observed.append((role, value, final)))
    start_tool = AsyncMock()
    monkeypatch.setattr(type(handler.tool_manager), "start_tool", start_tool)
    text = '简体原文 https://example.test/?q=简体 `print("x")` C:\\测试 badge-01'
    for answer in (text, "下一回合继续正常。"):
        await handler._handle_message({"serverContent": {"outputTranscription": {"text": answer}}})
        await handler._handle_message({"serverContent": {"turnComplete": True}})
    assert ("assistant", text, True) in observed
    assert ("assistant", "下一回合继续正常。", True) in observed
    assert socket.sent == []
    start_tool.assert_not_called()


@pytest.mark.asyncio
async def test_actual_rate_stereo_input_is_sent_as_mono_pcm_and_not_buffered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Captured float stereo audio is converted to correctly labelled PCM16 input."""
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    socket = FakeConnection([])
    monkeypatch.setattr(handler, "connection", socket)
    frame = np.full((4800, 2), 0.5, dtype=np.float32)
    await handler.receive((48000, frame))
    assert not socket.sent
    handler._ready = True
    await handler.receive((48000, frame))
    audio = socket.sent[0]["realtimeInput"]["audio"]
    assert audio["mimeType"] == "audio/pcm;rate=16000"
    samples = np.frombuffer(base64.b64decode(audio["data"]), dtype="<i2")
    assert 1000 < samples.size <= 1600 and np.median(samples) == pytest.approx(16384, abs=2)
    handler._ready = False
    await handler.receive((48000, frame))
    assert len(socket.sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "envelope",
    [
        {"serverContent": "private-malformed-payload"},
        {"serverContent": {"modelTurn": {"parts": "private-malformed-payload"}}},
        {"serverContent": {"modelTurn": {"parts": [{"inlineData": "private-malformed-payload"}]}}},
        {"toolCall": {"functionCalls": "private-malformed-payload"}},
        {"toolCall": {"functionCalls": [{"name": "move_head"}]}},
    ],
)
async def test_malformed_required_events_are_normalized(envelope: dict[str, object]) -> None:
    """Malformed required fields fail safely instead of silently dropping capabilities."""
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    with pytest.raises(gemini.GeminiConnectionError, match="^connection_lost$"):
        await handler._handle_message(envelope)


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [False, True])
async def test_connect_setup_and_fresh_fallback_share_fifteen_seconds(
    resume: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Connect latency and rejected resumption never restart the original setup deadline."""
    loop = asyncio.get_running_loop()
    elapsed = [loop.time()]
    monkeypatch.setattr(loop, "time", lambda: elapsed[0])
    monkeypatch.setattr(gemini, "time", SimpleNamespace(monotonic=lambda: elapsed[0]))
    monkeypatch.setattr(config, "GEMINI_API_KEY", "private-api-key")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [])
    opening = asyncio.Event()
    allow_open = asyncio.Event()
    awaiting_ack = asyncio.Event()
    socket = FakeConnection([])

    async def wait_for_ack() -> str:
        awaiting_ack.set()
        await asyncio.Event().wait()
        return "{}"

    monkeypatch.setattr(socket, "recv", wait_for_ack)
    rejected = FakeConnection([{"error": {"code": 400, "message": "Rejected resumption handle"}}])
    contexts = 0

    class DelayedConnect(FakeConnect):
        """Consume ten seconds before the first websocket opens."""

        async def __aenter__(self) -> FakeConnection:
            """Open only when the test releases the first handshake."""
            if contexts == 1:
                opening.set()
                await allow_open.wait()
            return self.socket

    def connect(*_args: object, **_kwargs: object) -> FakeConnect:
        nonlocal contexts
        contexts += 1
        return DelayedConnect(rejected if resume and contexts == 1 else socket)

    monkeypatch.setattr(gemini, "connect", connect)
    state = RealtimeSessionState(
        provider="gemini", resumable=resume, resumption_handle="checkpoint" if resume else None
    )
    handler = gemini.GeminiRealtimeHandler(
        ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()), session_state=state
    )
    task = asyncio.create_task(handler.start_up())
    try:
        await opening.wait()
        elapsed[0] += 10
        allow_open.set()
        await awaiting_ack.wait()
        elapsed[0] += 4.9
        for _step in range(10):
            await asyncio.sleep(0)
        assert not task.done() and not handler._is_connected()
        elapsed[0] += 0.2
        for _step in range(30):
            await asyncio.sleep(0)
        assert task.done()
        with pytest.raises(gemini.GeminiConnectionError, match="setup_timeout"):
            await task
        assert contexts == (2 if resume else 1)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_slow_socket_close_aborts_after_five_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A close that ignores cancellation loses its transport at the graceful-close deadline."""
    loop = asyncio.get_running_loop()
    elapsed = [loop.time()]
    monkeypatch.setattr(loop, "time", lambda: elapsed[0])
    closing = asyncio.Event()
    released = asyncio.Event()
    socket = FakeConnection([])

    async def close() -> None:
        closing.set()
        try:
            await released.wait()
        except asyncio.CancelledError:
            await released.wait()

    monkeypatch.setattr(socket, "close", close)
    socket.transport.abort.side_effect = released.set
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    monkeypatch.setattr(handler, "connection", socket)
    task = asyncio.create_task(handler.shutdown())
    try:
        await closing.wait()
        elapsed[0] += 5.1
        for _step in range(30):
            await asyncio.sleep(0)
        assert task.done() and not handler._is_connected()
        socket.transport.abort.assert_called_once()
        await task
    finally:
        released.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [{"setupComplete": "private-payload"}, ["private-payload"]])
async def test_malformed_setup_ack_is_not_readiness(message: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a valid setup acknowledgement can make the selected provider ready."""
    socket = FakeConnection([message])
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [])
    monkeypatch.setattr(gemini, "connect", lambda *_args, **_kwargs: FakeConnect(socket))
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    with pytest.raises(gemini.GeminiConnectionError, match="^connection_lost$"):
        await handler.start_up()
    assert not handler._is_connected()


@pytest.mark.asyncio
@pytest.mark.parametrize(("code", "recoverable"), [(1011, True), (4001, False)])
async def test_close_reasons_and_debug_frames_do_not_expose_credentials(
    code: int, recoverable: bool, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Configured wire logging and normalized close errors keep private payloads out of logs."""
    caplog.set_level(logging.DEBUG)
    key, handle, image = "private-api-key", "private-checkpoint", "private-image-payload"
    monkeypatch.setattr(config, "GEMINI_API_KEY", key)
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(config, "LOCAL_VAD_ENABLED", False)
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [])
    socket = FakeConnection([])
    received = 0

    async def receive() -> str:
        nonlocal received
        received += 1
        if received == 1:
            return '{"setupComplete":{}}'
        gemini.transport_logger.debug("Remote frame %s", image)
        raise ConnectionClosedError(Close(code, key + handle + image), None)

    async def send(message: str) -> None:
        gemini.transport_logger.debug("Outgoing frame %s", message)
        socket.sent.append(json.loads(message))

    monkeypatch.setattr(socket, "recv", receive)
    monkeypatch.setattr(socket, "send", send)

    def connect(*_args: object, **kwargs: object) -> FakeConnect:
        assert kwargs["logger"] is gemini.transport_logger
        gemini.transport_logger.debug("Request headers %s", kwargs["additional_headers"])
        return FakeConnect(socket)

    monkeypatch.setattr(gemini, "connect", connect)
    state = RealtimeSessionState(provider="gemini", resumable=True, resumption_handle=handle)
    handler = gemini.GeminiRealtimeHandler(
        ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()), session_state=state
    )
    with pytest.raises(gemini.GeminiConnectionError) as caught:
        await handler.start_up()
    assert caught.value.recoverable is recoverable
    assert not any(secret in caplog.text + str(caught.value) for secret in (key, handle, image))


@pytest.mark.asyncio
async def test_interruption_discards_old_media_and_preserves_multipart_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only output after the remote turn barrier survives an interruption."""
    samples = np.ones(2400, dtype="<i2")
    audio = {"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": base64.b64encode(samples.tobytes()).decode()}}
    socket = FakeConnection(
        [
            {"setupComplete": {}},
            {"serverContent": {"interrupted": True, "modelTurn": {"parts": [audio]}}},
            {"serverContent": {"generationComplete": True, "modelTurn": {"parts": [audio]}}},
            {"serverContent": {"turnComplete": True}},
            {"serverContent": {"modelTurn": {"parts": [audio, audio]}, "outputTranscription": {"text": "new answer"}}},
            {"serverContent": {"turnComplete": True}},
        ]
    )
    monkeypatch.setattr(config, "GEMINI_API_KEY", "secret-not-for-logs")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(config, "LOCAL_VAD_ENABLED", False)
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [])
    monkeypatch.setattr(gemini, "get_session_instructions", lambda _path: "personality")
    monkeypatch.setattr(gemini, "connect", lambda *_args, **_kwargs: FakeConnect(socket))
    robot = MagicMock()
    robot.media.get_output_audio_samplerate.return_value = 16000
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=robot, movement_manager=MagicMock()))
    transcripts: list[tuple[str, str, bool]] = []
    handler.set_transcript_observer(lambda role, text, final: transcripts.append((role, text, final)))
    completed = MagicMock()
    handler.exchange_completed = completed
    with pytest.raises(ConnectionError, match="simulated"):
        await handler.start_up()
    outputs = []
    while not handler.output_queue.empty():
        outputs.append(handler.output_queue.get_nowait())
    assert sum(output[1].size for output in outputs if not isinstance(output, AdditionalOutputs)) == 3200
    assert ("assistant", "new answer", True) in transcripts
    completed.assert_called_once()
    setup = socket.sent[0]["setup"]
    assert isinstance(setup, dict) and setup["systemInstruction"] == {"parts": [{"text": "personality"}]}
    assert "secret-not-for-logs" not in json.dumps(socket.sent)


def test_saved_voice_overrides_incompatible_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit provider choices resolve incompatible shared personality voices."""
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", None)
    monkeypatch.setattr(gemini, "get_session_voice", lambda default=None: "HF-only-voice")
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    with pytest.raises(ValueError, match="voice"):
        handler.get_current_voice()
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    assert handler.get_current_voice() == "Kore"


@pytest.mark.parametrize(
    ("saved", "profile", "environment", "expected"),
    [
        ("Puck", "Charon", "Aoede", "Puck"),
        (None, "Charon", "Aoede", "Charon"),
        (None, None, "Aoede", "Aoede"),
        (None, None, "", "Kore"),
    ],
)
def test_voice_precedence(
    saved: str | None, profile: str | None, environment: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Saved selection, compatible personality, environment and Kore resolve in order."""
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", saved)
    monkeypatch.setattr(config, "GEMINI_VOICE", environment)
    monkeypatch.setattr(gemini, "get_session_voice", lambda default=None: profile or default)
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    assert handler.get_current_voice() == expected


@pytest.mark.asyncio
async def test_uncertain_volume_result_is_not_treated_as_a_retryable_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown volume outcomes remain explicit and cannot replay the same action ID."""
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    socket = FakeConnection([])
    monkeypatch.setattr(handler, "connection", socket)
    handler._aliases = {"volume_control": "volume_control"}
    handler.session_state.invocations["volume-1"] = ToolInvocation("volume_control", "running")
    error = "Volume change outcome is uncertain. Do not retry automatically; ask the user first."

    await handler._handle_tool_result(
        gemini.ToolNotification(
            id="volume-1", tool_name="volume_control", is_idle_tool_call=False, status="failed", error=error
        )
    )

    response = socket.sent[0]["toolResponse"]["functionResponses"][0]["response"]
    assert response == {"error": error, "uncertain": True}
    assert handler.session_state.invocations["volume-1"].status == "uncertain"
    start_tool = AsyncMock()
    monkeypatch.setattr(type(handler.tool_manager), "start_tool", start_tool)
    await handler._tool_call({"id": "volume-1", "name": "volume_control", "args": {"level": 40}})
    start_tool.assert_not_called()
    assert "uncertain" in str(socket.sent[-1])


@pytest.mark.asyncio
async def test_replacement_handler_reuses_result_without_repeating_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """A resumed call reuses known results and never repeats uncertain effects."""
    state = RealtimeSessionState(provider="gemini", resumable=True, resumption_handle="opaque-checkpoint")
    state.invocations["call-1"] = ToolInvocation("move_head", "completed", {"ok": True})
    handler = gemini.GeminiRealtimeHandler(
        ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()), session_state=state
    )
    socket = FakeConnection([])
    monkeypatch.setattr(handler, "connection", socket)
    handler._aliases = {"move_head": "move_head"}
    start_tool = AsyncMock()
    monkeypatch.setattr(type(handler.tool_manager), "start_tool", start_tool)
    await handler._tool_call({"id": "call-1", "name": "move_head", "args": {}})
    assert socket.sent[0]["toolResponse"]["functionResponses"][0]["response"] == {"ok": True}
    start_tool.assert_not_called()
    state.invocations["call-1"].status = "uncertain"
    await handler._tool_call({"id": "call-1", "name": "move_head", "args": {}})
    assert "uncertain" in str(socket.sent[-1])
    start_tool.assert_not_called()
    assert "opaque-checkpoint" not in repr(state)


@pytest.mark.asyncio
async def test_resume_updates_clear_old_handle_and_old_generation_cannot_send(monkeypatch: pytest.MonkeyPatch) -> None:
    """The latest resume update and connection owner govern reuse."""
    state = RealtimeSessionState(provider="gemini", resumable=True, resumption_handle="old-checkpoint")
    handler = gemini.GeminiRealtimeHandler(
        ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()), session_state=state
    )
    socket = FakeConnection([])
    monkeypatch.setattr(handler, "connection", socket)
    await handler._handle_message({"sessionResumptionUpdate": {"resumable": False}})
    assert not state.resumable and state.resumption_handle is None
    state.begin_connection()
    with pytest.raises(gemini.GeminiConnectionError):
        await handler.say("old request")
    assert not socket.sent


@pytest.mark.asyncio
async def test_app_interrupt_retires_context_without_requesting_a_stop_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit interruption starts fresh and never sends a synthetic turn."""
    state = RealtimeSessionState(provider="gemini", resumable=True, resumption_handle="checkpoint")
    handler = gemini.GeminiRealtimeHandler(
        ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()), session_state=state
    )
    socket = FakeConnection([])
    monkeypatch.setattr(handler, "connection", socket)
    old_identity = state.logical_session_id
    await handler.interrupt()
    await handler.interrupt()
    assert state.logical_session_id != old_identity
    assert state.resumption_handle is None
    assert not socket.sent


@pytest.mark.parametrize(
    ("code", "message", "reason", "recoverable"),
    [
        (401, "secret-key", "authentication_failed", False),
        (400, "API key not valid: private-key", "authentication_failed", False),
        (400, "Unsupported function schema with private payload", "tool_schema_unsupported", False),
        (403, "secret-key", "access_unavailable", False),
        (429, "minute rate limit", "connection_lost", True),
        (429, "daily billing quota exhausted", "quota_exceeded", False),
        (503, "raw secret payload", "connection_lost", True),
    ],
)
def test_remote_failures_are_safe_and_classified(code: int, message: str, reason: str, recoverable: bool) -> None:
    """Remote errors expose only normalized recovery reasons."""
    with pytest.raises(gemini.GeminiConnectionError) as caught:
        gemini.GeminiRealtimeHandler._raise_remote_error({"code": code, "message": message})
    assert str(caught.value) == reason
    assert caught.value.recoverable is recoverable


@pytest.mark.asyncio
async def test_camera_tool_sends_one_snapshot_and_silent_sanitized_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """The existing manager dispatches an aliased tool once without leaking image text."""
    calls: list[str] = []

    class Snapshot(core_tools.Tool):
        """Capture a simulated permitted snapshot."""

        name = "snapshot.with.dots"
        _auto_register = False
        description = "Snapshot"
        parameters_schema = {"type": "object", "properties": {}, "additionalProperties": False}
        needs_response = False

        async def __call__(self, deps: ToolDependencies, **kwargs: object) -> dict[str, object]:
            """Return a fake JPEG using the existing camera result shape."""
            calls.append("capture")
            return {"b64_im": "encoded-jpeg"}

    tool = Snapshot()
    monkeypatch.setattr(core_tools, "get_tools", lambda: {tool.name: tool})
    monkeypatch.setattr(gemini, "get_tools", lambda: {tool.name: tool})
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [tool.spec()])
    handler = gemini.GeminiRealtimeHandler(
        ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock(), camera_enabled=True)
    )
    socket = FakeConnection([])
    monkeypatch.setattr(handler, "connection", socket)
    declarations = handler._declarations()
    alias = declarations[0]["name"]
    assert isinstance(alias, str) and len(alias) <= 128 and "." not in alias
    assert declarations[0]["behavior"] == "NON_BLOCKING"
    handler.tool_manager.start_up(tool_callbacks=[handler._handle_tool_result])
    try:
        await handler._tool_call({"id": "snapshot-1", "name": alias, "args": {}})
        for _attempt in range(100):
            if len(socket.sent) == 2:
                break
            await asyncio.sleep(0.001)
        response = socket.sent[0]["toolResponse"]["functionResponses"][0]
        assert response["id"] == "snapshot-1" and response["scheduling"] == "SILENT"
        assert "encoded-jpeg" not in json.dumps(response)
        assert socket.sent[1] == {"realtimeInput": {"video": {"mimeType": "image/jpeg", "data": "encoded-jpeg"}}}
        await handler._tool_call({"id": "snapshot-1", "name": alias, "args": {}})
        assert calls == ["capture"]
        await handler._tool_call({"id": "invalid", "name": alias, "args": {"unknown": True}})
        assert calls == ["capture"] and "Invalid tool arguments" in str(socket.sent[-1])
        handler.session_state.begin_connection()
        replacement = gemini.GeminiRealtimeHandler(handler.deps, session_state=handler.session_state)
        replacement_socket = FakeConnection([])
        monkeypatch.setattr(replacement, "connection", replacement_socket)
        replacement._declarations()
        await replacement._tool_call({"id": "snapshot-1", "name": alias, "args": {}})
        assert calls == ["capture"] and "snapshot" in str(replacement_socket.sent)
        assert "video" not in str(replacement_socket.sent)
    finally:
        await handler.shutdown()


@pytest.mark.asyncio
async def test_multiple_functions_keep_ids_and_suppress_late_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each enabled function is independently dispatched and cancelled results stay suppressed."""
    specs = [
        {"name": name, "description": name, "type": "function", "parameters": {"type": "object"}}
        for name in ("move_head", "get_robot_status")
    ]
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: specs)
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    socket = FakeConnection([])
    monkeypatch.setattr(handler, "connection", socket)
    handler._declarations()
    start = AsyncMock(side_effect=lambda call_id, *_args, **_kwargs: SimpleNamespace(tool_id="manager-" + call_id))
    cancel = AsyncMock()
    monkeypatch.setattr(type(handler.tool_manager), "start_tool", start)
    monkeypatch.setattr(type(handler.tool_manager), "cancel_tool", cancel)
    await handler._handle_message(
        {
            "toolCall": {
                "functionCalls": [
                    {"id": "head", "name": "move_head", "args": {}},
                    {"id": "status", "name": "get_robot_status", "args": {}},
                ]
            }
        }
    )
    assert start.await_count == 2
    await handler._handle_message({"toolCallCancellation": {"ids": ["head"]}})
    cancel.assert_awaited_once_with("manager-head")
    for call_id, name in (("head", "move_head"), ("status", "get_robot_status")):
        await handler._handle_tool_result(
            gemini.ToolNotification(
                id=call_id, tool_name=name, is_idle_tool_call=False, status="completed", result={"ok": True}
            )
        )
    assert len(socket.sent) == 1
    assert socket.sent[0]["toolResponse"]["functionResponses"][0]["id"] == "status"
    handler.session_state.begin_connection()
    await handler._handle_tool_result(
        gemini.ToolNotification(
            id="status", tool_name="get_robot_status", is_idle_tool_call=False, status="completed", result={"ok": True}
        )
    )
    assert len(socket.sent) == 1


@pytest.mark.parametrize("parameters", [{"type": "unknown"}, {"type": "array"}])
def test_unsupported_tool_schema_blocks_setup(parameters: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsupported tool declarations require correction instead of disappearing from setup."""
    monkeypatch.setattr(
        gemini,
        "get_tool_specs",
        lambda: [{"type": "function", "name": "bad.tool", "description": "bad", "parameters": parameters}],
    )
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    with pytest.raises(gemini.GeminiConnectionError, match="tool_schema_unsupported") as caught:
        handler._declarations()
    assert not caught.value.recoverable


@pytest.mark.asyncio
async def test_setup_and_send_deadlines_leave_no_ready_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unacknowledged setup and blocked sends are bounded and normalized."""
    socket = FakeConnection([])

    async def blocked_receive() -> str:
        await asyncio.Event().wait()
        return "{}"

    monkeypatch.setattr(socket, "recv", blocked_receive)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "private-key")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [])
    monkeypatch.setattr(gemini, "connect", lambda *_args, **_kwargs: FakeConnect(socket))
    monkeypatch.setattr(gemini, "SETUP_TIMEOUT_S", 0.01)
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    with pytest.raises(gemini.GeminiConnectionError, match="setup_timeout"):
        await handler.start_up()
    assert not handler._is_connected() and handler.connection is None

    async def blocked_send(_message: str) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(socket, "send", blocked_send)
    monkeypatch.setattr(handler, "connection", socket)
    monkeypatch.setattr(realtime, "AUDIO_SEND_TIMEOUT_S", 0.01)
    handler._ready = True
    with pytest.raises(gemini.GeminiConnectionError, match="send_timeout"):
        await handler.say("hello")
    assert not handler._is_connected()


@pytest.mark.asyncio
@pytest.mark.parametrize("reject_checkpoint", [False, True])
async def test_resume_or_fresh_fallback_uses_same_owner_state(
    reject_checkpoint: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid checkpoint skips greeting; rejection makes one acknowledged fresh attempt."""
    state = RealtimeSessionState(provider="gemini", resumable=True, resumption_handle="private-checkpoint")
    initial_identity = state.logical_session_id
    accepted = FakeConnection([{"setupComplete": {}}])
    rejected = FakeConnection([{"error": {"code": 400, "message": "Invalid resumption handle private-checkpoint"}}])
    sockets = iter([rejected, accepted] if reject_checkpoint else [accepted])
    monkeypatch.setattr(gemini, "connect", lambda *_args, **_kwargs: FakeConnect(next(sockets)))
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(config, "LOCAL_VAD_ENABLED", False)
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [])
    handler = gemini.GeminiRealtimeHandler(
        ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()), session_state=state
    )
    with pytest.raises(ConnectionError, match="simulated"):
        await handler.start_up()
    assert handler.session_state is state
    assert state.context_state == ("new" if reject_checkpoint else "resumed")
    assert (state.logical_session_id != initial_identity) is reject_checkpoint
    assert accepted.sent[0]["setup"]["sessionResumption"] == (
        {} if reject_checkpoint else {"handle": "private-checkpoint"}
    )
    assert len(accepted.sent) == (2 if reject_checkpoint else 1)


@pytest.mark.asyncio
async def test_goaway_preserves_eligible_context_for_replacement(monkeypatch: pytest.MonkeyPatch) -> None:
    """GoAway returns recovery to the owner while retaining the latest eligible checkpoint."""
    state = RealtimeSessionState(provider="gemini", resumable=True, resumption_handle="checkpoint")
    first = FakeConnection(
        [
            {"setupComplete": {}},
            {"sessionResumptionUpdate": {"resumable": True, "newHandle": "new-checkpoint"}},
            {"goAway": {"timeLeft": "10s"}},
        ]
    )
    second = FakeConnection([{"setupComplete": {}}])
    sockets = iter([first, second])
    monkeypatch.setattr(gemini, "connect", lambda *_args, **_kwargs: FakeConnect(next(sockets)))
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(config, "LOCAL_VAD_ENABLED", False)
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [])
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    handler = gemini.GeminiRealtimeHandler(deps, session_state=state)
    with pytest.raises(gemini.GeminiConnectionError) as caught:
        await handler.start_up()
    assert caught.value.recoverable
    state.begin_connection()
    replacement = gemini.GeminiRealtimeHandler(deps, session_state=state)
    with pytest.raises(ConnectionError, match="simulated"):
        await replacement.start_up()
    assert second.sent[0]["setup"]["sessionResumption"] == {"handle": "new-checkpoint"}
    assert state.context_state == "resumed"


@pytest.mark.asyncio
async def test_transient_resume_handshake_failure_keeps_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient socket loss before acknowledgement is not evidence of a rejected checkpoint."""
    state = RealtimeSessionState(provider="gemini", resumable=True, resumption_handle="checkpoint")
    socket = FakeConnection([])

    async def receive() -> str:
        raise ConnectionClosedError(Close(1011, "Temporary service error"), None)

    monkeypatch.setattr(socket, "recv", receive)
    connections = MagicMock(return_value=FakeConnect(socket))
    monkeypatch.setattr(gemini, "connect", connections)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [])
    handler = gemini.GeminiRealtimeHandler(
        ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()), session_state=state
    )
    with pytest.raises(gemini.GeminiConnectionError) as caught:
        await handler.start_up()
    assert caught.value.recoverable
    assert state.resumable and state.resumption_handle == "checkpoint"
    connections.assert_called_once()


@pytest.mark.asyncio
async def test_combined_interrupt_barrier_discards_envelope_and_preserves_user_transcript() -> None:
    """A bundled end marker reopens only subsequent output, independent of user input."""
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    transcripts: list[tuple[str, str, bool]] = []
    handler.set_transcript_observer(lambda role, text, final: transcripts.append((role, text, final)))
    await handler._handle_message(
        {
            "serverContent": {
                "interrupted": True,
                "turnComplete": True,
                "inputTranscription": {"text": "new user request"},
                "outputTranscription": {"text": "abandoned answer"},
            }
        }
    )
    await handler._handle_message(
        {"serverContent": {"outputTranscription": {"text": "next answer"}, "turnComplete": True}}
    )
    assert ("user", "new user request", True) in transcripts
    assert ("assistant", "next answer", True) in transcripts
    assert all("abandoned" not in text for _role, text, _final in transcripts)


@pytest.mark.asyncio
async def test_drain_suppresses_actions_but_accepts_cancellation_and_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated interruption keeps the barrier closed while control messages still apply."""
    handler = gemini.GeminiRealtimeHandler(ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()))
    handler.session_state.invocations["running"] = ToolInvocation("move_head", "running")
    handler._tool_ids["running"] = "manager-tool-id"
    cancel = AsyncMock()
    start = AsyncMock()
    monkeypatch.setattr(type(handler.tool_manager), "cancel_tool", cancel)
    monkeypatch.setattr(type(handler.tool_manager), "start_tool", start)
    interrupted = {"serverContent": {"interrupted": True}}
    await handler._handle_message(interrupted)
    first_epoch = handler.playback_epoch
    await handler._handle_message(interrupted)
    assert handler.playback_epoch > first_epoch
    await handler._handle_message({"toolCall": {"functionCalls": [{"id": "new", "name": "move_head", "args": {}}]}})
    start.assert_not_called()
    await handler._handle_message({"toolCallCancellation": {"ids": ["running"]}})
    cancel.assert_awaited_once_with("manager-tool-id")
    assert handler.session_state.invocations["running"].status == "cancelled"
    await handler._handle_message({"sessionResumptionUpdate": {"resumable": True, "newHandle": "checkpoint"}})
    assert handler.session_state.resumable
    await handler._handle_message({"serverContent": {"generationComplete": True}})
    assert handler._draining
    await handler._handle_message({"serverContent": {"turnComplete": True}})
    assert not handler._draining


@pytest.mark.asyncio
async def test_missing_interrupt_barrier_retires_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing remote end marker cannot keep abandoned output eligible indefinitely."""
    socket = FakeConnection([{"setupComplete": {}}, {"serverContent": {"interrupted": True}}])
    original_receive = socket.recv
    received = 0

    async def receive() -> str:
        nonlocal received
        received += 1
        if received > 2:
            await asyncio.Event().wait()
        return await original_receive()

    monkeypatch.setattr(socket, "recv", receive)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config, "GEMINI_VOICE_OVERRIDE", "Kore")
    monkeypatch.setattr(config, "LOCAL_VAD_ENABLED", False)
    monkeypatch.setattr(gemini, "get_tool_specs", lambda: [])
    monkeypatch.setattr(gemini, "connect", lambda *_args, **_kwargs: FakeConnect(socket))
    monkeypatch.setattr(gemini, "TURN_BOUNDARY_TIMEOUT_S", 0.01)
    state = RealtimeSessionState(provider="gemini", resumable=True, resumption_handle="old-checkpoint")
    handler = gemini.GeminiRealtimeHandler(
        ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()), session_state=state
    )
    previous = state.logical_session_id
    with pytest.raises(gemini.GeminiConnectionError, match="resume_unavailable"):
        await handler.start_up()
    assert state.resumption_handle is None and state.logical_session_id != previous
