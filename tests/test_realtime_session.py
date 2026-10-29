import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from reachy_mini_conversation_app.gemini_realtime import GeminiConnectionError, GeminiRealtimeHandler
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.huggingface_realtime import (
    ToolInvocation,
    RealtimeSessionState,
    HuggingFaceRealtimeHandler,
)


def test_logical_session_survives_reconnect_but_not_provider_change() -> None:
    """Reconnect retains deduplication and a fresh session invalidates it."""
    session = RealtimeSessionState(provider="gemini")
    session.invocations["call-1"] = ToolInvocation(tool_name="move_head")
    session.resumption_handle = "private-handle"
    session.resumable = True
    first = session.begin_connection()
    second = session.begin_connection()
    assert second > first
    assert "call-1" in session.invocations
    assert session.resumption_handle == "private-handle"
    session.fresh("huggingface", "changed")
    assert not session.invocations
    assert session.resumption_handle is None
    assert session.begin_connection() > second


def test_recovery_reports_uncertain_effects_once_without_forgetting_call_ids() -> None:
    """Repeated recovery preserves deduplication without repeating the uncertainty notice."""
    state = RealtimeSessionState(provider="gemini")
    state.invocations["started"] = ToolInvocation("move_head", "running")
    assert state.mark_uncertain_actions()
    state.begin_connection()
    assert not state.mark_uncertain_actions()
    assert state.invocations["started"].status == "uncertain"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["huggingface", "gemini"])
async def test_five_second_send_expiry_retires_both_providers(provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The actual shared send deadline invalidates ownership before transport cleanup."""
    loop = asyncio.get_running_loop()
    elapsed = [loop.time()]
    monkeypatch.setattr(loop, "time", lambda: elapsed[0])
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    handler = GeminiRealtimeHandler(deps) if provider == "gemini" else HuggingFaceRealtimeHandler(deps)
    writing = asyncio.Event()

    async def blocked_send(*_args: object, **_kwargs: object) -> None:
        writing.set()
        await asyncio.Event().wait()

    socket = MagicMock(send=blocked_send, close=AsyncMock())
    socket.conversation.item.create = blocked_send
    monkeypatch.setattr(handler, "connection", socket)
    if isinstance(handler, GeminiRealtimeHandler):
        handler._ready = True
    generation = handler.session_state.generation
    task = asyncio.create_task(handler.say("Say hello"))
    try:
        await writing.wait()
        elapsed[0] += 4.9
        for _step in range(10):
            await asyncio.sleep(0)
        assert not task.done() and handler._owns_connection()
        elapsed[0] += 0.2
        for _step in range(30):
            await asyncio.sleep(0)
        assert task.done() and not handler._owns_connection()
        assert handler.session_state.generation > generation
        with pytest.raises((TimeoutError, GeminiConnectionError)):
            await task
        assert handler.connection_error_reason == "send_timeout"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
