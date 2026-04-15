"""Tests for kbase.config — configuration constants and helpers."""
from kbase.config import (
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP_CHARS,
    DEFAULT_TOP_K,
    EMBEDDING_MODELS,
    SUPPORTED_EXTENSIONS,
)


class TestConfigConstants:
    def test_supported_extensions_not_empty(self):
        assert len(SUPPORTED_EXTENSIONS) > 10

    def test_common_formats_supported(self):
        for ext in [".md", ".pdf", ".docx", ".pptx", ".xlsx", ".txt"]:
            assert ext in SUPPORTED_EXTENSIONS, f"{ext} should be supported"

    def test_chunk_sizes_sensible(self):
        assert 500 <= CHUNK_MAX_CHARS <= 5000
        assert CHUNK_OVERLAP_CHARS < CHUNK_MAX_CHARS

    def test_embedding_models_have_required_fields(self):
        for key, model in EMBEDDING_MODELS.items():
            assert "name" in model, f"{key} missing 'name'"
            assert "type" in model, f"{key} missing 'type'"
            assert model["type"] in ("local", "openai", "dashscope", "voyageai", "openai-compatible-emb"), \
                f"{key} has unexpected type: {model['type']}"

    def test_default_top_k(self):
        assert DEFAULT_TOP_K > 0
