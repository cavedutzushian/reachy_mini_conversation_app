import os
import re
import json
import shutil
import hashlib
import logging
from pathlib import Path

from httpx import HTTPError
from huggingface_hub import HfApi, hf_hub_download, snapshot_download

from reachy_mini_conversation_app.document_assets import (
    MODEL_ID,
    RERANKER_ID,
    PAYLOAD_FILES,
    MODEL_REVISION,
    RERANKER_REVISION,
    RERANKER_PAYLOAD_FILES,
    AssetOperation,
    PreparationError,
    PreparationResult,
    PreparationArgumentParser,
    checkout_root,
    validate_receipt,
    run_preparation_worker,
    report_preparation_failure,
)


logger = logging.getLogger(__name__)
ENDPOINT = "https://huggingface.co"


def main(argv: list[str] | None = None) -> int:
    """Download one explicitly pinned model role and verify it offline."""
    parser = PreparationArgumentParser(description="依角色下載指定版本模型，離線驗證後發布。", allow_abbrev=False)
    parser.add_argument("--role", required=True, choices=("embedding", "reranker"))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replace", action="store_true")
    arguments = parser.parse_args(argv)
    operation: AssetOperation | None = None
    try:
        if re.fullmatch(r"[0-9a-f]{40}", arguments.revision) is None:
            raise PreparationError("invalid_arguments", 2)
        embedding = arguments.role == "embedding"
        setting = "REACHY_MINI_DOCUMENT_MODEL_PATH" if embedding else "REACHY_MINI_DOCUMENT_RERANKER_PATH"
        model_id = MODEL_ID if embedding else RERANKER_ID
        revision = MODEL_REVISION if embedding else RERANKER_REVISION
        payload_files = PAYLOAD_FILES if embedding else RERANKER_PAYLOAD_FILES
        if arguments.revision != revision:
            raise PreparationError("unsupported_revision", 3)
        repository = checkout_root()
        if arguments.output is None and repository is None:
            raise PreparationError("invalid_arguments", 2)
        output = arguments.output or Path(str(repository)) / "external_content" / (
            "bge-m3-model" if embedding else "bge-reranker-base-model"
        )
        operation = AssetOperation(output, "model", replace=True)
        with operation:
            if operation.destination.exists():
                try:
                    receipt = validate_receipt(operation.destination)
                except (OSError, ValueError, PreparationError) as error:
                    logger.warning("Existing model did not validate: %s", type(error).__name__)
                else:
                    if receipt["revision"] == arguments.revision and receipt["role"] == arguments.role:
                        print(PreparationResult("already_ready", False, True, "already_ready", 0).describe())
                        print(f"模型已就緒：{operation.destination}；角色 {arguments.role}；版本 {arguments.revision}")
                        print(f"{setting}={operation.destination}")
                        return 0
                if not arguments.replace:
                    raise PreparationError("destination_exists", 4)
            if os.environ.get("HF_HUB_OFFLINE", "").lower() in ("1", "true", "yes"):
                raise PreparationError("download_unavailable", 5)
            information = HfApi(endpoint=ENDPOINT, token=False).model_info(
                model_id, revision=arguments.revision, files_metadata=True
            )
            if information.sha != arguments.revision or information.siblings is None:
                raise PreparationError("unsupported_revision", 3)
            siblings = {entry.rfilename: entry for entry in information.siblings}
            if not set(payload_files).issubset(siblings):
                raise PreparationError("unsupported_revision", 3)
            transport = operation.lock / "transport"
            cache = operation.lock / "download-cache"
            small_files: tuple[str, ...] = (
                "config.json",
                "config_sentence_transformers.json",
                "modules.json",
                "sentence_bert_config.json",
                "1_Pooling/config.json",
            )
            if not embedding:
                small_files = ("config.json",)
            for name in small_files:
                hf_hub_download(
                    model_id,
                    name,
                    revision=arguments.revision,
                    endpoint=ENDPOINT,
                    token=False,
                    cache_dir=cache,
                    local_dir=transport,
                )
            if embedding:
                modules = json.loads((transport / "modules.json").read_bytes())
                if not isinstance(modules, list) or [entry.get("path") for entry in modules] != [
                    "",
                    "1_Pooling",
                    "2_Normalize",
                ]:
                    raise PreparationError("unsupported_revision", 3)
                pooling = json.loads((transport / "1_Pooling/config.json").read_bytes())
                tokenizer = json.loads((transport / "sentence_bert_config.json").read_bytes())
                if pooling.get("pooling_mode_cls_token") is not True or tokenizer.get("max_seq_length") != 8192:
                    raise PreparationError("unsupported_revision", 3)
            else:
                configuration = json.loads((transport / "config.json").read_bytes())
                if configuration.get("model_type") != "xlm-roberta" or configuration.get("architectures") != [
                    "XLMRobertaForSequenceClassification"
                ]:
                    raise PreparationError("unsupported_revision", 3)
            snapshot_download(
                model_id,
                revision=arguments.revision,
                endpoint=ENDPOINT,
                token=False,
                allow_patterns=list(payload_files),
                cache_dir=cache,
                local_dir=transport,
            )
            for name in payload_files:
                source = transport / name
                if not source.is_file() or source.is_symlink() or source.is_junction():
                    raise PreparationError("unsupported_revision", 3)
                sibling = siblings[name]
                if sibling.size is not None and source.stat().st_size != sibling.size:
                    raise PreparationError("validation_failed", 6)
                if sibling.lfs is not None:
                    with source.open("rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    if digest != sibling.lfs.sha256:
                        raise PreparationError("validation_failed", 6)
                elif sibling.blob_id is not None:
                    blob_digest = hashlib.sha1(f"blob {source.stat().st_size}\0".encode(), usedforsecurity=False)
                    with source.open("rb") as stream:
                        while block := stream.read(1024 * 1024):
                            blob_digest.update(block)
                    if blob_digest.hexdigest() != sibling.blob_id:
                        raise PreparationError("validation_failed", 6)
                target = operation.stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            operation.record("validating")
            run_preparation_worker(
                {
                    "operation": "verify-model",
                    "role": arguments.role,
                    "model": str(operation.stage),
                    "revision": arguments.revision,
                },
                operation,
            )
            validate_receipt(operation.stage)
            operation.record("validated")
            operation.publish()
        print(f"模型準備完成：{operation.destination}；角色 {arguments.role}；版本 {arguments.revision}")
        print(f"{setting}={operation.destination}")
        print(PreparationResult("completed", True, True, "completed", 0).describe())
        return 0
    except PreparationError as error:
        return report_preparation_failure(error.code, error.exit_code, operation)
    except KeyboardInterrupt:
        return report_preparation_failure("cancelled", 130, operation)
    except HTTPError as error:
        logger.warning("Model download failed: %s", type(error).__name__)
        return report_preparation_failure("download_unavailable", 5, operation)
    except (OSError, ValueError, TypeError, KeyError) as error:
        logger.warning("Preparation failed: %s", type(error).__name__)
        return report_preparation_failure("io_failed", 7, operation)


if __name__ == "__main__":
    raise SystemExit(main())
