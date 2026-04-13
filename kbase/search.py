"""Query routing with full enhancement pipeline (14-stage adaptive):
expand → retrieve → fuse → dedup → time-decay → rerank → recursive → parent-expand
→ dir-priority → summary-boost → graph-boost → table-hint.
"""
import math
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from kbase.store import KBaseStore
from kbase.enhance import expand_query, rerank_results, segment_text, generate_hyde, generate_multi_queries


def hybrid_search(store: KBaseStore, query: str, top_k: int = 10,
                  use_rerank: bool = True, use_expand: bool = True,
                  file_type: str = None, time_decay: bool = True,
                  dedup: bool = True, recursive: bool = True,
                  llm_func=None) -> dict:
    """Adaptive progressive search — escalates techniques based on result quality.

    Level 1: keyword + semantic (fast, <1s)
    Level 2: + query expansion + rerank (if L1 top score < threshold)
    Level 3: + HyDE + multi-query (if L2 still weak, uses LLM)
    Level 4: + recursive broadening (last resort)
    """
    methods = ["semantic", "keyword"]

    # Record user query interests (lightweight, no LLM)
    try:
        store.record_query_interests(query)
    except Exception:
        pass

    # ── Level 1: Basic retrieval ──
    fetch_k = max(top_k * 5, 50)
    semantic_results = store.semantic_search(query, top_k=fetch_k, file_type=file_type)

    # Adaptive threshold: use score distribution, not fixed number
    # If top-3 scores are tightly clustered AND high → confident match, skip escalation
    # If scores are low or spread → uncertain, escalate
    l1_scores = sorted([r.get("score", 0) for r in semantic_results[:5]], reverse=True)
    l1_top = l1_scores[0] if l1_scores else 0
    l1_spread = (l1_scores[0] - l1_scores[-1]) if len(l1_scores) >= 2 else 0
    l1_confident = l1_top > 0.5 and l1_spread < 0.15  # High + clustered = good
    search_level = 1

    # ── Level 2: Query expansion + synonym (always, nearly free) ──
    expanded = expand_query(query) if use_expand else query
    if expanded != query:
        semantic_expanded = store.semantic_search(expanded, top_k=fetch_k, file_type=file_type)
        semantic_results = _dedupe_merge(semantic_results, semantic_expanded)
        methods.append("expanded")
    search_level = 2

    # ── Level 3: HyDE + Multi-Query (LLM-powered, only if L1 not confident) ──
    if llm_func and not l1_confident:
        hyde_query = generate_hyde(query, llm_func=llm_func)
        if hyde_query != query:
            hyde_results = store.semantic_search(hyde_query, top_k=fetch_k, file_type=file_type)
            semantic_results = _dedupe_merge(semantic_results, hyde_results)
            methods.append("hyde")

        multi_queries = generate_multi_queries(query, llm_func=llm_func, n=2)
        if len(multi_queries) > 1:
            for mq in multi_queries[1:]:
                mq_results = store.semantic_search(mq, top_k=fetch_k // 2, file_type=file_type)
                semantic_results = _dedupe_merge(semantic_results, mq_results)
            methods.append(f"multi-query({len(multi_queries)})")
    segmented = segment_text(query)
    keyword_results = store.keyword_search(segmented, top_k=fetch_k)

    # 2b. Also search by original unsegmented query (catches exact phrases)
    keyword_raw = store.keyword_search(query, top_k=fetch_k)
    keyword_results = _dedupe_merge(keyword_results, keyword_raw)

    # 2c. File name search (catches matches in file names that chunks may miss)
    filename_results = store.filename_search(query, top_k=top_k)
    if filename_results:
        keyword_results = _dedupe_merge(keyword_results, filename_results)
        methods.append("filename")

    # 3. RRF fusion
    fused = _rrf_merge(semantic_results, keyword_results, k=60)

    # 4. Time-aware decay (newer docs rank higher)
    if time_decay:
        fused = _apply_time_decay(fused)
        methods.append("time-decay")

    # 5. Chunk deduplication (remove near-identical chunks)
    if dedup:
        before = len(fused)
        fused = _deduplicate_chunks(fused, threshold=0.92)
        if len(fused) < before:
            methods.append(f"dedup(-{before - len(fused)})")

    # 5b. Per-file aggregation: max 3 chunks per file to ensure diversity
    fused = _aggregate_per_file(fused, max_per_file=3)
    methods.append("file-agg")

    # 6. Re-rank top results
    if use_rerank and fused:
        candidates = fused[:top_k * 3]
        fused = rerank_results(query, candidates, top_k=top_k)
        methods.append("reranked")
    else:
        fused = fused[:top_k]

    # 7. Recursive retrieval: if top results score too low, fetch more
    if recursive and fused:
        max_score = max(r.get("rerank_score", r.get("rrf_score", 0)) for r in fused[:3])
        if max_score < 0.01 and len(fused) < top_k:
            # Scores too low — try broader search
            broader = store.semantic_search(expanded or query, top_k=top_k * 5)
            extra = [r for r in broader if r["chunk_id"] not in {f["chunk_id"] for f in fused}]
            if extra:
                fused.extend(extra[:top_k - len(fused)])
                methods.append("recursive")

    # 8. Parent chunk expansion — replace child chunks with parent context where available
    fused = _expand_to_parents(store, fused)
    if any(r.get("parent_expanded") for r in fused):
        methods.append("parent-expand")

    # 9. Directory priority (archive penalty, active boost)
    fused = _apply_directory_priority(fused)
    methods.append("dir-priority")

    # 10. Click boost — files users frequently click get ranking boost (harness sensor)
    try:
        fused = _boost_with_clicks(store, fused)
        if any(r.get("click_boosted") for r in fused):
            methods.append("click-boost")
    except Exception:
        pass

    # 11. Summary boost — use file-level LLM summaries for relevance (Karpathy LLM Wiki)
    try:
        fused = _boost_with_summaries(store, query, fused)
        if any(r.get("summary_boosted") for r in fused):
            methods.append("summary-boost")
    except Exception:
        pass

    # 12. Graph coherence boost — confirmed relationships boost search ranking
    try:
        from kbase.graph import boost_search_with_graph
        fused = boost_search_with_graph(store, fused)
        if any(r.get("graph_boosted") for r in fused):
            methods.append("graph-boost")
    except Exception:
        pass  # graph module not available or no edges

    # 13. Table hint detection
    table_hint = _detect_table_query(query)
    table_results = None
    if table_hint:
        tables = store.list_tables()
        if tables:
            table_results = {
                "hint": table_hint,
                "available_tables": [
                    {"name": t["table_name"], "file": t["file_path"],
                     "sheet": t["sheet_name"], "rows": t["row_count"]}
                    for t in tables[:20]
                ],
            }

    return {
        "query": query,
        "expanded_query": expanded if expanded != query else None,
        "results": fused[:top_k],
        "result_count": len(fused[:top_k]),
        "table_hint": table_results,
        "methods_used": methods + (["table_hint"] if table_results else []),
        "search_level": search_level,
        "l1_confidence": {"top_score": round(l1_top, 3), "spread": round(l1_spread, 3), "confident": l1_confident},
    }


def semantic_only(store: KBaseStore, query: str, top_k: int = 10,
                  file_type: str = None) -> dict:
    results = store.semantic_search(query, top_k=top_k, file_type=file_type)
    return {"query": query, "results": results, "result_count": len(results), "methods_used": ["semantic"]}


def keyword_only(store: KBaseStore, query: str, top_k: int = 10) -> dict:
    segmented = segment_text(query)
    results = store.keyword_search(segmented, top_k=top_k)
    return {"query": query, "results": results, "result_count": len(results), "methods_used": ["keyword"]}


def sql_search(store: KBaseStore, sql: str) -> dict:
    result = store.sql_query(sql)
    return {"query": sql, "results": result, "methods_used": ["sql"]}


def get_table_context(store: KBaseStore) -> dict:
    tables = store.list_tables()
    schemas = [store.get_table_schema(t["table_name"]) for t in tables]
    return {"table_count": len(schemas), "tables": schemas}


# ---- Enhancement helpers ----

def _apply_time_decay(results: list, half_life_days: int = 180) -> list:
    """Apply time decay: newer documents score higher.
    Uses file modification time from metadata if available.
    """
    now = time.time()
    for r in results:
        meta = r.get("metadata", {})
        # Try to extract date from filename (YYYY-MM-DD pattern)
        fname = meta.get("file_name", "")
        import re as _re
        date_match = _re.search(r"(\d{4})[-_](\d{2})[-_](\d{2})", fname)
        if date_match:
            try:
                from datetime import datetime
                dt = datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
                age_days = (now - dt.timestamp()) / 86400
            except (ValueError, OSError):
                age_days = 365  # Default: ~1 year old
        else:
            age_days = 180  # No date info, neutral

        # Decay factor: score * 2^(-age/half_life)
        decay = math.pow(2, -age_days / half_life_days)
        score_key = "rerank_score" if "rerank_score" in r else "rrf_score" if "rrf_score" in r else "score"
        if score_key in r and isinstance(r[score_key], (int, float)):
            r[score_key] = r[score_key] * (0.5 + 0.5 * decay)  # Blend: 50% original + 50% decayed

    results.sort(key=lambda x: x.get("rerank_score", x.get("rrf_score", x.get("score", 0))), reverse=True)
    return results


def _apply_directory_priority(results: list) -> list:
    """Boost/penalize based on directory path.

    - Files in archive/history directories get penalized
    - Files in active project directories get boosted
    - Duplicate files across directories: prefer non-archive version
    """
    # Penalty patterns — universal archive/deprecated indicators
    PENALTY_PATTERNS = [
        "归档", "历史", "archive", "archived", "backup", "old",
        "废弃", "作废", "旧版", "deprecated", "trash", "deleted",
    ]
    # No hardcoded boost patterns — use recency (time_decay) instead.
    # Active directories are boosted by having newer files, not by name.

    for r in results:
        meta = r.get("metadata", {})
        fpath = meta.get("file_path", "").lower()

        # Calculate path multiplier
        multiplier = 1.0

        # Penalty for archive directories
        for pattern in PENALTY_PATTERNS:
            if pattern.lower() in fpath:
                multiplier *= 0.6  # 40% penalty
                break

        # Apply multiplier to score
        score_key = "rerank_score" if "rerank_score" in r else "rrf_score" if "rrf_score" in r else "score"
        if score_key in r and isinstance(r[score_key], (int, float)):
            r[score_key] = r[score_key] * multiplier
            r["path_priority"] = multiplier

    results.sort(key=lambda x: x.get("rerank_score", x.get("rrf_score", x.get("score", 0))), reverse=True)
    return results


def _aggregate_per_file(results: list, max_per_file: int = 3) -> list:
    """Limit chunks per file to ensure result diversity.

    Keeps top N chunks from each file, interleaved by rank to maintain
    overall score ordering while preventing one file from dominating.
    """
    if not results:
        return results

    file_counts = {}
    kept = []
    overflow = []

    for r in results:
        fpath = r.get("metadata", {}).get("file_path", "")
        count = file_counts.get(fpath, 0)
        if count < max_per_file:
            kept.append(r)
            file_counts[fpath] = count + 1
        else:
            overflow.append(r)

    # If we don't have enough results, add overflow
    if len(kept) < 10 and overflow:
        kept.extend(overflow[:10 - len(kept)])

    return kept


def _deduplicate_chunks(results: list, threshold: float = 0.85) -> list:
    """Remove near-duplicate chunks (>threshold similarity)."""
    if len(results) <= 1:
        return results

    keep = [results[0]]
    for r in results[1:]:
        text = r.get("text", "")[:200]
        is_dup = False
        for kept in keep:
            kept_text = kept.get("text", "")[:200]
            if text and kept_text:
                sim = SequenceMatcher(None, text, kept_text).quick_ratio()
                if sim > threshold:
                    is_dup = True
                    break
        if not is_dup:
            keep.append(r)
    return keep


def _dedupe_merge(list_a: list, list_b: list) -> list:
    """Merge two result lists, deduplicating by chunk_id."""
    seen = set()
    merged = []
    for item in list_a + list_b:
        cid = item.get("chunk_id")
        if cid and cid not in seen:
            seen.add(cid)
            merged.append(item)
    return merged


def _rrf_merge(list_a: list[dict], list_b: list[dict], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion to merge two ranked lists."""
    scores = {}
    items = {}
    for rank, item in enumerate(list_a):
        cid = item.get("chunk_id")
        if not cid:
            continue
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
        if cid not in items:
            items[cid] = {**item, "method": "hybrid"}
    for rank, item in enumerate(list_b):
        cid = item.get("chunk_id")
        if not cid:
            continue
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
        if cid not in items:
            items[cid] = {**item, "method": "hybrid"}
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return [{**items[cid], "rrf_score": scores[cid]} for cid in sorted_ids]


def _expand_to_parents(store: KBaseStore, results: list) -> list:
    """Replace child chunks with their parent chunk text for richer LLM context.

    When a child chunk matches, find its parent (larger chunk containing more context)
    and use the parent text instead. This gives the LLM more surrounding context.
    """
    if not results:
        return results

    for r in results:
        meta = r.get("metadata", {})
        if meta.get("is_parent"):
            continue  # Already a parent

        file_path = meta.get("file_path", "")
        if not file_path:
            continue

        # Look for a parent chunk from same file
        try:
            # Search for parent chunks from the same file
            parent_results = store.keyword_search(
                f'"{Path(file_path).name}"',
                top_k=5,
            )
            for pr in parent_results:
                pr_meta = pr.get("metadata", {})
                if (pr_meta.get("is_parent") and
                    pr_meta.get("file_path") == file_path and
                    len(pr.get("text", "")) > len(r.get("text", ""))):
                    # Found parent with more context — use its text
                    r["text_original"] = r["text"]  # Keep original for highlighting
                    r["text"] = pr["text"]
                    r["parent_expanded"] = True
                    break
        except Exception:
            pass

    return results


def _boost_with_clicks(store: KBaseStore, results: list) -> list:
    """Boost search results using historical click data (harness sensor feedback).

    Files that users frequently click in search results get a ranking boost.
    """
    if not results:
        return results

    file_ids = list(set(
        r.get("metadata", {}).get("file_id", "") for r in results if r.get("metadata", {}).get("file_id")
    ))
    if not file_ids:
        return results

    click_scores = store.get_click_scores(file_ids)
    if not click_scores:
        return results

    for r in results:
        fid = r.get("metadata", {}).get("file_id", "")
        if fid in click_scores:
            boost = 0.02 * click_scores[fid]  # Up to 2% boost for most-clicked
            score_key = "rerank_score" if "rerank_score" in r else "rrf_score"
            if score_key in r:
                r[score_key] = r[score_key] + boost
            r["click_boosted"] = True

    score_key = "rerank_score" if any("rerank_score" in r for r in results) else "rrf_score"
    results.sort(key=lambda x: x.get(score_key, 0), reverse=True)
    return results


def _boost_with_summaries(store: KBaseStore, query: str, results: list) -> list:
    """Boost search results using file-level LLM summaries.

    If a file has a summary that matches the query keywords,
    all chunks from that file get a relevance boost.
    """
    if not results:
        return results

    query_lower = query.lower()
    query_terms = set(query_lower.split())

    # Collect unique file_ids from results
    file_ids = set()
    for r in results:
        fid = r.get("metadata", {}).get("file_id", "")
        if fid:
            file_ids.add(fid)

    if not file_ids:
        return results

    # Fetch summaries for these files
    summaries = {}
    try:
        c = store.conn.cursor()
        placeholders = ",".join("?" for _ in file_ids)
        c.execute(f"SELECT file_id, summary FROM files WHERE file_id IN ({placeholders})", list(file_ids))
        for row in c.fetchall():
            if row["summary"]:
                summaries[row["file_id"]] = row["summary"].lower()
    except Exception:
        return results

    if not summaries:
        return results

    # Compute match score: how many query terms appear in the summary
    for r in results:
        fid = r.get("metadata", {}).get("file_id", "")
        summary = summaries.get(fid, "")
        if summary:
            hits = sum(1 for term in query_terms if term in summary)
            if hits > 0:
                ratio = hits / max(len(query_terms), 1)
                boost = 0.03 * ratio  # Up to 3% boost
                score_key = "rerank_score" if "rerank_score" in r else "rrf_score"
                if score_key in r:
                    r[score_key] = r[score_key] + boost
                r["summary_boosted"] = True

    # Re-sort by score
    score_key = "rerank_score" if any("rerank_score" in r for r in results) else "rrf_score"
    results.sort(key=lambda x: x.get(score_key, 0), reverse=True)
    return results


def _detect_table_query(query: str) -> Optional[str]:
    table_patterns = [
        r"多少|数量|总数|统计|占比|百分比|排名|top\s*\d",
        r"平均|最大|最小|合计|求和|增长率",
        r"对比|比较|差异|环比|同比",
        r"哪些.*数据|列出.*指标|有哪些.*字段",
    ]
    for pattern in table_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return pattern
    return None
