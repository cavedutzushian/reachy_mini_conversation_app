import re
import sys
import json
import math
import hashlib
import logging
import argparse
from typing import Protocol
from pathlib import Path
from dataclasses import dataclass

from reachy_mini_conversation_app.document_assets import (
    AssetOperation,
    PreparationError,
    PreparationResult,
    checkout_root,
    validate_paths,
    validate_receipt,
    run_preparation_worker,
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
class SourceChunk:
    """Preserve an original source interval and its deterministic citation identity."""

    chunk_id: str
    start: int
    end: int
    text: str
    locator: str


def _checked_offsets(tokenizer: SourceTokenizer, text: str) -> list[tuple[int, int]]:
    offsets = tokenizer.offsets(text)
    previous = (0, 0)
    for start, end in offsets:
        if not 0 <= start <= end <= len(text) or start < previous[0] or end < previous[1]:
            raise PreparationError("model_incompatible", 3)
        previous = (start, end)
    return offsets


def source_chunks(
    text: str, tokenizer: SourceTokenizer, document_id: str, document_version: str, source_sha256: str
) -> list[SourceChunk]:
    """Apply the fixed source-window-v1 policy without rewriting any source character."""
    if not any(character.isalnum() for character in text):
        raise PreparationError("invalid_document", 2)
    line_numbers: list[int] = []
    line = 1
    for position, character in enumerate(text):
        line_numbers.append(line)
        if character == "\n" or character == "\r" and text[position + 1 : position + 2] != "\n":
            line += 1
    chunks: list[SourceChunk] = []
    start = 0
    while start < len(text):
        remaining = text[start:]
        offsets = _checked_offsets(tokenizer, remaining)
        ends = [token_end for token_start, token_end in offsets[:400] if token_end > token_start]
        end = len(text) if len(offsets) <= 400 else start + max(ends) if ends else min(start + 512, len(text))
        if text[end - 1 : end + 1] == "\r\n":
            end -= 1
        if end <= start:
            end = start + 1
            if text[end - 1 : end + 1] == "\r\n":
                end += 1
        while end > start:
            count = tokenizer.encoded_count(text[start:end])
            if count < 0:
                raise PreparationError("model_incompatible", 3)
            if count <= 512:
                break
            end -= 1
            if text[end - 1 : end + 1] == "\r\n":
                end -= 1
        if end <= start:
            raise PreparationError("model_incompatible", 3)
        identity = json.dumps(
            {
                "document_id": document_id,
                "document_version": document_version,
                "source_sha256": source_sha256,
                "policy": "source-window-v1",
                "start": start,
                "end": end,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        chunks.append(
            SourceChunk(
                "c-" + hashlib.sha256(identity).hexdigest(),
                start,
                end,
                text[start:end],
                f"L{line_numbers[start]}-L{line_numbers[end - 1]}; chars[{start},{end})",
            )
        )
        if end == len(text):
            break
        accepted_offsets = _checked_offsets(tokenizer, text[start:end])
        next_start = end
        if len(accepted_offsets) > 50:
            overlap_start, overlap_end = accepted_offsets[-50]
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
    parser = argparse.ArgumentParser(description="使用本機模型離線產生單文件索引包。", allow_abbrev=False)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--document-version", required=True)
    parser.add_argument("--index-version", required=True)
    parser.add_argument("--max-distance", required=True, type=float)
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
        if not math.isfinite(arguments.max_distance) or not 0 <= arguments.max_distance <= 2:
            raise PreparationError("invalid_distance", 2)
        repository = checkout_root()
        if repository is None and (arguments.model is None or arguments.output is None):
            raise PreparationError("invalid_arguments", 2)
        model = arguments.model or Path(str(repository)) / "external_content/bge-m3-model"
        output = arguments.output or Path(str(repository)) / "external_content/document-package"
        validate_paths(output, [source, model])
        if source.resolve().is_relative_to(model.resolve()) or model.resolve().is_relative_to(source.resolve()):
            raise PreparationError("unsafe_path", 4)
        validate_paths(model, [])
        if not model.is_dir() or not (model / "model-receipt.json").is_file():
            raise PreparationError("model_not_ready", 3)
        with AssetOperation(model, "model", replace=True):
            validate_receipt(model)
            operation = AssetOperation(output, "package", arguments.replace)
            with operation:
                request: dict[str, object] = {
                    "operation": "produce",
                    "source": str(source),
                    "model": str(model.resolve()),
                    "stage": str(operation.stage),
                    "document_id": arguments.document_id,
                    "title": title,
                    "document_version": arguments.document_version,
                    "index_version": arguments.index_version,
                    "max_distance": arguments.max_distance,
                    "policy": "source-window-v1",
                }
                result = run_preparation_worker(request, operation)
                operation.record("validating")
                request["operation"] = "verify-package"
                run_preparation_worker(request, operation)
                operation.record("validated")
                operation.publish()
        print(f"文件索引包準備完成：{operation.destination}；段落數 {result['count']}")
        print(f"REACHY_MINI_DOCUMENT_INDEX_PATH={operation.destination}")
        print(f"REACHY_MINI_DOCUMENT_MODEL_PATH={model.resolve()}")
        print(PreparationResult("completed", True, True, "completed", 0).describe())
        return 0
    except PreparationError as error:
        published = operation is not None and operation.published
        print(
            PreparationResult(
                "recovery_required"
                if error.exit_code == 8
                else "busy"
                if error.code == "destination_busy"
                else "failed",
                published,
                True if published else None,
                error.code,
                error.exit_code,
            ).describe()
        )
        logger.warning("Document preparation outcome: %s", error.code)
        if operation is not None and operation.published:
            print(f"已發布，清理未完成：{operation.destination}；請核對 {operation.lock} 後人工清理，不要自動重跑。")
        else:
            print(f"文件索引包未完成：{error.code}")
        return error.exit_code
    except KeyboardInterrupt:
        if operation is not None and operation.published:
            print(f"已發布，清理未完成：{operation.destination}；請核對 {operation.lock}，不要自動重跑。")
            return 8
        print("已取消文件產包，請核對本次操作記錄。")
        return 130
    except (OSError, ValueError, TypeError, KeyError) as error:
        logger.warning("Document preparation failed: %s", type(error).__name__)
        print("文件產包失敗，請檢查本機模型、UTF-8 文件與儲存空間。")
        return 7


if __name__ == "__main__":
    raise SystemExit(main())
