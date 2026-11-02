"""Apply persisted tool settings to the active conversation."""

import asyncio
import logging
from typing import NoReturn
from pathlib import Path
from collections.abc import Callable, Coroutine
from concurrent.futures import Future

from reachy_mini.io.jsonrpc import JsonRpcError
from reachy_mini_conversation_app.tools.core_tools import initialize_tools


logger = logging.getLogger(__name__)

RestartCallback = Callable[[str], Coroutine[None, None, None]]


def raise_tool_settings_error(reason: str, detail: str) -> NoReturn:
    """Raise a stable tool-settings error with user-facing detail."""
    raise JsonRpcError(detail, reason=reason, data={"detail": detail})


def _log_restart_completion(future: Future[None]) -> None:
    try:
        future.result()
    except Exception:
        logger.exception("Failed to restart the conversation after a tool change")


def apply_tool_change(
    instance_path: str | Path | None,
    get_loop: Callable[[], asyncio.AbstractEventLoop | None],
    restart_conversation: RestartCallback,
    reason: str,
) -> str:
    """Reload active tools and reconnect a running conversation."""
    try:
        initialize_tools(instance_path=instance_path, force=True)
    except Exception:
        logger.exception("Failed to reload tools after saving tool settings")
        return "已儲存，請重新啟動對話應用程式以套用工具變更。"

    try:
        conversation_loop = get_loop()
    except Exception:
        logger.exception("Failed to inspect the conversation loop after a tool change")
        return "已儲存，請重新啟動對話應用程式以套用工具變更。"
    if conversation_loop is None or not conversation_loop.is_running():
        return "對話啟動或重新啟動時將套用工具設定。"

    restart_coroutine: Coroutine[None, None, None] | None = None
    try:
        restart_coroutine = restart_conversation(reason)
        restart_future = asyncio.run_coroutine_threadsafe(
            restart_coroutine,
            conversation_loop,
        )
    except Exception:
        if restart_coroutine is not None:
            restart_coroutine.close()
        logger.exception("Failed to schedule a conversation restart after a tool change")
        return "已儲存，請重新啟動對話應用程式以套用工具變更。"
    restart_future.add_done_callback(_log_restart_completion)
    return "正在重新連接對話以套用工具變更。"
