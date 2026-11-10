import json
import hashlib
import importlib

import numpy as np
import pytest
from test_document_worker import document_index


__all__ = ["document_index"]


def test_shared_model_preserves_reader_cpu_encoding_contract(document_index) -> None:
    """Reader and preparation use the same checked CPU model and normalized vectors."""
    fixture = document_index
    module = importlib.import_module("reachy_mini_conversation_app.document_model")
    model = module.DocumentModel(fixture.model, fixture.manifest["embedding"], fixture.manifest["reference"])
    vector = model.encode("測試問題")
    assert vector.shape == (1024,) and vector.dtype == np.float32
    assert abs(float(np.linalg.norm(vector)) - 1) <= 1e-4
    options = fixture.sentence.SentenceTransformer.call_args.kwargs
    assert options["device"] == "cpu" and options["local_files_only"] is True
    assert options["trust_remote_code"] is False and options["model_kwargs"]["use_safetensors"] is True


def test_shared_encoder_rejects_invalid_output(document_index) -> None:
    """A malformed embedding cannot enter a receipt or index even after successful loading."""
    fixture = document_index
    module = importlib.import_module("reachy_mini_conversation_app.document_model")
    model = module.DocumentModel(fixture.model, fixture.manifest["embedding"], fixture.manifest["reference"])
    fixture.sentence.SentenceTransformer.return_value.encode.side_effect = None
    fixture.sentence.SentenceTransformer.return_value.encode.return_value = [[float("nan")]]
    with pytest.raises(ValueError, match="Invalid query vector"):
        model.encode("測試問題")


@pytest.mark.parametrize("invalid_output", [False, True])
def test_reranker_preserves_raw_scores_and_rejects_nonfinite_output(document_index, invalid_output: bool) -> None:
    """Raw single-label logits use local CPU safe weights without a sigmoid."""
    fixture = document_index
    module = importlib.import_module("reachy_mini_conversation_app.document_model")
    directory = fixture.model.parent / "reranker-unit"
    directory.mkdir()
    (directory / "config.json").write_text(
        json.dumps({"model_type": "xlm-roberta", "architectures": ["XLMRobertaForSequenceClassification"]}),
        encoding="utf-8",
    )
    (directory / "model.safetensors").write_bytes(b"synthetic; never loaded")
    from_inventory = [
        {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(directory.iterdir())
    ]
    fixture.sentence.CrossEncoder.return_value.num_labels = 1
    fixture.sentence.CrossEncoder.return_value.predict.return_value = np.array(
        [float("nan"), -2.0] if invalid_output else [4.5, -2.0], dtype=np.float32
    )
    reranker = module.DocumentReranker(directory, {"files": from_inventory})
    if invalid_output:
        with pytest.raises(ValueError, match="Invalid reranker output"):
            reranker.score("問題", ["原文甲", "原文乙"])
    else:
        assert reranker.score("問題", ["原文甲", "原文乙"]) == [4.5, -2.0]
        assert reranker.score("問題", []) == []
    options = fixture.sentence.CrossEncoder.call_args.kwargs
    assert options["device"] == "cpu" and options["local_files_only"] is True
    assert options["trust_remote_code"] is False and options["max_length"] == 512
    assert options["model_kwargs"]["use_safetensors"] is True
    fixture.sentence.CrossEncoder.return_value.predict.assert_called_once()
    assert fixture.sentence.CrossEncoder.return_value.predict.call_args.kwargs["batch_size"] == 4
    assert not module.torch.set_num_interop_threads.called


@pytest.mark.parametrize("question", ["Q" * 10, "Q" * 508])
def test_pair_scoring_preserves_query_and_returns_only_the_scored_source_prefix(document_index, question: str) -> None:
    """A long question is refused and a long passage is cut only on its right side."""
    from reachy_mini_conversation_app.document_assets import file_inventory

    fixture = document_index
    module = importlib.import_module("reachy_mini_conversation_app.document_model")

    class PairTokenizer:
        is_fast = True

        def __call__(self, first, second=None, **kwargs):
            if second is None:
                return {
                    "input_ids": list(range(len(first))),
                    "offset_mapping": [(position, position + 1) for position in range(len(first))],
                }
            return {"input_ids": list(range(len(first) + len(second) + 4))}

    encoder = fixture.sentence.CrossEncoder.return_value
    encoder.num_labels = 1
    encoder.tokenizer = PairTokenizer()
    encoder.predict.return_value = np.array([4.5], dtype=np.float32)
    reranker = module.DocumentReranker(fixture.reranker, {"files": file_inventory(fixture.reranker)})
    original = "X" * 600
    prefix = "脈絡：標題\n原文：\n"
    result = reranker.score_passages(question, [(prefix + original, original)])
    if len(question) == 508:
        assert result == []
        encoder.predict.assert_not_called()
    else:
        visible = original[: 512 - len(question) - 4 - len(prefix)]
        assert result == [(0, 4.5, visible, True)]
        assert encoder.predict.call_args.args[0] == [(question, prefix + visible)]
        assert len(question) + len(prefix + visible) + 4 == 512
