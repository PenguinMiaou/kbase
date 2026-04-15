"""Tests for kbase.chunk — smart document chunking."""
from kbase.chunk import chunk_document


class TestChunkDocument:
    def test_empty_text_returns_empty(self):
        assert chunk_document("", ".md") == []
        assert chunk_document("   ", ".txt") == []

    def test_short_text_single_chunk(self):
        chunks = chunk_document("Hello world", ".txt")
        children = [c for c in chunks if not c["metadata"].get("is_parent")]
        assert len(children) >= 1
        assert "Hello world" in children[0]["text"]

    def test_markdown_heading_split(self, sample_texts):
        chunks = chunk_document(sample_texts["long"], ".md")
        children = [c for c in chunks if not c["metadata"].get("is_parent")]
        assert len(children) > 1, "Long markdown should produce multiple chunks"

    def test_parent_chunks_generated(self, sample_texts):
        chunks = chunk_document(sample_texts["long"], ".md")
        parents = [c for c in chunks if c["metadata"].get("is_parent")]
        children = [c for c in chunks if not c["metadata"].get("is_parent")]
        if len(children) > 1:
            assert len(parents) >= 1, "Multiple children should generate parent chunks"

    def test_pptx_slide_split(self):
        slide_text = "--- Slide 1 ---\nSlide content 1\n--- Slide 2 ---\nSlide content 2"
        chunks = chunk_document(slide_text, ".pptx")
        assert len(chunks) >= 1

    def test_metadata_preserved(self):
        meta = {"source": "test.md", "custom": "value"}
        chunks = chunk_document("Some test content here.", ".md", metadata=meta)
        assert len(chunks) >= 1
        assert chunks[0]["metadata"]["source"] == "test.md"
        assert chunks[0]["metadata"]["custom"] == "value"

    def test_pdf_page_split(self):
        pages = "\n--- Page 1 ---\nPage one content.\n--- Page 2 ---\nPage two content."
        chunks = chunk_document(pages, ".pdf")
        assert len(chunks) >= 1
