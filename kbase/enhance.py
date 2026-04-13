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
# Generic Chinese↔English business/tech synonyms (no company-specific terms).
# Domain-specific terms should be auto-extracted into user glossary via /api/glossary/extract.
SYNONYM_MAP = {
    # ── Finance / Business ──
    "营收": ["收入", "revenue"],
    "收入": ["营收", "revenue"],
    "预算": ["budget", "经费"],
    "投资": ["investment", "投入"],
    "用户": ["客户", "customer", "user"],
    "客户": ["用户", "customer"],
    "项目": ["project", "工程"],
    "方案": ["plan", "计划", "规划"],
    "规划": ["planning", "方案"],
    "会议": ["meeting"],
    "汇报": ["report", "报告"],
    "报告": ["report", "汇报"],
    "采购": ["procurement", "供应链"],
    "指标": ["metric", "KPI"],
    "评价": ["evaluation", "考核"],
    "考核": ["assessment", "评价"],
    "标准": ["standard", "规范"],
    "规范": ["standard", "标准"],
    # ── Tech / IT ──
    "架构": ["architecture", "技术架构"],
    "平台": ["platform", "系统"],
    "系统": ["system", "平台"],
    "安全": ["security", "网络安全"],
    "云": ["cloud", "云计算"],
    "运维": ["operation", "O&M"],
    "网络": ["network"],
    "数据治理": ["data governance", "数据管理"],
    "数据管理": ["data management", "数据治理"],
    "数据平台": ["data platform"],
    "数据质量": ["data quality"],
    "数据资产": ["data asset"],
    "非结构化": ["unstructured"],
    "结构化": ["structured"],
    "治理": ["governance", "管理"],
    "元数据": ["metadata", "数据字典"],
    "数据字典": ["metadata", "元数据"],
    "数仓": ["data warehouse", "数据仓库"],
    "数据仓库": ["data warehouse", "数仓"],
    # ── Acronyms ──
    "大数据": ["big data"],
    "AI": ["人工智能", "artificial intelligence", "机器学习"],
    "5G": ["第五代移动通信"],
    "IoT": ["物联网", "internet of things"],
    "ETL": ["数据集成", "数据抽取"],
    "API": ["接口", "interface"],
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

def clean_text(text: str) -> str:
    """Clean text before embedding — remove noise that hurts retrieval quality.

    Applied in the Transform stage of the PTI pipeline (RAGFlow-inspired):
    1. Normalize whitespace (collapse multiple newlines/spaces)
    2. Remove zero-width and control characters
    3. Remove repeated headers/footers (common in PDF extraction)
    4. Strip page numbers and watermarks
    """
    if not text:
        return text

    # Remove zero-width chars and control chars (except newline/tab)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\u200c\u200d\ufeff\u00ad]', '', text)

    # Collapse 3+ consecutive newlines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Collapse runs of spaces/tabs (but not newlines) to single space
    text = re.sub(r'[^\S\n]{3,}', ' ', text)

    # Remove standalone page numbers (e.g. "- 12 -", "Page 12", "第12页")
    text = re.sub(r'^[\s]*[-–—]\s*\d+\s*[-–—][\s]*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*(?:Page|page|PAGE|第)\s*\d+\s*(?:页)?[\s]*$', '', text, flags=re.MULTILINE)

    # Remove common watermark patterns (repeated company disclaimers)
    text = re.sub(r'^[\s]*(CONFIDENTIAL|DRAFT|机密|内部资料|仅供参考)[\s]*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

    # Remove repeated header/footer lines: if same line appears 3+ times, it's a header/footer
    lines = text.split('\n')
    if len(lines) > 20:
        from collections import Counter
        line_counts = Counter(line.strip() for line in lines if len(line.strip()) > 3)
        repeated = {line for line, count in line_counts.items() if count >= 3}
        if repeated:
            lines = [line for line in lines if line.strip() not in repeated]
            text = '\n'.join(lines)

    return text.strip()


def deduplicate_chunks_cross_file(store, chunks: list[dict], file_path: str, threshold: float = 0.85) -> list[dict]:
    """Remove chunks that are near-duplicates of existing chunks from OTHER files.

    Key insight: in personal work directories, files have multiple versions
    (v1, v2, v3). We keep the NEWEST version's chunks and skip duplicates
    from older files.

    Args:
        store: KBaseStore with existing indexed data
        chunks: new chunks to be indexed
        file_path: path of the file being indexed
        threshold: similarity threshold for dedup (0-1)
    Returns:
        filtered chunks with near-duplicates removed
    """
    from difflib import SequenceMatcher
    from pathlib import Path
    import time

    if not chunks or len(chunks) < 2:
        return chunks

    # Get current file's modified time
    try:
        current_mtime = Path(file_path).stat().st_mtime
    except Exception:
        current_mtime = time.time()

    # Sample existing chunks from DB for comparison (limit to avoid slowness)
    try:
        c = store.conn.cursor()
        c.execute("""
            SELECT fc.text, f.file_path, f.modified_time
            FROM fts_chunks fc
            JOIN files f ON fc.file_id = f.file_id
            WHERE f.file_path != ?
            ORDER BY f.modified_time DESC
            LIMIT 500
        """, (file_path,))
        existing = [(row["text"], row["file_path"], row["modified_time"]) for row in c.fetchall()]
    except Exception:
        return chunks  # Can't query, skip dedup

    if not existing:
        return chunks

    # Build a quick lookup of existing chunk text snippets (first 200 chars for speed)
    existing_snippets = [(text[:200], mtime) for text, _, mtime in existing]

    kept = []
    removed = 0
    for chunk in chunks:
        chunk_snippet = chunk["text"][:200]
        is_dup = False
        for ex_snippet, ex_mtime in existing_snippets:
            ratio = SequenceMatcher(None, chunk_snippet, ex_snippet).ratio()
            if ratio >= threshold:
                # Duplicate found — keep only if current file is newer
                if current_mtime >= ex_mtime:
                    # Current file is newer, keep this chunk (old one will be replaced on re-ingest)
                    break
                else:
                    # Older file, skip this chunk
                    is_dup = True
                    break
        if not is_dup:
            kept.append(chunk)
        else:
            removed += 1

    if removed > 0:
        print(f"[KBase] Dedup: removed {removed} near-duplicate chunks from {Path(file_path).name} (older version)")

    return kept


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


# ============================================================
# 7. Auto-Glossary: Extract terminology from documents
# ============================================================

import json as _json
from pathlib import Path as _Path

_GLOSSARY_PATH = _Path.home() / ".kbase" / "default" / "glossary.json"
_user_glossary = {}  # Loaded at runtime


def load_glossary():
    """Load user-specific glossary from disk."""
    global _user_glossary
    if _GLOSSARY_PATH.exists():
        try:
            with open(_GLOSSARY_PATH, "r", encoding="utf-8") as f:
                _user_glossary = _json.load(f)
        except Exception:
            _user_glossary = {}
    # Merge into SYNONYM_MAP for search-time use
    SYNONYM_MAP.update(_user_glossary)
    return _user_glossary


def save_glossary():
    """Save user glossary to disk."""
    _GLOSSARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_GLOSSARY_PATH, "w", encoding="utf-8") as f:
        _json.dump(_user_glossary, f, ensure_ascii=False, indent=2)


def add_glossary_term(term: str, synonyms: list[str]):
    """Manually add a term to the glossary."""
    _user_glossary[term] = synonyms
    SYNONYM_MAP[term] = synonyms
    save_glossary()


def remove_glossary_term(term: str):
    """Remove a term from the glossary."""
    _user_glossary.pop(term, None)
    SYNONYM_MAP.pop(term, None)
    save_glossary()


def get_glossary() -> dict:
    """Get the full glossary (built-in + user)."""
    return {
        "builtin": {k: v for k, v in SYNONYM_MAP.items() if k not in _user_glossary},
        "user": _user_glossary,
        "total": len(SYNONYM_MAP),
    }


def extract_glossary_from_text(text: str, llm_func=None) -> dict:
    """Use LLM to extract terminology, abbreviations, and synonyms from text.

    Returns dict of {term: [synonym1, synonym2, ...]}
    """
    if not llm_func:
        return {}

    # Take a representative sample (not the whole document)
    sample = text[:3000]

    prompt = f"""Analyze the following document excerpt and extract specialized terminology.
For each term, provide its synonyms, abbreviations, translations (Chinese↔English), and related terms.

Rules:
- Only extract domain-specific terms (not common words)
- Include abbreviations and their full forms (e.g., "BSS" → "业务支撑系统")
- Include Chinese-English pairs (e.g., "数据治理" → "data governance")
- Output ONLY valid JSON: {{"term": ["synonym1", "synonym2"]}}
- Maximum 20 terms per extraction

Document excerpt:
{sample}

JSON output:"""

    try:
        result = llm_func(prompt)
        # Parse JSON from LLM response
        # Find the JSON part (LLM might add explanation text)
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', result, re.DOTALL)
        if json_match:
            terms = _json.loads(json_match.group())
            # Validate: each value should be a list of strings
            clean = {}
            for k, v in terms.items():
                if isinstance(v, list) and all(isinstance(s, str) for s in v):
                    clean[k.strip()] = [s.strip() for s in v if s.strip()]
            return clean
    except Exception:
        pass
    return {}


def auto_build_glossary(texts: list[str], llm_func=None) -> int:
    """Extract glossary from multiple document texts and merge into user glossary.

    Call this after ingestion to auto-build the glossary.
    Returns number of new terms added.
    """
    if not llm_func or not texts:
        return 0

    new_count = 0
    for text in texts[:10]:  # Limit to 10 documents per batch
        terms = extract_glossary_from_text(text, llm_func)
        for term, synonyms in terms.items():
            if term not in SYNONYM_MAP and term not in _user_glossary:
                _user_glossary[term] = synonyms
                SYNONYM_MAP[term] = synonyms
                new_count += 1

    if new_count > 0:
        save_glossary()
    return new_count


# Load glossary on module import
load_glossary()
