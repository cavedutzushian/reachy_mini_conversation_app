"""Contract checks for the optional document tool."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from reachy_mini_conversation_app.tools import core_tools
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.document_retrieval import DOCUMENT_ERRORS
from reachy_mini_conversation_app.tools.search_document import SearchDocument
from reachy_mini_conversation_app.tools.background_tool_manager import ToolCallRoutine, BackgroundToolManager


@pytest.mark.asyncio
@pytest.mark.parametrize("question", ["", "...", 12, " " * 2 + "字" * 499])
async def test_invalid_question_never_reaches_runtime(question) -> None:
    """Length is checked before trimming and invalid input never performs retrieval."""
    runtime = MagicMock(query=AsyncMock())
    deps = ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime)
    assert await SearchDocument()(deps, query=question) == {"error": "document_invalid_query"}
    runtime.query.assert_not_called()


@pytest.mark.asyncio
async def test_query_uses_injected_runtime_without_selecting_path() -> None:
    """The tool passes only the validated question to the instance's shared runtime."""
    runtime = MagicMock(query=AsyncMock(return_value={"error": "document_no_evidence"}))
    deps = ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime)
    assert await SearchDocument()(deps, query="  文件寫了什麼？  ") == {"error": "document_no_evidence"}
    runtime.query.assert_awaited_once_with("文件寫了什麼？")
    assert await SearchDocument()(deps, query="question", path=str(Path("other"))) == {
        "error": "document_invalid_query"
    }
    assert runtime.query.await_count == 1


@pytest.mark.asyncio
async def test_missing_runtime_is_not_ready() -> None:
    """Ordinary installations can expose a safe unavailable result without RAG dependencies."""
    deps = ToolDependencies(MagicMock(), MagicMock())
    assert await SearchDocument()(deps, query="question") == {"error": "document_not_ready"}


@pytest.mark.asyncio
async def test_five_hundred_unicode_characters_are_accepted_before_trimming() -> None:
    """The valid boundary counts Unicode code points rather than UTF-8 bytes."""
    runtime = MagicMock(query=AsyncMock(return_value={"error": "document_no_evidence"}))
    deps = ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime)
    assert await SearchDocument()(deps, query=" " + "字" * 498 + " ") == {"error": "document_no_evidence"}
    runtime.query.assert_awaited_once_with("字" * 498)


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ['{"query":"private-sentinel"', '{"query":"question","tool_manager":{}}'])
async def test_dispatcher_rejects_malformed_or_injected_arguments_without_echo(
    arguments: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The shared parser must not disclose invalid queries or accept model-owned manager arguments."""
    runtime = MagicMock(query=AsyncMock())
    deps = ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime)
    monkeypatch.setattr(core_tools, "get_tools", lambda: {"search_document": SearchDocument()})
    result = await core_tools.dispatch_tool_call("search_document", arguments, deps)
    assert result == {"error": "document_invalid_query"}
    assert "private-sentinel" not in caplog.text
    runtime.query.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_unexpected_error_never_returns_private_payload(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The dispatcher reports a safe error even when an unexpected runtime failure contains document text."""
    runtime = MagicMock(query=AsyncMock(side_effect=RuntimeError("private-exception-sentinel")))
    deps = ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime)
    monkeypatch.setattr(core_tools, "get_tools", lambda: {"search_document": SearchDocument()})
    result = await core_tools.dispatch_tool_call("search_document", '{"query":"question"}', deps)
    assert result == {"error": "document_unavailable"}
    assert "private-exception-sentinel" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("error", sorted(DOCUMENT_ERRORS))
async def test_fixed_errors_survive_background_manager(error: str, monkeypatch) -> None:
    """The real dispatcher and manager retain each recoverable document error code."""
    runtime = MagicMock(query=AsyncMock(return_value={"error": error}))
    deps = ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime)
    monkeypatch.setattr(core_tools, "get_tools", lambda: {"search_document": SearchDocument()})
    manager = BackgroundToolManager()
    completed = []
    manager.start_up(tool_callbacks=[AsyncMock(side_effect=completed.append)])
    try:
        tool = await manager.start_tool(
            "doc-call",
            ToolCallRoutine(tool_name="search_document", args_json_str='{"query":"question"}', deps=deps),
            is_idle_tool_call=False,
        )
        for _attempt in range(100):
            if completed:
                break
            await asyncio.sleep(0.01)
        assert len(completed) == 1
        assert completed[0].error == error
        assert manager.get_tool(tool.tool_id).error == error
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_document_deadline_notice_is_not_queued_behind_another_tool_callback(monkeypatch) -> None:
    """A provider wait in another callback cannot postpone the local RAG timeout notice."""
    runtime = MagicMock(query=AsyncMock(return_value={"error": "document_timeout"}))
    deps = ToolDependencies(MagicMock(), MagicMock(), document_retrieval=runtime)
    monkeypatch.setattr(
        core_tools,
        "get_tools",
        lambda: {"search_document": SearchDocument(), "normal_tool": AsyncMock(return_value={"ok": True})},
    )
    blocked, release = asyncio.Event(), asyncio.Event()
    documents = []

    async def receive(note):
        if note.tool_name == "normal_tool":
            blocked.set()
            await release.wait()
        else:
            documents.append(note)

    manager = BackgroundToolManager()
    manager.start_up(tool_callbacks=[receive])
    try:
        await manager.start_tool(
            "normal", ToolCallRoutine(tool_name="normal_tool", args_json_str="{}", deps=deps), False
        )
        await asyncio.wait_for(blocked.wait(), timeout=1)
        await manager.start_tool(
            "doc", ToolCallRoutine(tool_name="search_document", args_json_str='{"query":"question"}', deps=deps), False
        )
        for _attempt in range(50):
            if documents:
                break
            await asyncio.sleep(0.01)
        assert len(documents) == 1
        assert documents[0].error == "document_timeout"
    finally:
        release.set()
        await manager.shutdown()
