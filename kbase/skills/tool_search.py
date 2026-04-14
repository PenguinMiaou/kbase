"""Search tools — KB search + web search, wrapping existing KBase modules."""
import json
from .tools import SkillTool, register_tool


class KBSearchTool(SkillTool):
    name = "kb_search"
    description = "Search the KBase knowledge base. Returns ranked results with file names, text excerpts, and scores."
    is_read_only = True
    max_result_chars = 6000
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "description": "Max results (default 5)"},
        },
        "required": ["query"],
    }

    _store = None

    def call(self, params: dict) -> str:
        if not self._store:
            from kbase.store import KBaseStore
            self._store = KBaseStore()

        from kbase.search import hybrid_search
        results = hybrid_search(
            self._store, params["query"],
            top_k=params.get("top_k", 5),
        )

        items = []
        for r in results.get("results", [])[:params.get("top_k", 5)]:
            meta = r.get("metadata", {})
            items.append({
                "file": meta.get("file_name", "?"),
                "score": round(r.get("rrf_score", 0), 4),
                "text": r.get("text", "")[:500],
            })
        return json.dumps({"query": params["query"], "count": len(items), "results": items}, ensure_ascii=False)


class WebSearchTool(SkillTool):
    name = "web_search"
    description = "Search the internet. Returns titles, URLs, and snippets from multiple search engines."
    is_read_only = True
    max_result_chars = 4000
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results (default 5)"},
        },
        "required": ["query"],
    }

    def call(self, params: dict) -> str:
        from kbase.websearch import web_search
        results = web_search(params["query"], max_results=params.get("max_results", 5))
        items = []
        for r in results[:params.get("max_results", 5)]:
            items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("body", r.get("snippet", ""))[:300],
            })
        return json.dumps({"query": params["query"], "count": len(items), "results": items}, ensure_ascii=False)


register_tool(KBSearchTool())
register_tool(WebSearchTool())
