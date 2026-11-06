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
