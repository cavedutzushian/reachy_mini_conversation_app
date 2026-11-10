import os
import re
import sys
import json
import hashlib
import logging
from typing import Protocol
from pathlib import Path
from contextlib import ExitStack
from dataclasses import dataclass

from reachy_mini_conversation_app.document_assets import (
    AssetOperation,
    PreparationError,
    PreparationResult,
    PreparationArgumentParser,
    checkout_root,
    validate_paths,
    validate_receipt,
    source_line_numbers,
    run_preparation_worker,
    load_preparation_scheme,
    report_preparation_failure,
)
from reachy_mini_conversation_app.document_retrieval import valid_display_text


logger = logging.getLogger(__name__)


class SourceTokenizer(Protocol):
    """Expose source offsets and exact untruncated counts without importing inference."""

    def offsets(self, text: str) -> list[tuple[int, int]]:
        """Return content-token offsets relative to the exact supplied text."""
        ...

    def encoded_count(self, text: str) -> int:
        """Count the actual text including special tokens without truncation."""
        ...


@dataclass(frozen=True)
class SourceHeading:
    """Locate one original ATX heading without its Markdown delimiter."""

    text: str
    start: int
    end: int
    line_start: int
    line_end: int


@dataclass(frozen=True)
class SourceRange:
    """Keep one adjacent chapter range and its actual heading ancestry."""

    start: int
    end: int
    headings: tuple[SourceHeading, ...]


@dataclass(frozen=True)
class SourceChunk:
    """Preserve the original passage separately from its fixed retrieval context."""

    chunk_id: str
    document_id: str
    document_version: str
    start: int
    end: int
    line_start: int
    line_end: int
    text: str
    headings: tuple[SourceHeading, ...]
    aliases: list[dict[str, object]]
    context: str
    alias_context: str
    model_text: str
    model_text_sha256: str

    @property
    def locator(self) -> str:
        """Describe true source lines and the half-open character interval."""
        return f"L{self.line_start}-L{self.line_end}; chars[{self.start},{self.end})"


def _checked_offsets(tokenizer: SourceTokenizer, text: str) -> list[tuple[int, int]]:
    offsets = tokenizer.offsets(text)
    previous = (0, 0)
    for start, end in offsets:
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start <= end <= len(text)
            or start < previous[0]
            or end < previous[1]
        ):
            raise PreparationError("model_incompatible", 3)
        previous = (start, end)
    return offsets


def chapter_ranges(text: str, markdown: bool) -> tuple[list[SourceRange], set[tuple[int, int]]]:
    """Find original ATX sections and valid alias subtree scopes outside fenced code."""
    headings: list[tuple[int, int, SourceHeading]] = []
    fence_character, fence_length = "", 0
    position = 0
    for number, line in enumerate(re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text), 1):
        content = line.rstrip("\r\n")
        if markdown:
            fence = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", content)
            if fence_character:
                if (
                    fence is not None
                    and fence[1][0] == fence_character
                    and len(fence[1]) >= fence_length
                    and not fence[2].strip()
                ):
                    fence_character, fence_length = "", 0
            elif fence is not None and (fence[1][0] == "~" or "`" not in fence[2]):
                fence_character, fence_length = fence[1][0], len(fence[1])
            else:
                match = re.fullmatch(r" {0,3}(#{1,6})(?:[ \t]+(.*)|$)", content)
                if match is not None:
                    label = match[2] or ""
                    left = match.start(2) if match[2] is not None else len(content)
                    closing = re.search(r"[ \t]+#+[ \t]*$", label)
                    if closing is not None:
                        label = label[: closing.start()]
                    elif label and set(label.strip()) == {"#"}:
                        label = ""
                    leading = len(label) - len(label.lstrip(" \t"))
                    label = label.strip(" \t")
                    first = position + left + leading
                    headings.append(
                        (position, len(match[1]), SourceHeading(label, first, first + len(label), number, number))
                    )
        position += len(line)
    if not headings:
        return [SourceRange(0, len(text), ())], {(0, len(text))}
    ranges: list[SourceRange] = []
    scopes = {(0, len(text))}
    if headings[0][0] > 0:
        ranges.append(SourceRange(0, headings[0][0], ()))
        scopes.add((0, headings[0][0]))
    ancestry: list[tuple[int, SourceHeading]] = []
    for ordinal, (start, level, heading) in enumerate(headings):
        while ancestry and ancestry[-1][0] >= level:
            ancestry.pop()
        ancestry.append((level, heading))
        stop = headings[ordinal + 1][0] if ordinal + 1 < len(headings) else len(text)
        ranges.append(SourceRange(start, stop, tuple(item[1] for item in ancestry)))
        subtree_end = next((item[0] for item in headings[ordinal + 1 :] if item[1] <= level), len(text))
        scopes.add((start, subtree_end))
    return ranges, scopes


def verified_aliases(
    value: dict[str, object] | None,
    text: str,
    document_id: str,
    document_version: str,
    source_sha256: str,
    scopes: set[tuple[int, int]],
) -> list[dict[str, object]]:
    """Require every manual alias to match original evidence and a genuine source scope."""
    if value is None:
        return []
    if (
        set(value) != {"schema_version", "document_id", "document_version", "source_sha256", "aliases"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["document_id"] != document_id
        or value["document_version"] != document_version
        or value["source_sha256"] != source_sha256
        or not isinstance(value["aliases"], list)
    ):
        raise PreparationError("invalid_aliases", 2)
    accepted: list[dict[str, object]] = []
    for alias in value["aliases"]:
        if (
            not isinstance(alias, dict)
            or set(alias) != {"text", "evidence_start", "evidence_end", "scope_start", "scope_end"}
            or not isinstance(alias["text"], str)
        ):
            raise PreparationError("invalid_aliases", 2)
        positions = [alias[key] for key in ("evidence_start", "evidence_end", "scope_start", "scope_end")]
        if any(type(position) is not int for position in positions):
            raise PreparationError("invalid_aliases", 2)
        start, end, scope_start, scope_end = positions
        if (
            not 0 <= scope_start <= start < end <= scope_end <= len(text)
            or (scope_start, scope_end) not in scopes
            or alias["text"] != text[start:end]
            or alias in accepted
        ):
            raise PreparationError("invalid_aliases", 2)
        accepted.append(dict(alias))
    return accepted


def _context_tail(text: str, tokenizer: SourceTokenizer, limit: int) -> str:
    offsets = _checked_offsets(tokenizer, text)
    if len(offsets) <= limit:
        return text
    start = offsets[-limit][0]
    while start < len(text):
        if text[start - 1 : start + 1] == "\r\n":
            start += 1
            continue
        candidate = text[start:]
        if len(_checked_offsets(tokenizer, candidate)) <= limit:
            return candidate
        start += 1
    raise PreparationError("model_incompatible", 3)


def source_chunks(
    text: str,
    tokenizer: SourceTokenizer,
    document_id: str,
    document_version: str,
    source_sha256: str,
    *,
    source_name: str,
    markdown: bool,
    aliases: dict[str, object] | None = None,
) -> list[SourceChunk]:
    """Apply chapter-source-v1 with complete source coverage and source-verified context."""
    if not any(character.isalnum() for character in text):
        raise PreparationError("invalid_document", 2)
    if not source_name or Path(source_name).name != source_name or any(c in source_name for c in ("/", "\\")):
        raise PreparationError("invalid_document", 2)
    ranges, scopes = chapter_ranges(text, markdown)
    original_aliases = verified_aliases(aliases, text, document_id, document_version, source_sha256, scopes)
    canonical_aliases = json.dumps(original_aliases, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    alias_digest = hashlib.sha256(canonical_aliases.encode("utf-8")).hexdigest()
    scheme = load_preparation_scheme()
    configuration = {
        "strategy": scheme["strategy"],
        "chunking": scheme["chunking"],
        "embedding_model_id": "BAAI/bge-m3",
        "embedding_revision": "50f9396f75618b3389c1fd1068a1ff58dc7b5b26",
    }
    configuration_digest = hashlib.sha256(
        json.dumps(configuration, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    lines = source_line_numbers(text)
    chunks: list[SourceChunk] = []
    for section in ranges:
        context = _context_tail(
            " > ".join(heading.text for heading in section.headings[-3:]) if section.headings else source_name,
            tokenizer,
            64,
        )
        expanded: list[dict[str, object]] = []
        names: list[str] = []
        for alias in original_aliases:
            scope_start, scope_end = alias["scope_start"], alias["scope_end"]
            if not isinstance(scope_start, int) or not isinstance(scope_end, int):
                raise PreparationError("invalid_aliases", 2)
            if scope_start <= section.start and section.end <= scope_end:
                first, last = alias["evidence_start"], alias["evidence_end"]
                if not isinstance(first, int) or not isinstance(last, int):
                    raise PreparationError("invalid_aliases", 2)
                expanded.append({**alias, "evidence_line_start": lines[first], "evidence_line_end": lines[last - 1]})
                name = str(alias["text"])
                if name not in names:
                    names.append(name)
        alias_context = _context_tail(" / ".join(names), tokenizer, 48)
        prefix = f"脈絡：{context}\n" + (f"戰隊別名：{alias_context}\n" if alias_context else "") + "原文：\n"
        start = section.start
        while start < section.end:
            offsets = _checked_offsets(tokenizer, text[start : section.end])
            ends = [end for first, end in offsets[:300] if end > first]
            end = section.end if len(offsets) <= 300 else start + max(ends) if ends else min(start + 512, section.end)
            if end < section.end:
                position = start
                blank_boundaries: list[int] = []
                for line in re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text[start:end]):
                    if not line.strip() and start + (end - start) // 2 <= position < end:
                        blank_boundaries.append(position)
                    position += len(line)
                if blank_boundaries:
                    end = blank_boundaries[-1]
            if text[end - 1 : end + 1] == "\r\n":
                end -= 1
            if end <= start:
                end = start + 1
                if text[end - 1 : end + 1] == "\r\n":
                    end += 1
            while end > start:
                count = tokenizer.encoded_count(prefix + text[start:end])
                if count < 0:
                    raise PreparationError("model_incompatible", 3)
                if count <= 512:
                    break
                end -= 1
                if text[end - 1 : end + 1] == "\r\n":
                    end -= 1
            if end <= start:
                raise PreparationError("model_incompatible", 3)
            model_text = prefix + text[start:end]
            model_digest = hashlib.sha256(model_text.encode("utf-8")).hexdigest()
            identity = {
                "document_id": document_id,
                "document_version": document_version,
                "source_sha256": source_sha256,
                "policy": "chapter-source-v1",
                "configuration_sha256": configuration_digest,
                "aliases_sha256": alias_digest,
                "model_text_sha256": model_digest,
                "start": start,
                "end": end,
            }
            identifier = (
                "c-"
                + hashlib.sha256(
                    json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
            )
            chunks.append(
                SourceChunk(
                    identifier,
                    document_id,
                    document_version,
                    start,
                    end,
                    lines[start],
                    lines[end - 1],
                    text[start:end],
                    section.headings,
                    expanded,
                    context,
                    alias_context,
                    model_text,
                    model_digest,
                )
            )
            if end == section.end:
                break
            accepted = _checked_offsets(tokenizer, text[start:end])
            next_start = end
            if len(accepted) > 30:
                overlap_start, overlap_end = accepted[-30]
                proposed = start + overlap_start
                if overlap_end > overlap_start and start < proposed < end:
                    if text[proposed - 1 : proposed + 1] == "\r\n":
                        proposed += 1
                    if proposed < end:
                        next_start = proposed
            start = next_start
    return chunks


def main(argv: list[str] | None = None) -> int:
    """Build and independently verify a single local TXT or Markdown document package."""
    parser = PreparationArgumentParser(description="使用本機模型離線產生單文件索引包。", allow_abbrev=False)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--document-version", required=True)
    parser.add_argument("--index-version", required=True)
    parser.add_argument("--scheme", required=True, choices=("bge-base-final-selection-20261109",))
    parser.add_argument("--reranker-model", type=Path)
    parser.add_argument("--aliases", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replace", action="store_true")
    supplied = sys.argv[1:] if argv is None else argv
    if sum(argument == "--input" or argument.startswith("--input=") for argument in supplied) > 1:
        parser.error("只能指定一份文件，不可重複 --input。")
    arguments = parser.parse_args(supplied)
    operation: AssetOperation | None = None
    try:
        source = arguments.input.absolute()
        if source.suffix.lower() not in (".txt", ".md", ".markdown") or not source.is_file():
            raise PreparationError("invalid_document", 2)
        for identifier in (arguments.document_id, arguments.document_version, arguments.index_version):
            if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}", identifier) is None:
                raise PreparationError("invalid_arguments", 2)
        title = arguments.title
        if not valid_display_text(title, 160):
            raise PreparationError("invalid_arguments", 2)
        repository = checkout_root()
        if repository is None and any(
            value is None for value in (arguments.model, arguments.reranker_model, arguments.output)
        ):
            raise PreparationError("invalid_arguments", 2)
        model = (arguments.model or Path(str(repository)) / "external_content/bge-m3-model").absolute()
        reranker = (
            arguments.reranker_model or Path(str(repository)) / "external_content/bge-reranker-base-model"
        ).absolute()
        output = (arguments.output or Path(str(repository)) / "external_content/document-package").absolute()
        aliases = arguments.aliases.absolute() if arguments.aliases is not None else None
        if aliases is not None and (not aliases.is_file() or aliases.resolve() == source.resolve()):
            raise PreparationError("invalid_aliases", 2)
        inputs = [source, model, reranker] + ([aliases] if aliases is not None else [])
        validate_paths(output, inputs)
        validate_paths(model, [path for path in inputs if path != model])
        validate_paths(reranker, [path for path in inputs if path != reranker])
        if model.resolve() == reranker.resolve():
            raise PreparationError("unsafe_path", 4)
        for directory in (model, reranker):
            if not directory.is_dir() or not (directory / "model-receipt.json").is_file():
                raise PreparationError("model_not_ready", 3)
        model_operations: list[AssetOperation] = []
        with ExitStack() as locks:
            for directory in sorted((model, reranker), key=lambda path: os.path.normcase(str(path.resolve()))):
                model_operations.append(locks.enter_context(AssetOperation(directory, "model", replace=True)))
            if validate_receipt(model)["role"] != "embedding" or validate_receipt(reranker)["role"] != "reranker":
                raise PreparationError("model_incompatible", 3)
            operation = AssetOperation(output, "package", arguments.replace)
            with operation:
                request: dict[str, object] = {
                    "operation": "produce",
                    "source": str(source),
                    "model": str(model.resolve()),
                    "reranker_model": str(reranker.resolve()),
                    "stage": str(operation.stage),
                    "document_id": arguments.document_id,
                    "title": title,
                    "document_version": arguments.document_version,
                    "index_version": arguments.index_version,
                    "scheme": arguments.scheme,
                    "policy": "chapter-source-v1",
                }
                if aliases is not None:
                    request["aliases"] = str(aliases)
                try:
                    result = run_preparation_worker(request, operation)
                    operation.record("validating")
                    request["operation"] = "verify-package"
                    run_preparation_worker(request, operation)
                    validate_paths(output, inputs)
                    validate_paths(model, [path for path in inputs if path != model])
                    validate_paths(reranker, [path for path in inputs if path != reranker])
                    operation.record("validated")
                    operation.publish()
                except BaseException:
                    if operation.preserve:
                        for model_operation in model_operations:
                            model_operation.preserve = True
                    raise
        print(f"文件索引包準備完成：{operation.destination}；段落數 {result['count']}")
        print(f"REACHY_MINI_DOCUMENT_INDEX_PATH={operation.destination}")
        print(f"REACHY_MINI_DOCUMENT_MODEL_PATH={model.resolve()}")
        print(f"REACHY_MINI_DOCUMENT_RERANKER_PATH={reranker.resolve()}")
        print(PreparationResult("completed", True, True, "completed", 0).describe())
        return 0
    except PreparationError as error:
        return report_preparation_failure(error.code, error.exit_code, operation)
    except KeyboardInterrupt:
        return report_preparation_failure("cancelled", 130, operation)
    except (OSError, ValueError, TypeError, KeyError) as error:
        logger.warning("Preparation failed: %s", type(error).__name__)
        return report_preparation_failure("io_failed", 7, operation)


if __name__ == "__main__":
    raise SystemExit(main())
