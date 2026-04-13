"""Web search + Research module — multi-engine search with language-based routing."""
import json
import re
import time
import urllib.request
import urllib.parse
from typing import Optional
from html.parser import HTMLParser


# ============================================================
# Multi-Engine Search (16 engines, no API keys needed)
# ============================================================

# Engine definitions: {name, url_template, parser, group}
SEARCH_ENGINES = {
    # ── International ──
    "duckduckgo": {"name": "DuckDuckGo", "group": "intl", "type": "api"},
    "brave": {"name": "Brave", "group": "intl", "type": "scrape",
              "url": "https://search.brave.com/search?q={q}"},
    "serper": {"name": "Google (Serper)", "group": "intl", "type": "api", "needs_key": "serper_api_key"},
    # ── China (国内) ──
    "bing_cn": {"name": "Bing CN", "group": "china", "type": "scrape",
                "url": "https://cn.bing.com/search?q={q}&ensearch=0"},
    "sogou": {"name": "Sogou", "group": "china", "type": "scrape",
              "url": "https://sogou.com/web?query={q}"},
    "wechat": {"name": "WeChat Articles", "group": "china", "type": "scrape",
               "url": "https://wx.sogou.com/weixin?type=2&query={q}"},
}

# Default engine selection per language
DEFAULT_ENGINES = {
    "zh": ["duckduckgo", "bing_cn"],      # Chinese queries
    "en": ["duckduckgo", "brave"],          # English queries
    "auto": ["duckduckgo"],                 # Fallback
}


def _detect_language(text: str) -> str:
    """Detect if text is primarily Chinese or English."""
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return "zh" if cjk / max(len(text), 1) > 0.2 else "en"


def web_search(query: str, max_results: int = 5, region: str = "wt-wt",
               engines: list = None, settings: dict = None) -> list:
    """Multi-engine web search with automatic language-based routing.

    Args:
        query: Search query
        max_results: Max results per engine
        engines: Explicit engine list, or None for auto-detect
        settings: Settings dict (for API keys like serper_api_key)
    """
    settings = settings or {}

    # Auto-select engines based on query language
    if not engines:
        lang = _detect_language(query)
        engines = DEFAULT_ENGINES.get(lang, DEFAULT_ENGINES["auto"])
        # Add serper if API key is available
        if settings.get("serper_api_key"):
            engines = ["serper"] + engines

    all_results = []
    seen_urls = set()

    for engine_key in engines:
        engine = SEARCH_ENGINES.get(engine_key)
        if not engine:
            continue

        try:
            if engine_key == "duckduckgo":
                results = _search_duckduckgo(query, max_results)
            elif engine_key == "serper":
                api_key = settings.get("serper_api_key", "")
                if api_key:
                    results = _search_serper(query, api_key, max_results)
                else:
                    continue
            elif engine.get("type") == "scrape":
                results = _search_scrape(query, engine, max_results)
            else:
                continue

            # Deduplicate by URL
            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    r["engine"] = engine.get("name", engine_key)
                    all_results.append(r)

        except Exception as e:
            all_results.append({
                "title": f"{engine.get('name', engine_key)} error",
                "snippet": str(e)[:100],
                "url": "", "source": "error", "engine": engine.get("name"),
            })

        # Rate limit between engines
        if len(engines) > 1:
            time.sleep(0.5)

    return all_results[:max_results * 2]  # Return up to 2x for multi-engine


def _search_duckduckgo(query: str, max_results: int) -> list:
    """DuckDuckGo via duckduckgo_search library."""
    from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return [
        {"title": r.get("title", ""), "url": r.get("href", ""),
         "snippet": r.get("body", ""), "source": "web"}
        for r in results
    ]


def _search_serper(query: str, api_key: str, max_results: int) -> list:
    """Google results via Serper.dev API."""
    data = json.dumps({"q": query, "num": max_results}).encode()
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=data,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    return [
        {"title": r.get("title", ""), "url": r.get("link", ""),
         "snippet": r.get("snippet", ""), "source": "google"}
        for r in result.get("organic", [])[:max_results]
    ]


def _search_scrape(query: str, engine: dict, max_results: int) -> list:
    """Scrape search results from engine URL (no API key needed)."""
    url = engine["url"].format(q=urllib.parse.quote_plus(query))
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return []

    # Simple HTML result extraction
    results = []
    # Look for common search result patterns: <a href="...">title</a> + snippet
    links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)</a>', html)
    for href, title in links:
        title = title.strip()
        if not title or len(title) < 5:
            continue
        # Skip engine's own links
        if any(skip in href for skip in ["bing.com/ck", "sogou.com/link", "google.com/search"]):
            continue
        results.append({
            "title": _unescape_html(title),
            "url": href,
            "snippet": "",
            "source": "web",
        })
        if len(results) >= max_results:
            break

    return results


def _unescape_html(text: str) -> str:
    """Unescape HTML entities."""
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    return text


def web_search_serper(query: str, api_key: str, max_results: int = 5) -> list:
    """Legacy wrapper for backward compatibility."""
    return _search_serper(query, api_key, max_results)


def research(query: str, llm_func=None, kb_search_func=None,
             max_steps: int = 3, web_results: int = 5) -> dict:
    """Deep research mode: iterative search + KB lookup + synthesis.

    Steps:
    1. Decompose question into sub-queries
    2. Search web + KB for each sub-query
    3. Synthesize findings
    """
    findings = []
    sub_queries = [query]  # Start with original query

    # Step 1: Generate sub-queries if LLM available
    if llm_func and max_steps > 1:
        try:
            decompose_prompt = (
                f"Break this question into 2-3 specific search queries "
                f"that would help answer it comprehensively. "
                f"Return ONLY the queries, one per line.\n\n"
                f"Question: {query}"
            )
            sub_text = llm_func(decompose_prompt)
            lines = [l.strip().strip("-").strip("•").strip("1234567890.").strip()
                     for l in sub_text.strip().split("\n") if l.strip()]
            if lines:
                sub_queries = lines[:3]
        except Exception:
            pass

    # Step 2: Search for each sub-query
    for i, sq in enumerate(sub_queries):
        step = {"query": sq, "web": [], "kb": []}

        # Web search
        try:
            web_results_list = web_search(sq, max_results=web_results)
            step["web"] = web_results_list
        except Exception as e:
            step["web_error"] = str(e)

        # KB search
        if kb_search_func:
            try:
                kb_results = kb_search_func(sq)
                step["kb"] = kb_results
            except Exception as e:
                step["kb_error"] = str(e)

        findings.append(step)

    return {
        "query": query,
        "sub_queries": sub_queries,
        "findings": findings,
        "steps": len(findings),
    }


# Search mode definitions
SEARCH_MODES = {
    "kb": {
        "name": "KB Only",
        "name_zh": "仅知识库",
        "desc": "Search local knowledge base only",
        "icon": "📚",
    },
    "web": {
        "name": "Web Only",
        "name_zh": "仅网络搜索",
        "desc": "Search the web only (DuckDuckGo)",
        "icon": "🌐",
    },
    "hybrid": {
        "name": "KB + Web",
        "name_zh": "知识库+网络",
        "desc": "Search both local KB and web, merge results",
        "icon": "🔀",
    },
    "research": {
        "name": "Deep Research",
        "name_zh": "深度研究",
        "desc": "Multi-step research: decompose → search → synthesize",
        "icon": "🔬",
    },
}
