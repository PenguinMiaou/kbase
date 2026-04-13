"""Web search + Research module — combine with local KB for hybrid answers."""
import json
from typing import Optional


def web_search(query: str, max_results: int = 5, region: str = "wt-wt") -> list:
    """Search the web using DuckDuckGo (free, no API key)."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, region=region, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
                "source": "web",
            }
            for r in results
        ]
    except Exception as e:
        return [{"title": "Search error", "snippet": str(e), "url": "", "source": "error"}]


def web_search_serper(query: str, api_key: str, max_results: int = 5) -> list:
    """Search using Serper.dev (Google results, needs API key)."""
    import urllib.request
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
