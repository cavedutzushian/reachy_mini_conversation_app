import os
import re
import json
import shutil
import hashlib
import logging
import argparse
from pathlib import Path

from httpx import HTTPError
from huggingface_hub import HfApi, hf_hub_download, snapshot_download

from reachy_mini_conversation_app.document_assets import (
    MODEL_ID,
    PAYLOAD_FILES,
    AssetOperation,
    PreparationError,
    PreparationResult,
    checkout_root,
    validate_receipt,
    run_preparation_worker,
)


logger = logging.getLogger(__name__)
ENDPOINT = "https://huggingface.co"


def main(argv: list[str] | None = None) -> int:
    """Download one explicitly pinned safe BGE-M3 snapshot and verify it offline."""
    parser = argparse.ArgumentParser(description="下載指定版本的 BGE-M3 模型，離線驗證後發布。", allow_abbrev=False)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replace", action="store_true")
    arguments = parser.parse_args(argv)
    operation: AssetOperation | None = None
    try:
        if re.fullmatch(r"[0-9a-f]{40}", arguments.revision) is None:
            raise PreparationError("invalid_arguments", 2)
        repository = checkout_root()
        if arguments.output is None and repository is None:
            raise PreparationError("invalid_arguments", 2)
        output = arguments.output or Path(str(repository)) / "external_content/bge-m3-model"
        operation = AssetOperation(output, "model", replace=True)
        with operation:
            if operation.destination.exists():
                try:
                    receipt = validate_receipt(operation.destination)
                except (OSError, ValueError, PreparationError) as error:
                    logger.warning("Existing model did not validate: %s", type(error).__name__)
                else:
                    if receipt["revision"] == arguments.revision:
                        print(PreparationResult("already_ready", False, True, "already_ready", 0).describe())
                        print(f"模型已就緒：{operation.destination}；版本 {arguments.revision}")
                        return 0
                if not arguments.replace:
                    raise PreparationError("destination_exists", 4)
            if os.environ.get("HF_HUB_OFFLINE", "").lower() in ("1", "true", "yes"):
                raise PreparationError("download_unavailable", 5)
            information = HfApi(endpoint=ENDPOINT, token=False).model_info(
                MODEL_ID, revision=arguments.revision, files_metadata=True
            )
            if information.sha != arguments.revision or information.siblings is None:
                raise PreparationError("unsupported_revision", 3)
            siblings = {entry.rfilename: entry for entry in information.siblings}
            if not set(PAYLOAD_FILES).issubset(siblings):
                raise PreparationError("unsupported_revision", 3)
            transport = operation.lock / "transport"
            cache = operation.lock / "download-cache"
            small_files = (
                "config.json",
                "config_sentence_transformers.json",
                "modules.json",
                "sentence_bert_config.json",
                "1_Pooling/config.json",
            )
            for name in small_files:
                hf_hub_download(
                    MODEL_ID,
                    name,
                    revision=arguments.revision,
                    endpoint=ENDPOINT,
                    token=False,
                    cache_dir=cache,
                    local_dir=transport,
                )
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
            snapshot_download(
                MODEL_ID,
                revision=arguments.revision,
                endpoint=ENDPOINT,
                token=False,
                allow_patterns=list(PAYLOAD_FILES),
                cache_dir=cache,
                local_dir=transport,
            )
            for name in PAYLOAD_FILES:
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
                {"operation": "verify-model", "model": str(operation.stage), "revision": arguments.revision}, operation
            )
            validate_receipt(operation.stage)
            operation.record("validated")
            operation.publish()
        print(f"模型準備完成：{operation.destination}；版本 {arguments.revision}")
        print(f"REACHY_MINI_DOCUMENT_MODEL_PATH={operation.destination}")
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
        logger.warning("Model preparation outcome: %s", error.code)
        if operation is not None and operation.published:
            print(f"已發布，清理未完成：{operation.destination}；請核對 {operation.lock} 後人工清理，不要自動重跑。")
        else:
            print(f"模型準備未完成：{error.code}")
        return error.exit_code
    except KeyboardInterrupt:
        if operation is not None and operation.published:
            print(f"已發布，清理未完成：{operation.destination}；請核對 {operation.lock}，不要自動重跑。")
            return 8
        print("已取消模型準備；請核對本次操作記錄。")
        return 130
    except HTTPError as error:
        logger.warning("Model download failed: %s", type(error).__name__)
        print("目前無法下載指定模型，請稍後手動重試。")
        return 5
    except (OSError, ValueError, TypeError, KeyError) as error:
        logger.warning("Model preparation failed: %s", type(error).__name__)
        print("模型準備失敗，請檢查版本、檔案與儲存空間。")
        return 7


if __name__ == "__main__":
    raise SystemExit(main())
