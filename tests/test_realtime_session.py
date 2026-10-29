from reachy_mini_conversation_app.huggingface_realtime import ToolInvocation, RealtimeSessionState


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
