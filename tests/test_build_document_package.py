import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path

import pytest

from reachy_mini_conversation_app import document_assets
from reachy_mini_conversation_app.document_assets import PreparationError, file_inventory
from reachy_mini_conversation_app.build_document_package import main, source_chunks


class CharacterTokenizer:
    """Supply deterministic repeated offsets with the production window constants."""

    def offsets(self, text: str) -> list[tuple[int, int]]:
        """Map one content token to every Unicode code point."""
        return [(index, index + 1) for index in range(len(text)) for _ in range(1)]

    def encoded_count(self, text: str) -> int:
        """Include two synthetic special tokens without truncation."""
        return len(text) + 2


def test_source_windows_preserve_exact_text_and_deterministic_identifiers() -> None:
    """Chapter windows cover every character with the fixed thirty-token overlap."""
    original = "X" * 800
    chunks = source_chunks(
        original, CharacterTokenizer(), "manual", "v1", "a" * 64, source_name="source.txt", markdown=False
    )
    assert [(chunk.start, chunk.end) for chunk in chunks] == [(0, 300), (270, 570), (540, 800)]
    assert chunks == source_chunks(
        original, CharacterTokenizer(), "manual", "v1", "a" * 64, source_name="source.txt", markdown=False
    )
    assert all(chunk.text == original[chunk.start : chunk.end] and len(chunk.chunk_id) == 66 for chunk in chunks)
    assert all(
        chunk.context == "source.txt" and chunk.model_text == "脈絡：source.txt\n原文：\n" + chunk.text
        for chunk in chunks
    )


def test_source_windows_never_split_crlf() -> None:
    """The included CRLF ending belongs to the preceding source line."""
    original = "A" * 299 + "\r\n" + "B" * 310
    chunks = source_chunks(
        original, CharacterTokenizer(), "manual", "v1", "a" * 64, source_name="source.txt", markdown=False
    )
    assert chunks[0].end == 299
    assert all(
        original[chunk.start - 1 : chunk.start + 1] != "\r\n" and original[chunk.end - 1 : chunk.end + 1] != "\r\n"
        for chunk in chunks
    )
    assert chunks[-1].line_end == 2
    assert set().union(*(set(range(chunk.start, chunk.end)) for chunk in chunks)) == set(range(len(original)))


def test_zero_offsets_preserve_the_complete_source_without_overlap() -> None:
    """The zero-offset fallback counts the complete prefix and never drops the tail."""

    class ZeroTokenizer:
        def offsets(self, text: str) -> list[tuple[int, int]]:
            return [(0, 0)] * len(text)

        def encoded_count(self, text: str) -> int:
            return len(text) + 2

    chunks = source_chunks(
        "X" * 600, ZeroTokenizer(), "manual", "v1", "a" * 64, source_name="source.txt", markdown=False
    )
    assert [(chunk.start, chunk.end) for chunk in chunks] == [(0, 492), (492, 600)]
    assert "".join(chunk.text for chunk in chunks) == "X" * 600
    assert all(len(chunk.model_text) + 2 <= 512 for chunk in chunks)


def test_nonmonotonic_token_counts_are_checked_at_every_legal_cut() -> None:
    """A high count at one cut cannot hide a valid shorter scored source prefix."""
    checked: list[str] = []

    class NonmonotonicTokenizer(CharacterTokenizer):
        def encoded_count(self, text: str) -> int:
            original = text.split("原文：\n", 1)[1]
            checked.append(original)
            return {300: 514, 299: 600, 298: 10}.get(len(original), len(text) + 2)

    chunks = source_chunks(
        "X" * 800, NonmonotonicTokenizer(), "manual", "v1", "a" * 64, source_name="source.txt", markdown=False
    )
    assert [len(text) for text in checked[:3]] == [300, 299, 298]
    assert chunks[0].end == 298


def test_whitespace_only_source_is_rejected() -> None:
    """A source with no meaningful text cannot become a ready package."""
    with pytest.raises(PreparationError, match="invalid_document"):
        source_chunks(
            "\r\n  \t", CharacterTokenizer(), "manual", "v1", "a" * 64, source_name="source.txt", markdown=False
        )


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
        ["--scheme", "unknown"],
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
        "--scheme": "bge-base-final-selection-20261109",
        "--reranker-model": str(tmp_path / "missing-reranker"),
        "--model": str(tmp_path / "missing-model"),
        "--output": str(tmp_path / "package"),
    }
    options[overrides[0]] = overrides[1]
    try:
        result = main([argument for pair in options.items() for argument in pair])
    except SystemExit as error:
        result = error.code
    assert result == 2
    assert not (tmp_path / "package").exists()


@pytest.mark.parametrize("offsets", [[(1, 2), (0, 1)], [(0, 9)], [(-1, 1)]])
def test_invalid_offset_mapping_is_rejected(offsets: list[tuple[int, int]]) -> None:
    """Out-of-range or nonmonotonic tokenizer mappings cannot silently discard source text."""

    class InvalidTokenizer(CharacterTokenizer):
        def offsets(self, text: str) -> list[tuple[int, int]]:
            return offsets

    with pytest.raises(PreparationError, match="model_incompatible"):
        source_chunks("ABCD", InvalidTokenizer(), "manual", "v1", "a" * 64, source_name="source.txt", markdown=False)


@pytest.mark.skipif(os.environ.get("RUN_DOCUMENT_PACKAGE_ACCEPTANCE") != "1", reason="Explicit local model acceptance")
@pytest.mark.parametrize(
    "text,filename,alias_mode",
    [
        ("繁體中文手冊。", "source.md", "absent"),
        ("An English manual.", "source.md", "absent"),
        ("不可按下紅色按鈕。", "source.md", "absent"),
        ("| 項目 | 數值 |\r\n| A | 1 |", "source.md", "absent"),
        ("```python\nprint('do not run')\n```\nhttps://example.invalid", "source.md", "absent"),
        ("純文字內容\r\n第二行\r尾端", "manual.txt", "empty"),
        ("前言\n# 紫色風車\n正文\n## 子節\n內容\n# 其他\n尾文", "source.md", "valid"),
        ("前言\n# 同名\n```\n# 假標題\n```\n正文\n# 同名\n尾文", "source.md", "absent"),
    ],
    ids=["zh", "en", "negation", "table", "code", "txt", "aliases", "duplicate-headings"],
)
def test_real_local_model_builds_five_source_packages_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str, filename: str, alias_mode: str
) -> None:
    """Actual CPU models preserve source, model bytes and repeated offline package contents."""
    model = Path(os.environ["DOCUMENT_MODEL_PATH"])
    reranker = Path(os.environ["DOCUMENT_RERANKER_PATH"])
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    models_before = [file_inventory(directory) for directory in (model, reranker)]
    source = tmp_path / filename
    original = text.encode("utf-8")
    source.write_bytes(original)
    arguments = [
        "--input",
        str(source),
        "--model",
        str(model),
        "--reranker-model",
        str(reranker),
        "--document-id",
        "manual",
        "--title",
        "驗收手冊",
        "--document-version",
        "v1",
        "--index-version",
        "build-1",
        "--scheme",
        "bge-base-final-selection-20261109",
    ]
    aliases = tmp_path / "aliases.json"
    if alias_mode != "absent":
        entries = []
        if alias_mode == "valid":
            first = text.index("紫色風車")
            entries.append(
                {
                    "text": "紫色風車",
                    "evidence_start": first,
                    "evidence_end": first + 4,
                    "scope_start": text.index("# 紫色風車"),
                    "scope_end": text.index("# 其他"),
                }
            )
        aliases.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "document_id": "manual",
                    "document_version": "v1",
                    "source_sha256": hashlib.sha256(original).hexdigest(),
                    "aliases": entries,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        arguments.extend(["--aliases", str(aliases)])
    alias_before = aliases.read_bytes() if aliases.exists() else None
    for repeat in range(2):
        output = tmp_path / f"package-{repeat}"
        assert main([*arguments, "--output", str(output)]) == 0
        assert source.read_bytes() == original
        assert (aliases.read_bytes() if aliases.exists() else None) == alias_before
    for asset in ("chunks.jsonl", "bm25.json"):
        assert (tmp_path / "package-0" / "retrieval" / asset).read_bytes() == (
            tmp_path / "package-1" / "retrieval" / asset
        ).read_bytes()
    assert [file_inventory(directory) for directory in (model, reranker)] == models_before


@pytest.mark.skipif(os.environ.get("RUN_DOCUMENT_PACKAGE_ACCEPTANCE") != "1", reason="Explicit local model acceptance")
def test_real_package_replacement_busy_and_cancelled_worker_preserve_materials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Actual role models survive rejected concurrent builds and controlled worker-start cancellation."""
    models = [Path(os.environ[name]) for name in ("DOCUMENT_MODEL_PATH", "DOCUMENT_RERANKER_PATH")]
    models_before = [file_inventory(directory) for directory in models]
    source = tmp_path / "source.txt"
    source.write_bytes("這份手冊禁止按下紅色按鈕。".encode("utf-8"))
    output = tmp_path / "package"
    arguments = [
        "--input",
        str(source),
        "--model",
        os.environ["DOCUMENT_MODEL_PATH"],
        "--reranker-model",
        os.environ["DOCUMENT_RERANKER_PATH"],
        "--output",
        str(output),
        "--document-id",
        "manual",
        "--title",
        "驗收手冊",
        "--document-version",
        "v1",
        "--index-version",
        "build-1",
        "--scheme",
        "bge-base-final-selection-20261109",
    ]
    assert main(arguments) == 0
    before = file_inventory(output)
    assert main(arguments) == 4
    assert file_inventory(output) == before
    lock_holder = (
        "import sys; from pathlib import Path; "
        "from reachy_mini_conversation_app.document_assets import AssetOperation; "
        "operation=AssetOperation(Path(sys.argv[1]), 'package', replace=True); "
        "operation.__enter__(); print('locked', flush=True); "
        "sys.stdin.buffer.read(1); operation.__exit__(None, None, None)"
    )
    with subprocess.Popen(
        [sys.executable, "-c", lock_holder, str(output)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as concurrent:
        assert concurrent.stdout is not None
        try:
            assert concurrent.stdout.readline().strip() == b"locked"
            assert main([*arguments, "--replace"]) == 4
            assert file_inventory(output) == before
        finally:
            concurrent.communicate(b"x", timeout=30)
        assert concurrent.returncode == 0

    class InterruptedWorker(subprocess.Popen[bytes]):
        def communicate(self, input: bytes | None = None, timeout: float | None = None) -> tuple[bytes, bytes]:
            if isinstance(self.args, list) and "reachy_mini_conversation_app.document_prepare_worker" in self.args:
                raise KeyboardInterrupt
            return super().communicate(input=input, timeout=timeout)

    with monkeypatch.context() as context:
        context.setattr(document_assets.subprocess, "Popen", InterruptedWorker)
        assert main([*arguments, "--replace"]) == 130
    assert file_inventory(output) == before
    assert source.read_bytes() == "這份手冊禁止按下紅色按鈕。".encode("utf-8")
    assert not (tmp_path / ".package.lock").exists()
    assert main([*arguments, "--replace"]) == 0
    for asset in ("retrieval/chunks.jsonl", "retrieval/bm25.json"):
        expected = next(entry for entry in before if entry["path"] == asset)
        actual = next(entry for entry in file_inventory(output) if entry["path"] == asset)
        assert actual == expected
    assert [file_inventory(directory) for directory in models] == models_before


@pytest.mark.parametrize("busy_role", [None, "embedding", "reranker", "package"])
def test_dual_models_lock_in_order_and_release_on_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, busy_role: str | None
) -> None:
    """Both model locks precede publication and a busy destination preserves every input."""
    from reachy_mini_conversation_app import build_document_package as builder
    from reachy_mini_conversation_app.document_assets import AssetOperation

    source = tmp_path / "source.txt"
    source.write_bytes(b"source-sentinel")
    embedding, reranker, output = (tmp_path / name for name in ("z-embedding", "a-reranker", "package"))
    for model in (embedding, reranker):
        model.mkdir()
        (model / "model-receipt.json").write_bytes(b"fake-receipt-never-loaded")
    expected = [reranker, embedding, output]
    entered: list[Path] = []
    original_enter = AssetOperation.__enter__

    def enter(operation):
        entered.append(operation.destination)
        return original_enter(operation)

    def verify_receipt(directory):
        return {"role": "embedding" if directory == embedding else "reranker"}

    requests = []

    def worker(request, operation):
        requests.append(dict(request))
        assert all(path.with_name(f".{path.name}.lock").is_dir() for path in expected)
        assert request["scheme"] == "bge-base-final-selection-20261109"
        assert request["reranker_model"] == str(reranker)
        assert "max_distance" not in request
        (operation.stage / "manifest.json").write_bytes(b"fake candidate; never a usable package")
        return {"status": "ok", "count": 1, "verified": True}

    monkeypatch.setattr(AssetOperation, "__enter__", enter)
    monkeypatch.setattr(builder, "validate_receipt", verify_receipt)
    monkeypatch.setattr(builder, "run_preparation_worker", worker)
    busy = {"embedding": embedding, "reranker": reranker, "package": output}.get(busy_role)
    if busy is not None:
        busy.with_name(f".{busy.name}.lock").mkdir()
    arguments = [
        "--input",
        str(source),
        "--model",
        str(embedding),
        "--reranker-model",
        str(reranker),
        "--output",
        str(output),
        "--document-id",
        "manual",
        "--title",
        "手冊",
        "--document-version",
        "v1",
        "--index-version",
        "v2",
        "--scheme",
        "bge-base-final-selection-20261109",
    ]
    assert main(arguments) == (4 if busy else 0)
    assert entered == expected[: expected.index(busy) + 1] if busy else entered == expected
    assert len(requests) == (0 if busy else 2)
    for path in expected:
        assert path.with_name(f".{path.name}.lock").exists() == (path == busy)
    assert source.read_bytes() == b"source-sentinel"
    for model in (embedding, reranker):
        assert (model / "model-receipt.json").read_bytes() == b"fake-receipt-never-loaded"


@pytest.mark.parametrize("missing", ["--model", "--reranker-model", "--output"])
def test_wheel_builder_requires_every_explicit_asset_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """An installed wheel never guesses a checkout or writes into its current directory."""
    from reachy_mini_conversation_app import build_document_package as builder

    monkeypatch.setattr(builder, "checkout_root", lambda: None)
    source = tmp_path / "source.md"
    source.write_text("原文", encoding="utf-8")
    options = {
        "--input": str(source),
        "--model": str(tmp_path / "embedding"),
        "--reranker-model": str(tmp_path / "reranker"),
        "--output": str(tmp_path / "package"),
        "--document-id": "manual",
        "--title": "手冊",
        "--document-version": "v1",
        "--index-version": "v2",
        "--scheme": "bge-base-final-selection-20261109",
    }
    del options[missing]
    assert main([argument for pair in options.items() for argument in pair]) == 2
    assert not (tmp_path / "package").exists()


@pytest.mark.parametrize("markdown", [True, False])
def test_chapters_preserve_fences_preamble_duplicate_titles_and_original_locations(markdown: bool) -> None:
    """Only actual Markdown headings create sections; every original character remains covered."""
    text = "前言\r\n# 同名\r\n正文\r\n```\r\n# 假標題\r\n```\r\n## 子節\r\n內容\r\n# 同名\r\n尾文"
    chunks = source_chunks(
        text,
        CharacterTokenizer(),
        "manual",
        "v1",
        "a" * 64,
        source_name="manual.md" if markdown else "manual.txt",
        markdown=markdown,
    )
    assert set().union(*(set(range(chunk.start, chunk.end)) for chunk in chunks)) == set(range(len(text)))
    assert all(chunk.text == text[chunk.start : chunk.end] for chunk in chunks)
    for chunk in chunks:
        for heading in chunk.headings:
            assert heading.text == text[heading.start : heading.end]
    if markdown:
        assert len(chunks) == 4
        assert [chunk.context for chunk in chunks] == ["manual.md", "同名", "同名 > 子節", "同名"]
        assert chunks[1].headings[0].start != chunks[3].headings[0].start
    else:
        assert len(chunks) == 1 and not chunks[0].headings and chunks[0].context == "manual.txt"


def test_aliases_are_source_verified_and_expand_only_within_the_selected_subtree() -> None:
    """A name found elsewhere cannot silently become context for another section."""
    text = "# 北部\n紫色風車\n## 子節\n內容\n# 南部\n其他\n"
    start = text.index("紫色風車")
    aliases = {
        "schema_version": 1,
        "document_id": "manual",
        "document_version": "v1",
        "source_sha256": "a" * 64,
        "aliases": [
            {
                "text": "紫色風車",
                "evidence_start": start,
                "evidence_end": start + 4,
                "scope_start": 0,
                "scope_end": text.index("# 南部"),
            }
        ],
    }
    chunks = source_chunks(
        text, CharacterTokenizer(), "manual", "v1", "a" * 64, source_name="manual.md", markdown=True, aliases=aliases
    )
    assert [chunk.alias_context for chunk in chunks] == ["紫色風車", "紫色風車", ""]
    assert chunks[0].aliases[0]["evidence_line_start"] == 2
    assert "戰隊別名：紫色風車\n" in chunks[0].model_text
    for change in ({"document_version": "v2"}, {"source_sha256": "b" * 64}, {"unexpected": True}):
        with pytest.raises(PreparationError, match="invalid_aliases"):
            source_chunks(
                text,
                CharacterTokenizer(),
                "manual",
                "v1",
                "a" * 64,
                source_name="manual.md",
                markdown=True,
                aliases={**aliases, **change},
            )


@pytest.mark.parametrize("arguments", [["--scheme", "unknown"], ["--max-distance", "0.58"]])
def test_builder_rejects_missing_or_overridden_scheme(arguments: list[str]) -> None:
    """No standalone threshold or unknown preset can select a retrieval strategy."""
    with pytest.raises(SystemExit) as failure:
        main(
            [
                "--input",
                "source.txt",
                "--document-id",
                "manual",
                "--title",
                "手冊",
                "--document-version",
                "v1",
                "--index-version",
                "v2",
                *arguments,
            ]
        )
    assert failure.value.code == 2


def test_unconfirmed_producer_exit_preserves_both_model_locks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A possibly running child retains all material ownership until manual recovery."""
    from reachy_mini_conversation_app import build_document_package as builder

    source = tmp_path / "source.txt"
    source.write_bytes(b"source")
    models = [tmp_path / "embedding", tmp_path / "reranker"]
    for model in models:
        model.mkdir()
        (model / "model-receipt.json").write_bytes(b"fake; never loaded")
    monkeypatch.setattr(
        builder, "validate_receipt", lambda path: {"role": "embedding" if path == models[0] else "reranker"}
    )

    def uncertain_exit(request, operation):
        operation.preserve = True
        raise PreparationError("recovery_required", 8)

    monkeypatch.setattr(builder, "run_preparation_worker", uncertain_exit)
    assert (
        main(
            [
                "--input",
                str(source),
                "--model",
                str(models[0]),
                "--reranker-model",
                str(models[1]),
                "--output",
                str(tmp_path / "package"),
                "--document-id",
                "manual",
                "--title",
                "??",
                "--document-version",
                "v1",
                "--index-version",
                "v2",
                "--scheme",
                "bge-base-final-selection-20261109",
            ]
        )
        == 8
    )
    assert all((tmp_path / name).is_dir() for name in (".embedding.lock", ".reranker.lock", ".package.lock"))
    assert all((model / "model-receipt.json").read_bytes() == b"fake; never loaded" for model in models)


@pytest.mark.parametrize("relationship", ["same_models", "nested_models", "output_in_model", "aliases_is_source"])
def test_unsafe_dual_model_relationships_fail_before_worker(
    tmp_path: Path, relationship: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No combination of explicit paths may turn a source or model into disposable output."""
    from reachy_mini_conversation_app import build_document_package as builder

    source = tmp_path / "source.txt"
    source.write_bytes(b"source")
    model, reranker, output = (tmp_path / name for name in ("model", "reranker", "output"))
    if relationship == "same_models":
        reranker = model
    elif relationship == "nested_models":
        reranker = model / "nested"
    elif relationship == "output_in_model":
        output = model / "output"

    def unexpected_worker(*args):
        pytest.fail("Unsafe paths reached inference")

    monkeypatch.setattr(builder, "run_preparation_worker", unexpected_worker)
    arguments = [
        "--input",
        str(source),
        "--model",
        str(model),
        "--reranker-model",
        str(reranker),
        "--output",
        str(output),
        "--document-id",
        "manual",
        "--title",
        "??",
        "--document-version",
        "v1",
        "--index-version",
        "v2",
        "--scheme",
        "bge-base-final-selection-20261109",
    ]
    if relationship == "aliases_is_source":
        arguments.extend(["--aliases", str(source)])
    assert main(arguments) in (2, 4)
    assert source.read_bytes() == b"source"
    assert not output.exists()


@pytest.mark.parametrize("change", ["wrong_text", "wrong_scope", "bool_offset", "duplicate"])
def test_alias_evidence_and_scope_cannot_be_guessed(change: str) -> None:
    """A manual alias needs exact source text and an actual enclosing subtree."""
    text = "# 北部\n紫色風車\n# 南部\n其他\n"
    first = text.index("紫色風車")
    entry = {
        "text": "紫色風車",
        "evidence_start": first,
        "evidence_end": first + 4,
        "scope_start": 0,
        "scope_end": text.index("# 南部"),
    }
    if change == "wrong_text":
        entry["text"] = "紫色氣球"
    elif change == "wrong_scope":
        entry["scope_end"] -= 1
    elif change == "bool_offset":
        entry["scope_start"] = False
    aliases = {
        "schema_version": 1,
        "document_id": "manual",
        "document_version": "v1",
        "source_sha256": "a" * 64,
        "aliases": [entry, entry] if change == "duplicate" else [entry],
    }
    with pytest.raises(PreparationError, match="invalid_aliases"):
        source_chunks(
            text,
            CharacterTokenizer(),
            "manual",
            "v1",
            "a" * 64,
            source_name="source.md",
            markdown=True,
            aliases=aliases,
        )


def test_unicode_separators_do_not_create_nonexistent_source_lines() -> None:
    """Only CRLF, CR and LF contribute to original source line numbers."""
    text = "# 中文\u2028仍是標題\n正文\u0085仍是正文"
    chunks = source_chunks(
        text, CharacterTokenizer(), "manual", "v1", "a" * 64, source_name="source.md", markdown=True
    )
    assert len(chunks) == 1
    assert chunks[0].headings[0].text == "中文\u2028仍是標題"
    assert chunks[0].headings[0].line_start == 1
    assert chunks[0].line_end == 2


def test_checkout_defaults_are_independent_of_the_cli_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All three default asset paths stay rooted at the selected checkout."""
    from reachy_mini_conversation_app import build_document_package as builder

    root = tmp_path / "checkout"
    embedding = root / "external_content/bge-m3-model"
    reranker = root / "external_content/bge-reranker-base-model"
    output = root / "external_content/document-package"
    for directory in (embedding, reranker):
        directory.mkdir(parents=True)
        (directory / "model-receipt.json").write_bytes(b"fake; never loaded")
    source = tmp_path / "source.TXT"
    source.write_bytes(b"source")
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    monkeypatch.setattr(builder, "checkout_root", lambda: root)
    monkeypatch.setattr(
        builder, "validate_receipt", lambda directory: {"role": "embedding" if directory == embedding else "reranker"}
    )

    def worker(request, operation):
        assert request["model"] == str(embedding) and request["reranker_model"] == str(reranker)
        assert operation.destination == output
        (operation.stage / "manifest.json").write_bytes(b"fake; never a usable package")
        return {"status": "ok", "count": 1, "verified": True}

    monkeypatch.setattr(builder, "run_preparation_worker", worker)
    assert (
        main(
            [
                "--input",
                str(source),
                "--document-id",
                "manual",
                "--title",
                "手冊",
                "--document-version",
                "v1",
                "--index-version",
                "v2",
                "--scheme",
                "bge-base-final-selection-20261109",
            ]
        )
        == 0
    )
    assert (output / "manifest.json").is_file() and not (other / "external_content").exists()
