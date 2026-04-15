"""Tests for kbase.enhance — query expansion, segmentation, synonym mapping."""
from kbase.enhance import expand_query, segment_chinese, segment_text


class TestExpandQuery:
    def test_synonym_expansion(self):
        result = expand_query("数据治理")
        assert "数据治理" in result
        assert "governance" in result or "数据管理" in result

    def test_no_expansion_for_unknown(self):
        result = expand_query("xyzzy12345")
        assert "xyzzy12345" in result

    def test_mixed_language_expansion(self):
        result = expand_query("AI平台")
        assert "AI" in result or "人工智能" in result

    def test_empty_query(self):
        result = expand_query("")
        assert isinstance(result, str)


class TestSegmentation:
    def test_chinese_segmentation(self):
        result = segment_chinese("数据治理是核心能力")
        assert " " in result, "Segmented text should have spaces"

    def test_segment_text_zh(self):
        result = segment_text("测试文本", language="zh-en")
        assert isinstance(result, str)

    def test_segment_text_english(self):
        result = segment_text("hello world", language="en")
        assert "hello" in result

    def test_segment_text_auto(self):
        result = segment_text("这是中文", language="auto")
        assert isinstance(result, str)
