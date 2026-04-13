"""Search enhancement: re-ranking, query expansion, multi-language segmentation."""
import re
from typing import Optional

import jieba

from kbase.config import LANGUAGE_PROFILES


# ============================================================
# 1. Multi-Language Segmentation
# ============================================================

def segment_text(text: str, language: str = "zh-en") -> str:
    """Segment text based on language profile."""
    profile = LANGUAGE_PROFILES.get(language, LANGUAGE_PROFILES["zh-en"])
    segmenter = profile.get("segmenter", "jieba")

    if segmenter == "jieba":
        return segment_chinese(text)
    elif segmenter == "mecab":
        return _segment_mecab(text)
    elif segmenter == "whitespace":
        return text  # English uses whitespace naturally
    elif segmenter == "auto":
        return _segment_auto(text)
    return text


def segment_chinese(text: str) -> str:
    """Segment Chinese text with jieba for better FTS5 matching."""
    words = jieba.cut(text, cut_all=False)
    return " ".join(words)


def _segment_mecab(text: str) -> str:
    """Segment Japanese/Korean with MeCab."""
    try:
        import MeCab
        tagger = MeCab.Tagger("-Owakati")
        return tagger.parse(text).strip()
    except ImportError:
        return segment_chinese(text)  # Fallback to jieba


def _segment_auto(text: str) -> str:
    """Auto-detect language and segment accordingly."""
    # Simple heuristic: check character ranges
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    jp_count = sum(1 for c in text if '\u3040' <= c <= '\u30ff')
    total = len(text) or 1

    if jp_count / total > 0.1:
        return _segment_mecab(text)
    elif cjk_count / total > 0.1:
        return segment_chinese(text)
    return text  # English/other


# ============================================================
# 2. Query Expansion (synonym + related terms)
# ============================================================

# Common Chinese business/tech synonyms
SYNONYM_MAP = {
    "营收": ["收入", "revenue", "营业收入"],
    "收入": ["营收", "revenue", "营业收入"],
    "数据治理": ["data governance", "数据管理", "数据质量"],
    "数据管理": ["data management", "数据治理"],
    "架构": ["architecture", "系统架构", "技术架构"],
    "IT架构": ["系统架构", "技术架构", "IT architecture"],
    "预算": ["budget", "OPEX", "CAPEX", "经费"],
    "投资": ["investment", "投入", "资金"],
    "用户": ["客户", "customer", "user"],
    "客户": ["用户", "customer"],
    "平台": ["platform", "系统"],
    "系统": ["system", "平台", "应用"],
    "项目": ["project", "工程"],
    "方案": ["plan", "计划", "规划"],
    "规划": ["planning", "方案", "计划"],
    "会议": ["meeting", "会议纪要"],
    "汇报": ["report", "报告", "presentation"],
    "报告": ["report", "汇报"],
    "安全": ["security", "数据安全", "网络安全"],
    "智算": ["AI computing", "智能计算", "算力"],
    "云": ["cloud", "云计算", "云平台"],
    "转型": ["transformation", "数智化转型"],
    "运维": ["operation", "运营维护", "O&M"],
    "网络": ["network", "网络部"],
    "市场": ["market", "市场部", "marketing"],
    "财务": ["finance", "财务部"],
    "采购": ["procurement", "供应链"],
    "数用": ["用数", "数据应用", "数据使用", "数据消费", "治数用数"],
    "用数": ["数用", "数据应用", "数据使用", "治数用数"],
    "数据应用": ["数用", "用数", "data application", "数据消费"],
    "标准": ["standard", "规范", "标准化"],
    "规范": ["standard", "标准", "规范化"],
    "非结构化": ["unstructured", "非结构化数据"],
    "结构化": ["structured", "结构化数据"],
    "治理": ["governance", "管控", "管理"],
    "数据中台": ["data platform", "数据平台", "数据中心"],
    "数据平台": ["data platform", "数据中台"],
    "指标": ["metric", "KPI", "指标体系"],
    "评价": ["evaluation", "考核", "评估"],
    "考核": ["assessment", "评价", "绩效"],
    "BSS": ["业务支撑", "business support"],
    "OSS": ["运营支撑", "operation support"],
    "大数据": ["big data", "数据分析"],
    "AI": ["人工智能", "artificial intelligence", "机器学习"],
    "5G": ["五G", "第五代移动通信"],
    "IoT": ["物联网", "internet of things"],
    "元数据": ["metadata", "数据字典"],
    "数据字典": ["metadata", "元数据", "data dictionary"],
    "数据质量": ["data quality", "质量管控"],
    "数据资产": ["data asset", "数据资产管理"],
    "数仓": ["data warehouse", "数据仓库"],
    "数据仓库": ["data warehouse", "数仓"],
    "ETL": ["数据集成", "数据抽取"],
    "API": ["接口", "interface", "api"],
    "接口": ["API", "interface"],
}


def expand_query(query: str) -> str:
    """Expand query with synonyms for better recall."""
    expanded_terms = set()
    expanded_terms.add(query)

    # Check full query and n-grams against synonym map
    # First: check full query
    if query in SYNONYM_MAP:
        for syn in SYNONYM_MAP[query][:3]:
            expanded_terms.add(syn)

    # Then: check all contiguous substrings (2-6 chars)
    for length in range(2, min(7, len(query) + 1)):
        for start in range(len(query) - length + 1):
            substr = query[start:start + length]
            if substr in SYNONYM_MAP:
                for syn in SYNONYM_MAP[substr][:2]:
                    expanded_terms.add(syn)

    # Also check jieba-segmented words
    words = list(jieba.cut(query, cut_all=False))
    for word in words:
        word = word.strip()
        if len(word) < 2:
            continue
        if word in SYNONYM_MAP:
            for syn in SYNONYM_MAP[word][:2]:
                expanded_terms.add(syn)

    return " ".join(expanded_terms)


# ============================================================
# 3. HyDE — Hypothetical Document Embedding
# ============================================================

def generate_hyde(query: str, llm_func=None) -> str:
    """Generate a hypothetical document that would answer the query.

    HyDE (Gao et al. 2022): instead of embedding the short query,
    we generate a hypothetical answer and embed THAT — the embedding
    of a document-like text matches real documents much better than
    a short query embedding.

    Args:
        query: User's search query
        llm_func: Callable that takes (prompt) → str. If None, returns query unchanged.
    """
    if not llm_func:
        return query

    prompt = f"""Please write a short paragraph (100-200 words) that would be a good answer to this question.
Write it as if it's an excerpt from a real document. Include specific details, numbers, and terminology.
Do NOT say "I don't know" or ask clarifying questions. Just write the hypothetical document content.

Question: {query}

Hypothetical document excerpt:"""

    try:
        hyde_doc = llm_func(prompt)
        if hyde_doc and len(hyde_doc) > 20:
            return hyde_doc[:500]  # Truncate to reasonable embedding length
    except Exception:
        pass
    return query


# ============================================================
# 4. Multi-Query Expansion (LLM-powered)
# ============================================================

def generate_multi_queries(query: str, llm_func=None, n: int = 3) -> list[str]:
    """Generate multiple search queries from different angles.

    Inspired by RAG-Fusion: generate diverse queries to cover
    different aspects and phrasings of the user's intent.
    """
    if not llm_func:
        return [query]

    prompt = f"""Generate {n} different search queries for finding documents related to this question.
Each query should approach the topic from a different angle or use different keywords.
Output ONLY the queries, one per line. No numbering, no explanation.

Original question: {query}

Alternative queries:"""

    try:
        result = llm_func(prompt)
        queries = [q.strip() for q in result.strip().split("\n") if q.strip() and len(q.strip()) > 3]
        return [query] + queries[:n]
    except Exception:
        return [query]


# ============================================================
# 5. Re-ranking with Cross-Encoder
# ============================================================

_reranker = None


def get_reranker():
    """Lazy-load reranker model."""
    global _reranker
    if _reranker is None:
        try:
            from FlagEmbedding import FlagReranker
            _reranker = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True)
        except Exception:
            _reranker = "unavailable"
    return _reranker


def rerank_results(query: str, results: list, top_k: int = 10) -> list:
    """Re-rank search results using cross-encoder for better precision."""
    reranker = get_reranker()
    if reranker == "unavailable" or not results:
        return results[:top_k]

    # Prepare pairs
    pairs = []
    for r in results:
        text = r.get("text", "")[:512]  # Truncate for speed
        if text:
            pairs.append([query, text])
        else:
            pairs.append([query, "empty"])

    try:
        scores = reranker.compute_score(pairs, normalize=True)
        if isinstance(scores, (int, float)):
            scores = [scores]

        # Attach rerank scores and sort
        for i, r in enumerate(results):
            r["rerank_score"] = scores[i] if i < len(scores) else 0

        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return results[:top_k]
    except Exception:
        return results[:top_k]


# ============================================================
# 4. Contextual Chunk Enrichment
# ============================================================

def enrich_chunk_context(chunk_text: str, file_name: str, metadata: dict) -> str:
    """Add contextual prefix to chunk for better retrieval.

    Follows Anthropic's Contextual Retrieval approach:
    prepend document-level context to each chunk before embedding.
    """
    parts = [f"[File: {file_name}]"]

    title = metadata.get("title", "")
    if title and title != file_name:
        parts.append(f"[Title: {title}]")

    heading = metadata.get("heading", "")
    if heading:
        parts.append(f"[Section: {heading}]")

    slide = metadata.get("slide", "")
    if slide:
        parts.append(f"[Slide {slide}]")

    page = metadata.get("page", "")
    if page:
        parts.append(f"[Page {page}]")

    sheet = metadata.get("sheet", "")
    if sheet:
        parts.append(f"[Sheet: {sheet}]")

    context_prefix = " ".join(parts)
    return f"{context_prefix}\n{chunk_text}"
