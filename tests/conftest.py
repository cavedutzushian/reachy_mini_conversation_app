"""Pytest configuration for path setup."""

import os
import sys
import asyncio
from pathlib import Path
from collections.abc import Callable

import pytest


PROJECT_ROOT = Path(__file__).parents[1].resolve()
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


# Make tests reproducible by ignoring machine-specific profile/tool env config.
# Without this, importing config during test collection can pick up a developer's
# local .env and fail before tests run.
os.environ["REACHY_MINI_SKIP_DOTENV"] = "1"
os.environ.pop("REACHY_MINI_CUSTOM_PROFILE", None)
os.environ.pop("REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY", None)
os.environ.pop("REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY", None)


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    """Use native test loops with a portable socket loop for the local MCP fixture."""
    if isinstance(item, pytest.Function) and "local_mcp_server" in item.fixturenames:
        # Proactor close callbacks can strand Server.wait_closed on Python 3.12 Windows.
        return {"http": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}
