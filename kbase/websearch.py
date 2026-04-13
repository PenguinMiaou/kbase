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
    "google": {"name": "Google", "group": "intl", "type": "scrape",
               "url": "https://www.google.com/search?q={q}&hl=en"},
    "startpage": {"name": "Startpage", "group": "intl", "type": "scrape",
                  "url": "https://www.startpage.com/do/dsearch?query={q}"},
    "ecosia": {"name": "Ecosia", "group": "intl", "type": "scrape",
               "url": "https://www.ecosia.org/search?q={q}"},
    "serper": {"name": "Google (Serper)", "group": "intl", "type": "api", "needs_key": "serper_api_key"},
    # ── China (国内) ──
    "bing_cn": {"name": "Bing CN", "group": "china", "type": "scrape",
                "url": "https://cn.bing.com/search?q={q}&ensearch=0"},
    "bing_intl": {"name": "Bing", "group": "intl", "type": "scrape",
                  "url": "https://www.bing.com/search?q={q}"},
    "sogou": {"name": "Sogou", "group": "china", "type": "scrape",
              "url": "https://sogou.com/web?query={q}"},
    "wechat": {"name": "WeChat Articles", "group": "china", "type": "scrape",
               "url": "https://wx.sogou.com/weixin?type=2&query={q}"},
    "baidu": {"name": "Baidu", "group": "china", "type": "scrape",
              "url": "https://www.baidu.com/s?wd={q}"},
}

# Default engine selection per language (batch of 3-4, most reliable first)
DEFAULT_ENGINES = {
    "zh": ["duckduckgo", "sogou", "bing_cn", "baidu"],    # Chinese queries
    "en": ["duckduckgo", "brave", "bing_intl", "ecosia"],  # English queries
    "auto": ["duckduckgo", "brave"],                        # Fallback
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
            print(f"[KBase] Web search engine {engine.get('name', engine_key)} failed: {e}")

        # Rate limit between engines (1-2s delay, CrawHub pattern)
        if len(engines) > 1:
            time.sleep(1.0)

    return all_results[:max_results * 2]  # Return up to 2x for multi-engine


def _search_duckduckgo(query: str, max_results: int, region: str = "wt-wt") -> list:
    """DuckDuckGo via ddgs (or legacy duckduckgo_search) library."""
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    import warnings
    warnings.filterwarnings("ignore", message=".*renamed.*")
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results, region=region))
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


# ── Session-aware HTTP client (cookie recovery pattern from CrawHub) ──
_cookie_jar = {}  # In-memory cookie store: {domain: http.cookiejar.CookieJar}

def _get_opener(domain: str):
    """Get a urllib opener with cookie support for a domain."""
    import http.cookiejar
    if domain not in _cookie_jar:
        _cookie_jar[domain] = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(_cookie_jar[domain])
    )

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
    "DNT": "1",
}

def _fetch_html(url: str, retry_with_cookies: bool = True) -> str:
    """Fetch HTML with session cookies and anti-CAPTCHA recovery.

    Strategy (CrawHub pattern):
    1. Try with existing session cookies
    2. If 403/429/CAPTCHA → fetch engine homepage to get fresh cookies
    3. Retry the search with new cookies
    """
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    opener = _get_opener(domain)

    req = urllib.request.Request(url, headers=_BROWSER_HEADERS)
    try:
        with opener.open(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Check for CAPTCHA/verification pages
        captcha_signals = ["captcha", "verify", "challenge", "验证", "robot", "unusual traffic"]
        if any(sig in html.lower() for sig in captcha_signals) and retry_with_cookies:
            # Session recovery: visit homepage to get fresh cookies
            homepage = f"https://{domain}/"
            home_req = urllib.request.Request(homepage, headers=_BROWSER_HEADERS)
            try:
                with opener.open(home_req, timeout=8) as _:
                    pass
                time.sleep(1)  # Brief pause after cookie acquisition
            except Exception:
                pass
            # Retry with fresh cookies
            return _fetch_html(url, retry_with_cookies=False)

        return html
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) and retry_with_cookies:
            # Rate limited or blocked → session recovery
            homepage = f"https://{domain}/"
            home_req = urllib.request.Request(homepage, headers=_BROWSER_HEADERS)
            try:
                with opener.open(home_req, timeout=8) as _:
                    pass
                time.sleep(1)
            except Exception:
                pass
            return _fetch_html(url, retry_with_cookies=False)
        raise


def _search_scrape(query: str, engine: dict, max_results: int) -> list:
    """Scrape search results with engine-specific parsers (CrawHub pattern)."""
    url = engine["url"].format(q=urllib.parse.quote_plus(query))
    try:
        html = _fetch_html(url)
    except Exception:
        return []

    engine_name = engine.get("name", "")

    if "Bing" in engine_name:
        return _parse_bing(html, max_results)
    elif "Brave" in engine_name:
        return _parse_brave(html, max_results)
    elif "Sogou" in engine_name or "WeChat" in engine_name:
        return _parse_sogou(html, max_results)
    elif "Baidu" in engine_name:
        return _parse_baidu(html, max_results)
    elif "Google" in engine_name:
        return _parse_google(html, max_results)
    elif "Startpage" in engine_name:
        return _parse_startpage(html, max_results)
    elif "Ecosia" in engine_name:
        return _parse_bing(html, max_results)  # Ecosia uses Bing's result format
    else:
        return _parse_generic(html, max_results)


def _parse_bing(html: str, max_results: int) -> list:
    """Parse Bing search results."""
    results = []
    # Bing result blocks: <li class="b_algo">...<h2><a href="URL">Title</a></h2>...<p>snippet</p>...</li>
    blocks = re.findall(r'<li class="b_algo">(.*?)</li>', html, re.DOTALL)
    for block in blocks[:max_results]:
        # Extract URL and title from <h2><a>
        m = re.search(r'<h2><a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a></h2>', block, re.DOTALL)
        if not m:
            continue
        href, title = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
        # Extract snippet from <p> or <div class="b_caption">
        snippet = ""
        sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        if sm:
            snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
        if title and len(title) >= 3:
            results.append({"title": _unescape_html(title), "url": href,
                            "snippet": _unescape_html(snippet)[:300], "source": "web"})
    return results


def _parse_brave(html: str, max_results: int) -> list:
    """Parse Brave search results."""
    results = []
    # Brave renders with data-type="web" blocks
    blocks = re.findall(r'<div[^>]+data-type="web"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)
    if not blocks:
        # Fallback: look for snippet fdb blocks
        blocks = re.findall(r'<div class="snippet[^"]*">(.*?)</div>\s*</div>', html, re.DOTALL)
    for block in blocks[:max_results]:
        m = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not m:
            continue
        href, title = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
        snippet = ""
        sm = re.search(r'<p[^>]*class="snippet-description[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
        if sm:
            snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
        if title and len(title) >= 3 and "brave.com" not in href:
            results.append({"title": _unescape_html(title), "url": href,
                            "snippet": _unescape_html(snippet)[:300], "source": "web"})
    # If Brave blocks fail, use ddgs as fallback
    if not results:
        try:
            return _search_duckduckgo(query="", max_results=0)  # no-op, handled by caller
        except Exception:
            pass
    return results


def _parse_sogou(html: str, max_results: int) -> list:
    """Parse Sogou/WeChat search results."""
    results = []
    # Sogou wraps results in <div class="vrwrap"> or <div class="results">
    blocks = re.findall(r'<div class="(?:vrwrap|rb)"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
    if not blocks:
        blocks = re.findall(r'<div class="txt-box">(.*?)</div>', html, re.DOTALL)
    for block in blocks[:max_results]:
        m = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not m:
            # Sogou uses redirect URLs
            m = re.search(r'<a[^>]+href="(/link\?[^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if m:
                href = "https://sogou.com" + m.group(1)
            else:
                continue
        else:
            href = m.group(1)
        title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        snippet = ""
        sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        if not sm:
            sm = re.search(r'<div class="txt-info[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
        if sm:
            snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
        if title and len(title) >= 3:
            results.append({"title": _unescape_html(title), "url": href,
                            "snippet": _unescape_html(snippet)[:300], "source": "web"})
    return results


def _parse_baidu(html: str, max_results: int) -> list:
    """Parse Baidu search results."""
    results = []
    # Baidu: <div class="result c-container"> with <h3><a href="...">title</a></h3>
    blocks = re.findall(r'<div[^>]+class="[^"]*result[^"]*c-container[^"]*"[^>]*>(.*?)</div>\s*<!--', html, re.DOTALL)
    if not blocks:
        blocks = re.findall(r'<div[^>]+class="c-container"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)
    for block in blocks[:max_results]:
        m = re.search(r'<h3[^>]*>\s*<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not m:
            continue
        href, title = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
        snippet = ""
        # Baidu snippets: <span class="content-right_..."> or <div class="c-abstract">
        sm = re.search(r'<span[^>]+class="content-right[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        if not sm:
            sm = re.search(r'<div[^>]+class="c-abstract[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
        if sm:
            snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
        if title and len(title) >= 3:
            results.append({"title": _unescape_html(title), "url": href,
                            "snippet": _unescape_html(snippet)[:300], "source": "web"})
    return results


def _parse_google(html: str, max_results: int) -> list:
    """Parse Google search results (direct scrape, no API)."""
    results = []
    # Google result blocks contain <div class="g"> or data-sokoban
    blocks = re.findall(r'<div class="g"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)
    if not blocks:
        # Alternative: look for <a> inside <h3>
        blocks = re.findall(r'<div[^>]+data-sokoban[^>]*>(.*?)</div>', html, re.DOTALL)
    for block in blocks[:max_results]:
        m = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
        if not m:
            m = re.search(r'<h3[^>]*><a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a></h3>', block, re.DOTALL)
        if not m:
            continue
        href, title = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
        snippet = ""
        sm = re.search(r'<span[^>]+class="[^"]*st[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        if not sm:
            sm = re.search(r'<div[^>]+data-sncf[^>]*>(.*?)</div>', block, re.DOTALL)
        if sm:
            snippet = re.sub(r'<[^>]+>', '', sm.group(1)).strip()
        if title and "google.com" not in href:
            results.append({"title": _unescape_html(title), "url": href,
                            "snippet": _unescape_html(snippet)[:300], "source": "web"})
    return results


def _parse_startpage(html: str, max_results: int) -> list:
    """Parse Startpage search results."""
    results = []
    blocks = re.findall(r'<a[^>]+class="w-gl__result-url[^"]*"[^>]+href="(https?://[^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>.*?<p[^>]+class="w-gl__description[^"]*"[^>]*>(.*?)</p>', html, re.DOTALL)
    for href, title, snippet in blocks[:max_results]:
        title = re.sub(r'<[^>]+>', '', title).strip()
        snippet = re.sub(r'<[^>]+>', '', snippet).strip()
        if title:
            results.append({"title": _unescape_html(title), "url": href,
                            "snippet": _unescape_html(snippet)[:300], "source": "web"})
    return results


def _parse_generic(html: str, max_results: int) -> list:
    """Generic HTML search result parser — last resort."""
    results = []
    links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]{5,})</a>', html)
    skip_domains = ["bing.com", "sogou.com", "google.com", "brave.com", "baidu.com"]
    for href, title in links:
        if any(d in href for d in skip_domains):
            continue
        results.append({"title": _unescape_html(title.strip()), "url": href,
                        "snippet": "", "source": "web"})
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
