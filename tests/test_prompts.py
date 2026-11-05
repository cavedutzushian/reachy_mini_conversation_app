"""Document instructions remain conditional on existing tool access."""

from pathlib import Path

import pytest

from reachy_mini_conversation_app.config import config
from reachy_mini_conversation_app.prompts import get_session_instructions
from reachy_mini_conversation_app.profile_toolsets import ProfileToolsets, write_profile_toolsets


def test_document_instructions_follow_profile_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only an explicitly enabled document tool adds evidence and citation rules."""
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", "default")
    monkeypatch.setattr(config, "MEMORY_ENABLED", False)
    write_profile_toolsets(tmp_path, ProfileToolsets(profiles={"default": []}))
    assert "search_document" not in get_session_instructions(tmp_path)
    write_profile_toolsets(tmp_path, ProfileToolsets(profiles={"default": ["search_document"]}))
    instructions = get_session_instructions(tmp_path)
    assert "search_document" in instructions
    assert "Traditional Chinese" in instructions
    assert "untrusted reference text" in instructions
    assert "source locator" in instructions
    assert "another language" in instructions
