import os
import sys
import subprocess
from pathlib import Path

import pytest

from reachy_mini_conversation_app.document_assets import PreparationError
from reachy_mini_conversation_app.build_document_package import main, source_chunks


class CharacterTokenizer:
    """Supply deterministic repeated offsets with the production window constants."""

    def offsets(self, text: str) -> list[tuple[int, int]]:
        """Map one hundred content tokens to every Unicode code point."""
        return [(index, index + 1) for index in range(len(text)) for _ in range(100)]

    def encoded_count(self, text: str) -> int:
        """Include two synthetic special tokens without truncation."""
        return len(text) * 100 + 2


def test_source_windows_preserve_exact_text_and_deterministic_identifiers() -> None:
    """Accepted windows cover the entire source with the fixed token-origin overlap."""
    chunks = source_chunks("ABCDEFGH", CharacterTokenizer(), "manual", "v1", "a" * 64)
    assert [(chunk.start, chunk.end, chunk.text) for chunk in chunks] == [(0, 4, "ABCD"), (3, 7, "DEFG"), (6, 8, "GH")]
    assert chunks == source_chunks("ABCDEFGH", CharacterTokenizer(), "manual", "v1", "a" * 64)
    assert all(len(chunk.chunk_id) == 66 and chunk.locator.startswith("L1-L1;") for chunk in chunks)


def test_source_windows_never_split_crlf() -> None:
    """CRLF boundaries preserve literal source and count the included line ending once."""
    chunks = source_chunks("ABC\r\nDEF", CharacterTokenizer(), "manual", "v1", "a" * 64)
    assert [(chunk.start, chunk.end) for chunk in chunks] == [(0, 3), (2, 6), (5, 8)]
    assert [chunk.text for chunk in chunks] == ["ABC", "C\r\nD", "DEF"]
    assert chunks[1].locator == "L1-L2; chars[2,6)"


def test_zero_offsets_preserve_the_complete_source_without_overlap() -> None:
    """The fixed fallback backs off from 512 characters until special tokens fit."""

    class ZeroTokenizer:
        def offsets(self, text: str) -> list[tuple[int, int]]:
            return [(0, 0)] * len(text)

        def encoded_count(self, text: str) -> int:
            return len(text) + 2

    chunks = source_chunks("X" * 600, ZeroTokenizer(), "manual", "v1", "a" * 64)
    assert [(chunk.start, chunk.end) for chunk in chunks] == [(0, 510), (510, 600)]
    assert "".join(chunk.text for chunk in chunks) == "X" * 600


def test_nonmonotonic_token_counts_are_checked_at_every_legal_cut() -> None:
    """A higher count at the preceding cut cannot hide a smaller valid prefix."""
    checked: list[str] = []

    class NonmonotonicTokenizer(CharacterTokenizer):
        def encoded_count(self, text: str) -> int:
            checked.append(text)
            return {"ABCD": 514, "ABC": 600, "AB": 10}.get(text, len(text) * 100 + 2)

    chunks = source_chunks("ABCDEFGH", NonmonotonicTokenizer(), "manual", "v1", "a" * 64)
    assert checked[:3] == ["ABCD", "ABC", "AB"]
    assert chunks[0].text == "AB"


def test_whitespace_only_source_is_rejected() -> None:
    """A source with no meaningful text cannot become a ready package."""
    with pytest.raises(PreparationError, match="invalid_document"):
        source_chunks("\r\n  \t", CharacterTokenizer(), "manual", "v1", "a" * 64)


def test_builder_help_stays_lightweight() -> None:
    """Configuration and inference remain outside the public CLI import graph."""
    command = """
import sys
from reachy_mini_conversation_app.build_document_package import main
try:
    main(["--help"])
except SystemExit as error:
    assert error.code == 0
assert not {"torch", "chromadb", "sentence_transformers", "reachy_mini_conversation_app.config"}.intersection(sys.modules)
"""
    subprocess.run([sys.executable, "-c", command], check=True, capture_output=True)


def test_builder_rejects_multiple_inputs() -> None:
    """Argparse must not silently select the last of several input files."""
    with pytest.raises(SystemExit) as failure:
        main(["--input", "a.txt", "--input", "b.txt"])
    assert failure.value.code == 2


@pytest.mark.parametrize(
    "overrides",
    [
        ["--document-id", "../escape"],
        ["--title", "bad\nlabel"],
        ["--max-distance", "nan"],
        ["--max-distance", "3"],
        ["--document-version", "x" * 129],
        ["--input", "https://example.invalid/source.md"],
    ],
)
def test_invalid_build_arguments_fail_before_model_loading(tmp_path: Path, overrides: list[str]) -> None:
    """Invalid identity, display, format or distance cannot start a worker or touch an output."""
    source = tmp_path / "source.TXT"
    source.write_bytes(b"source")
    options = {
        "--input": str(source),
        "--document-id": "manual",
        "--title": "Manual",
        "--document-version": "v1",
        "--index-version": "build-1",
        "--max-distance": "0.3",
        "--model": str(tmp_path / "missing-model"),
        "--output": str(tmp_path / "package"),
    }
    options[overrides[0]] = overrides[1]
    assert main([argument for pair in options.items() for argument in pair]) == 2
    assert not (tmp_path / "package").exists()


@pytest.mark.parametrize("offsets", [[(1, 2), (0, 1)], [(0, 9)], [(-1, 1)]])
def test_invalid_offset_mapping_is_rejected(offsets: list[tuple[int, int]]) -> None:
    """Out-of-range or nonmonotonic tokenizer mappings cannot silently discard source text."""

    class InvalidTokenizer(CharacterTokenizer):
        def offsets(self, text: str) -> list[tuple[int, int]]:
            return offsets

    with pytest.raises(PreparationError, match="model_incompatible"):
        source_chunks("ABCD", InvalidTokenizer(), "manual", "v1", "a" * 64)


@pytest.mark.skipif(os.environ.get("RUN_DOCUMENT_PACKAGE_ACCEPTANCE") != "1", reason="Explicit local model acceptance")
def test_real_local_model_builds_five_source_packages_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicitly supplied model and calibrated threshold exercise the actual offline workers."""
    model = Path(os.environ["DOCUMENT_MODEL_PATH"])
    distance = os.environ["DOCUMENT_MAX_DISTANCE"]
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    examples = [
        "繁體中文手冊。",
        "An English manual.",
        "不可按下紅色按鈕。",
        "| 項目 | 數值 |\n| A | 1 |",
        "```python\nprint('do not run')\n```\nhttps://example.invalid",
    ]
    for ordinal, text in enumerate(examples):
        source = tmp_path / f"source-{ordinal}.md"
        source.write_text(text, encoding="utf-8")
        assert (
            main(
                [
                    "--input",
                    str(source),
                    "--model",
                    str(model),
                    "--output",
                    str(tmp_path / f"package-{ordinal}"),
                    "--document-id",
                    "manual",
                    "--title",
                    "驗收手冊",
                    "--document-version",
                    "v1",
                    "--index-version",
                    "build-1",
                    "--max-distance",
                    distance,
                ]
            )
            == 0
        )
        assert source.read_text(encoding="utf-8") == text
