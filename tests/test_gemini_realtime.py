import json
import base64
import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

import reachy_mini_conversation_app.gemini_realtime as gemini
import reachy_mini_conversation_app.huggingface_realtime as realtime
from reachy_mini_conversation_app.tools import core_tools
from reachy_mini_conversation_app.config import config
from reachy_mini_conversation_app.streaming import AdditionalOutputs
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.huggingface_realtime import ToolInvocation, RealtimeSessionState


class FakeConnection:
    """Replay remote messages and capture outgoing payloads."""

    def __init__(self, messages: list[dict[str, object]]) -> None:
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
    with pytest.raises(ConnectionError, match="simulated"):
        await handler.start_up()
    outputs = []
    while not handler.output_queue.empty():
        outputs.append(handler.output_queue.get_nowait())
    assert sum(output[1].size for output in outputs if not isinstance(output, AdditionalOutputs)) == 3200
    assert ("assistant", "new answer", True) in transcripts
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
    finally:
        await handler.shutdown()


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
