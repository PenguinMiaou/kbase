"""Chat with LLM using knowledge base as context + conversation memory. Copyright@PenguinMiaou"""
import json
import os
import time
from typing import Optional

from kbase.config import load_settings
from kbase.store import KBaseStore
from kbase.search import hybrid_search


LLM_PROVIDERS = {
    # --- International ---
    "claude-sonnet": {
        "name": "Claude Sonnet 4", "type": "anthropic", "model": "claude-sonnet-4-20250514",
        "desc": "Anthropic - 快速高质量", "group": "global",
        "logo": "/static/logos/claude.svg",
        "signup_url": "https://console.anthropic.com/",
    },
    "claude-opus": {
        "name": "Claude Opus 4", "type": "anthropic", "model": "claude-opus-4-20250514",
        "desc": "Anthropic - 最强推理", "group": "global",
        "logo": "/static/logos/claude.svg",
        "signup_url": "https://console.anthropic.com/",
    },
    "gpt-4o": {
        "name": "GPT-4o", "type": "openai", "model": "gpt-4o",
        "desc": "OpenAI GPT-4o", "group": "global",
        "logo": "/static/logos/openai.svg",
        "signup_url": "https://platform.openai.com/api-keys",
    },
    "gpt-4o-mini": {
        "name": "GPT-4o Mini", "type": "openai", "model": "gpt-4o-mini",
        "desc": "OpenAI - 便宜快速", "group": "global",
        "logo": "/static/logos/openai.svg",
        "signup_url": "https://platform.openai.com/api-keys",
    },
    "gemini-2.5-flash": {
        "name": "Gemini 2.5 Flash", "type": "openai-compatible",
        "model": "gemini-2.5-flash-preview-05-20",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY", "desc": "Google - 快速便宜", "group": "global",
        "logo": "/static/logos/gemini.webp",
        "signup_url": "https://aistudio.google.com/apikey",
    },
    "gemini-2.5-pro": {
        "name": "Gemini 2.5 Pro", "type": "openai-compatible",
        "model": "gemini-2.5-pro-preview-06-05",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY", "desc": "Google - 最强推理", "group": "global",
        "logo": "/static/logos/gemini.webp",
        "signup_url": "https://aistudio.google.com/apikey",
    },
    # --- China ---
    "deepseek-chat": {
        "name": "DeepSeek Chat", "type": "openai-compatible", "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1", "key_env": "DEEPSEEK_API_KEY",
        "desc": "性价比极高", "group": "china",
        "logo": "/static/logos/deepseek-sign-logo.png",
        "signup_url": "https://platform.deepseek.com/api_keys",
    },
    "qwen-plus": {
        "name": "通义千问 Plus", "type": "openai-compatible", "model": "qwen-plus",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "key_env": "DASHSCOPE_API_KEY", "desc": "阿里 - 中文能力强", "group": "china",
        "logo": "/static/logos/Qwen_logo.svg.png",
        "signup_url": "https://dashscope.console.aliyun.com/apiKey",
    },
    "qwen-max": {
        "name": "通义千问 Max", "type": "openai-compatible", "model": "qwen-max",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "key_env": "DASHSCOPE_API_KEY", "desc": "阿里旗舰 - 最强中文推理", "group": "china",
        "logo": "/static/logos/Qwen_logo.svg.png",
        "signup_url": "https://dashscope.console.aliyun.com/apiKey",
    },
    "glm-4-plus": {
        "name": "智谱 GLM-4", "type": "openai-compatible", "model": "glm-4-plus",
        "base_url": "https://open.bigmodel.cn/api/paas/v4", "key_env": "ZHIPU_API_KEY",
        "desc": "智谱清言 - 综合优秀", "group": "china",
        "logo": "/static/logos/zhipu-color.png",
        "signup_url": "https://open.bigmodel.cn/usercenter/apikeys",
    },
    "moonshot-v1": {
        "name": "Kimi (月之暗面)", "type": "openai-compatible", "model": "moonshot-v1-128k",
        "base_url": "https://api.moonshot.cn/v1", "key_env": "MOONSHOT_API_KEY",
        "desc": "超长上下文 128K", "group": "china",
        "logo": "/static/logos/Kimi-logo-2025.png",
        "signup_url": "https://platform.moonshot.cn/console/api-keys",
    },
    "doubao-pro": {
        "name": "豆包 (字节)", "type": "openai-compatible", "model": "doubao-pro-256k",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3", "key_env": "ARK_API_KEY",
        "desc": "需在火山引擎创建 Endpoint, model 填 Endpoint ID", "group": "china",
        "logo": "/static/logos/doubao.webp",
        "signup_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
    },
    "ernie-4": {
        "name": "文心一言 4.0", "type": "openai-compatible", "model": "ernie-4.0-8k",
        "base_url": "https://qianfan.baidubce.com/v2", "key_env": "ERNIE_API_KEY",
        "desc": "百度千帆平台 (OpenAI兼容)", "group": "china",
        "logo": "/static/logos/wenxin-color.png",
        "signup_url": "https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application",
    },
    "hunyuan": {
        "name": "混元 (腾讯)", "type": "openai-compatible", "model": "hunyuan-pro",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1", "key_env": "HUNYUAN_API_KEY",
        "desc": "腾讯混元大模型", "group": "china",
        "logo": "/static/logos/hunyuan-color.png",
        "signup_url": "https://cloud.tencent.com/product/hunyuan",
    },
    "minimax": {
        "name": "MiniMax", "type": "openai-compatible", "model": "abab6.5s-chat",
        "base_url": "https://api.minimax.chat/v1", "key_env": "MINIMAX_API_KEY",
        "desc": "擅长长文本理解", "group": "china",
        "logo": "/static/logos/minimax-color.png",
        "signup_url": "https://platform.minimaxi.com/user-center/basic-information/interface-key",
    },
    # --- Local ---
    "ollama": {
        "name": "Ollama (本地)", "type": "ollama", "model": "qwen2.5:7b",
        "desc": "免费离线，需安装 Ollama", "group": "local",
        "logo": "/static/logos/Ollama-logo.svg.png",
        "signup_url": "https://ollama.com/download",
    },
    "claude-cli": {
        "name": "Claude CLI", "type": "cli", "cmd": "claude -p",
        "desc": "本地 OAuth 登录，无需 Key", "group": "local",
        "logo": "/static/logos/claude.svg",
        "signup_url": "",
    },
    "llm-cli": {
        "name": "LLM CLI", "type": "cli", "cmd": "llm",
        "desc": "Simon Willison llm 工具", "group": "local",
        "logo": "/static/logos/llm.png",
        "signup_url": "https://llm.datasette.io/",
    },
    "qwen-cli": {
        "name": "Qwen CLI", "type": "cli", "cmd": "qwen -p",
        "desc": "通义千问 CLI，本地登录无需 Key", "group": "local",
        "logo": "/static/logos/qwen-new.png",
        "signup_url": "https://github.com/QwenLM/qwen-code",
    },
    "custom": {
        "name": "Custom (自定义)", "type": "openai-compatible",
        "model": "", "base_url": "", "key_env": "CUSTOM_API_KEY",
        "desc": "任何 OpenAI 兼容 API", "group": "local",
        "logo": "/static/logos/llm.png",
        "signup_url": "",
    },
    "dify": {
        "name": "Dify", "type": "dify",
        "model": "dify", "base_url": "", "key_env": "CUSTOM_API_KEY",
        "desc": "Dify AI Platform", "group": "local",
        "logo": "/static/logos/llm.png",
        "signup_url": "",
    },
}

# Buddy personality presets
BUDDY_PRESETS = {
    "professional": {
        "name": "Professional",
        "name_zh": "专业顾问",
        "avatar": "/static/logos/buddy-pro.svg",
        "mbti": "ISTJ",
        "desc": "Precise, structured, formal",
        "desc_zh": "严谨专业，条理清晰，适合正式工作场景",
        "personality": "Methodical, detail-oriented, reliable",
        "system_extra": (
            "You are a professional knowledge assistant. Be precise, structured, and formal. "
            "Use numbered lists and clear headings. Always cite sources with file names. "
            "Avoid casual language. Prioritize accuracy over friendliness."
        ),
    },
    "buddy": {
        "name": "Buddy",
        "name_zh": "好同事",
        "avatar": "/static/logos/buddy-friend.svg",
        "mbti": "ENFP",
        "desc": "Warm, helpful, like a knowledgeable friend",
        "desc_zh": "友好随和，像个靠谱的同事，有啥说啥",
        "personality": "Enthusiastic, empathetic, creative",
        "system_extra": (
            "You are KBase Buddy — a friendly, knowledgeable coworker who happens to have perfect memory of all the files. "
            "Be warm but concise. Use casual tone (but still professional). "
            "Occasionally add a brief encouraging remark or a light observation. "
            "If you find something interesting in the data, mention it like 'btw, I noticed...' "
            "When citing files, be specific about where the info comes from. "
            "If the user seems stressed, be supportive. If the question is fun, match the energy. "
            "You speak the user's language (Chinese if they write Chinese). "
            "Sign off important answers with a brief one-liner like a friend would."
        ),
    },
    "analyst": {
        "name": "Analyst",
        "name_zh": "数据分析师",
        "avatar": "/static/logos/buddy-analyst.webp",
        "mbti": "INTJ",
        "desc": "Data-driven, finds patterns and insights",
        "desc_zh": "数据驱动，擅长从数据中挖掘洞察和趋势",
        "personality": "Analytical, strategic, insightful",
        "system_extra": (
            "You are a sharp data analyst assistant. Focus on numbers, trends, comparisons. "
            "When answering, structure with: Key Finding → Supporting Data → Implication. "
            "Proactively point out anomalies or interesting patterns in the data."
        ),
    },
    "tutor": {
        "name": "Tutor",
        "name_zh": "导师",
        "avatar": "/static/logos/buddy-tutor.png",
        "mbti": "INFJ",
        "desc": "Patient teacher, explains complex topics simply",
        "desc_zh": "耐心的老师，善于把复杂概念讲清楚",
        "personality": "Patient, insightful, nurturing",
        "system_extra": (
            "You are a patient tutor. Explain concepts step by step. "
            "Use analogies the user would understand. Ask clarifying questions when needed. "
            "Break complex topics into digestible pieces."
        ),
    },
    "creative": {
        "name": "Creative",
        "name_zh": "创意达人",
        "avatar": "/static/logos/buddy-creative.svg",
        "mbti": "ENTP",
        "desc": "Brainstorming, out-of-the-box thinking",
        "desc_zh": "天马行空，擅长头脑风暴和创意发想",
        "personality": "Inventive, witty, provocative",
        "system_extra": (
            "You are a creative brainstorming partner. Think outside the box. "
            "Generate unconventional ideas and connections. Challenge assumptions. "
            "Use 'What if...' and 'Have you considered...' to inspire new directions."
        ),
    },
    "executive": {
        "name": "Executive",
        "name_zh": "高管助理",
        "avatar": "/static/logos/buddy-exec.webp",
        "mbti": "ENTJ",
        "desc": "Strategic, concise, decision-focused",
        "desc_zh": "战略视角，简洁高效，聚焦决策",
        "personality": "Decisive, strategic, results-driven",
        "system_extra": (
            "You are an executive assistant. Be extremely concise — bullet points preferred. "
            "Lead with the conclusion, then supporting evidence. "
            "Frame answers in terms of impact, risk, and recommended actions. "
            "If data is insufficient for a decision, say so clearly."
        ),
    },
    "custom": {
        "name": "Custom",
        "name_zh": "自定义",
        "avatar": "/static/logos/buddy-custom.webp",
        "mbti": "",
        "desc": "Define your own AI personality",
        "desc_zh": "自定义 AI 人格和行为",
        "personality": "",
        "system_extra": "",  # Will be filled from settings.custom_buddy_prompt
    },
}

SYSTEM_PROMPTS = {
    "kb": """You are a knowledgeable assistant with access to the user's local knowledge base.
Answer based on the retrieved context below.

{buddy_extra}

Rules:
- Answer in the same language as the user's question. If the user writes in Chinese, you MUST reply in Chinese. Never switch to English unless the user uses English.
- Cite source files using [filename] format.
- Files ending in .mbox are email archives — treat their content as emails.
- If context is insufficient, say so honestly.
- Be concise and direct. Include specific numbers when available.

Retrieved Context:
{context}
""",
    "web": """You are a knowledgeable assistant with access to web search results.
Answer based on the web search results below.

{buddy_extra}

Rules:
- Answer in the same language as the user's question. If the user writes in Chinese, you MUST reply in Chinese. Never switch to English unless the user uses English.
- Cite sources using [Source Title](URL) format when available.
- If the search results are insufficient, say so honestly and provide what you know.
- Be concise and direct. Include specific numbers when available.

Web Search Results:
{context}
""",
    "hybrid": """You are a knowledgeable assistant with access to the user's local knowledge base and web search.
Answer based on the retrieved context below, combining local and web sources.

{buddy_extra}

Rules:
- Answer in the same language as the user's question. If the user writes in Chinese, you MUST reply in Chinese. Never switch to English unless the user uses English.
- Cite local sources using [filename] format and web sources using [Source Title](URL) format.
- Prioritize local KB sources; supplement with web results.
- If context is insufficient, say so honestly.
- Be concise and direct. Include specific numbers when available.

Retrieved Context:
{context}
""",
    "direct": """You are a knowledgeable assistant.

{buddy_extra}

Rules:
- Answer in the same language as the user's question. If the user writes in Chinese, you MUST reply in Chinese. Never switch to English unless the user uses English.
- Be concise and direct.
- If you're not sure about something, say so honestly.

{context}
""",
}
# Backward compat alias
SYSTEM_PROMPT = SYSTEM_PROMPTS["kb"]

# Persistent conversation store
_conversations: dict[str, list] = {}
_conv_titles: dict[str, str] = {}  # conversation_id -> title
_global_memories: list = []  # [{id, content, source, created_at}]
_conv_file = None
_titles_file = None
_memories_file = None

DEFAULT_MEMORY_TURNS = 10


def _get_conv_file(workspace: str = "default"):
    from kbase.config import get_workspace_dir
    path = get_workspace_dir(workspace) / "conversations.json"
    return path


def _get_titles_file(workspace: str = "default"):
    from kbase.config import get_workspace_dir
    return get_workspace_dir(workspace) / "conv_titles.json"


def _get_memories_file(workspace: str = "default"):
    from kbase.config import get_workspace_dir
    return get_workspace_dir(workspace) / "global_memories.json"


def _load_conversations(workspace: str = "default"):
    global _conv_file, _titles_file, _memories_file
    _conv_file = _get_conv_file(workspace)
    _titles_file = _get_titles_file(workspace)
    _memories_file = _get_memories_file(workspace)
    if _conv_file.exists():
        try:
            data = json.loads(_conv_file.read_text())
            _conversations.clear()
            _conversations.update(data)
        except Exception:
            pass
    if _titles_file and _titles_file.exists():
        try:
            _conv_titles.clear()
            _conv_titles.update(json.loads(_titles_file.read_text()))
        except Exception:
            pass
    if _memories_file and _memories_file.exists():
        try:
            _global_memories.clear()
            _global_memories.extend(json.loads(_memories_file.read_text()))
        except Exception:
            pass
    return _conversations


def _save_conversations():
    if _conv_file:
        _conv_file.parent.mkdir(parents=True, exist_ok=True)
        _conv_file.write_text(json.dumps(_conversations, ensure_ascii=False, indent=1))
    if _titles_file:
        _titles_file.parent.mkdir(parents=True, exist_ok=True)
        _titles_file.write_text(json.dumps(_conv_titles, ensure_ascii=False, indent=1))


def _save_memories():
    if _memories_file:
        _memories_file.parent.mkdir(parents=True, exist_ok=True)
        _memories_file.write_text(json.dumps(_global_memories, ensure_ascii=False, indent=1))


def _detect_intent(question: str) -> str:
    """Detect query intent and route to appropriate search mode (no LLM needed).

    Returns: "direct" | "kb" | "web" | "hybrid" | "research"
    """
    q = question.strip().lower()

    # Direct chat signals (no search needed)
    direct_signals = [
        "你好", "hello", "hi ", "hey", "谢谢", "thanks", "再见", "bye",
        "你是谁", "who are you", "帮我", "help me",
    ]
    if any(q.startswith(s) or q == s for s in direct_signals):
        return "direct"
    if len(q) < 5 and not any('\u4e00' <= c <= '\u9fff' for c in q):
        return "direct"

    # Web search signals
    web_signals = [
        "最新", "latest", "news", "新闻", "今天", "today", "2026", "2025",
        "价格", "price", "天气", "weather", "股价", "stock",
        "怎么样", "what is", "who is", "where is",
    ]
    # If query asks about external/real-time info not in local docs
    web_score = sum(1 for s in web_signals if s in q)

    # KB search signals
    kb_signals = [
        "文件", "file", "文档", "document", "报告", "report", "方案", "plan",
        "会议", "meeting", "邮件", "email", "ppt", "excel", "pdf",
        "我们的", "our", "公司", "company", "部门", "department",
        "上次", "之前", "去年", "上季度",
    ]
    kb_score = sum(1 for s in kb_signals if s in q)

    # Research signals (require strong intent indicators)
    research_signals = [
        "研究", "research", "综合分析", "comprehensive", "深入研究",
        "详细分析", "深度调研", "全面分析", "写一份报告", "deep dive",
    ]
    research_score = sum(1 for s in research_signals if s in q)

    if research_score >= 1:
        return "research"
    if kb_score > web_score:
        return "kb"
    if web_score > kb_score:
        return "web"
    if web_score > 0 and kb_score > 0:
        return "hybrid"

    # Default: KB search (most common use case for a local knowledge base)
    return "kb"


MAX_MEMORIES = 100  # Hard cap on total stored memories


def _select_relevant_memories(question: str, max_items: int = 10) -> list[str]:
    """Select memories most relevant to the current question.

    Strategy: keyword overlap scoring + recency boost.
    Falls back to most recent if no keyword match.
    """
    if not _global_memories:
        return []

    import jieba
    q_words = set(jieba.cut(question.lower()))
    # Remove stopwords
    q_words -= {"的", "是", "了", "在", "和", "与", "有", "被", "对", "等", "用",
                "个", "这", "那", "要", "会", "就", "都", "也", "我", "你", "他",
                "什么", "怎么", "如何", "吗", "呢", "吧", "啊", "哪"}

    scored = []
    now = __import__("time").time()
    for i, mem in enumerate(_global_memories):
        content = mem.get("content", "")
        mem_words = set(jieba.cut(content.lower()))
        # Keyword overlap score
        overlap = len(q_words & mem_words)
        # Recency score: newer memories get slight boost (decay over 30 days)
        created = mem.get("created_at", "")
        recency = 0.1  # default low
        if created:
            try:
                from datetime import datetime
                dt = datetime.strptime(created, "%Y-%m-%d %H:%M")
                age_days = (now - dt.timestamp()) / 86400
                recency = max(0, 1.0 - age_days / 30)  # 0~1, decays over 30 days
            except (ValueError, TypeError):
                pass
        score = overlap * 2 + recency
        scored.append((score, i, content))

    # Sort by score desc, take top N
    scored.sort(key=lambda x: -x[0])
    selected = [s[2] for s in scored[:max_items]]
    return selected


def _deduplicate_memories():
    """Remove duplicate/similar memories. Keep the newer one."""
    if len(_global_memories) <= 1:
        return
    from difflib import SequenceMatcher
    seen = []
    deduped = []
    for mem in reversed(_global_memories):  # newest first
        content = mem.get("content", "").strip()
        is_dup = False
        for s in seen:
            if SequenceMatcher(None, content, s).ratio() > 0.7:
                is_dup = True
                break
        if not is_dup:
            seen.append(content)
            deduped.append(mem)
    deduped.reverse()
    if len(deduped) < len(_global_memories):
        removed = len(_global_memories) - len(deduped)
        _global_memories.clear()
        _global_memories.extend(deduped[-MAX_MEMORIES:])  # also enforce cap
        _save_memories()
        print(f"[KBase] Memory dedup: removed {removed} duplicates, {len(_global_memories)} remaining")


def _compute_context_budget(question: str, results: list) -> int:
    """Dynamically compute how many context chunks to include.

    Simple questions get fewer chunks (less noise), complex questions get more.
    Prevents the "Lost in the Middle" effect (RAGFlow insight).
    """
    q = question.strip().lower()

    # Short questions = simple, limit context (but check for CJK chars which are shorter)
    cjk_count = sum(1 for c in q if '\u4e00' <= c <= '\u9fff')
    effective_len = len(q) if cjk_count == 0 else cjk_count * 2 + (len(q) - cjk_count)
    if effective_len < 15:
        return 3

    # Complex signals = need more context
    complex_signals = ["对比", "compare", "所有", "all", "列出", "list",
                       "区别", "difference", "分别", "各个", "分析", "analyze"]
    complexity = sum(1 for s in complex_signals if s in q)

    if complexity >= 2:
        return 10
    if complexity >= 1:
        return 6

    # Medium complexity
    return 5


def chat(store: KBaseStore, question: str, settings: dict = None,
         top_k: int = 10, conversation_id: str = "default",
         history: list = None) -> dict:
    """Search knowledge base and generate LLM response with conversation memory."""
    settings = settings or {}
    memory_turns = settings.get("memory_turns", DEFAULT_MEMORY_TURNS)
    buddy_mode = settings.get("buddy_preset", "buddy")

    # Load persistent conversations
    if not _conversations:
        _load_conversations()

    # Get or create conversation history
    if history is not None:
        conv_history = history
    else:
        if conversation_id not in _conversations:
            _conversations[conversation_id] = []
        conv_history = _conversations[conversation_id]

    # 0. Intent detection + auto mode routing
    search_mode = settings.get("search_mode", "kb")
    if search_mode == "auto":
        search_mode = _detect_intent(question)
    skip_words = {"开始", "go", "start", "直接搜", "搜吧", "研究吧", "好的", "ok"}
    is_followup = question.strip().lower() in skip_words or len(conv_history) >= 2
    if search_mode == "research" and not is_followup:
        # First message in research mode — check if we need clarification
        clarity = _assess_question_clarity(question)
        if clarity.get("needs_clarification"):
            # Return clarifying questions instead of searching
            conv_history.append({"role": "user", "content": question})
            clarify_response = clarity["response"]
            conv_history.append({"role": "assistant", "content": clarify_response})
            _save_conversations()
            return {
                "question": question,
                "answer": clarify_response,
                "sources": [],
                "web_sources": [],
                "provider": "system",
                "buddy": buddy_mode,
                "context_chunks": 0,
                "search_mode": "research",
                "history_turns": len(conv_history) // 2,
            }

    # 1. Build search query enhanced with conversation context
    # If user said "go"/"开始", use the original question from history
    if question.strip().lower() in skip_words and conv_history:
        for msg in conv_history:
            if msg["role"] == "user":
                question = msg["content"]
                break
    search_query = _enhance_query(question, conv_history)

    # 2. Retrieve context based on search mode
    context_parts = []
    source_files = []
    web_sources = []

    # Direct mode: no search, just chat with memory
    if search_mode == "direct":
        pass  # Skip all retrieval, just use memory + conversation history

    # KB search (for kb, hybrid, research modes)
    elif search_mode in ("kb", "hybrid", "research"):
        # Create lightweight LLM func for HyDE/Multi-Query (optional, enhances search)
        def _search_llm(prompt):
            try:
                return _call_llm(provider, [{"role": "user", "content": prompt}], "", settings)
            except Exception:
                return ""
        search_result = hybrid_search(store, search_query, top_k=max(top_k, 15), llm_func=_search_llm)
        for i, r in enumerate(search_result.get("results", [])):
            meta = r.get("metadata", {})
            fname = meta.get("file_name", "unknown")
            fpath = meta.get("file_path", "")
            text = r.get("text", "")[:800]
            context_parts.append(f"[KB Source {i+1}: {fname}]\n{text}")
            if fpath and fpath not in [s["path"] for s in source_files]:
                source_files.append({
                    "name": fname, "path": fpath,
                    "score": r.get("rrf_score") or r.get("score", 0),
                    "preview": r.get("text", "")[:400],
                })

    # Web search (for web, hybrid, research modes)
    if search_mode in ("web", "hybrid", "research"):
        from kbase.websearch import web_search, research as do_research
        if search_mode == "research":
            # Deep research: multi-step
            research_data = do_research(search_query, max_steps=3)
            for step in research_data.get("findings", []):
                for wr in step.get("web", []):
                    context_parts.append(f"[Web: {wr['title']}]\n{wr['snippet']}")
                    web_sources.append({"name": wr["title"], "url": wr["url"], "source": "web"})
        else:
            # Single web search
            web_results = web_search(search_query, max_results=5, settings=settings)
            for wr in web_results:
                context_parts.append(f"[Web: {wr['title']}]\n{wr['snippet']}")
                web_sources.append({"name": wr["title"], "url": wr["url"], "source": "web"})

    # Apply context budget: limit chunks to prevent "Lost in the Middle" effect
    budget = _compute_context_budget(question, context_parts)
    context_parts = context_parts[:budget]
    context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant context found."

    # 3. Build buddy personality
    buddy_info = BUDDY_PRESETS.get(buddy_mode, BUDDY_PRESETS["buddy"])
    buddy_extra = buddy_info.get("system_extra", "")
    # Custom buddy: use user-defined prompt from settings
    if buddy_mode == "custom" and settings.get("custom_buddy_prompt"):
        buddy_extra = settings["custom_buddy_prompt"]

    # 4. Build system prompt (inject relevant memories)
    memory_context = ""
    if _global_memories:
        mem_lines = _select_relevant_memories(question, max_items=10)
        if mem_lines:
            memory_context = "\n\nUser Memory (facts learned from previous conversations):\n" + "\n".join(f"- {l}" for l in mem_lines)
    prompt_template = SYSTEM_PROMPTS.get(search_mode, SYSTEM_PROMPTS["kb"])
    system = prompt_template.format(context=context, buddy_extra=buddy_extra) + memory_context

    # 5. Build messages with conversation history
    messages = []
    recent = conv_history[-(memory_turns * 2):] if memory_turns > 0 else []
    for msg in recent:
        messages.append(msg)
    messages.append({"role": "user", "content": question})

    # 6. Call LLM
    provider_key = settings.get("llm_provider", "claude-sonnet")
    provider = LLM_PROVIDERS.get(provider_key, LLM_PROVIDERS["claude-sonnet"])

    try:
        answer = _call_llm(provider, messages, system, settings)
    except Exception as e:
        answer = f"Error: {str(e)}"

    # 7. Save to conversation history (include sources for restore)
    conv_history.append({"role": "user", "content": question})
    conv_history.append({"role": "assistant", "content": answer, "sources": source_files[:8], "search_mode": search_mode})

    # Trim history if too long
    max_msgs = (memory_turns + 5) * 2
    if len(conv_history) > max_msgs:
        conv_history[:] = conv_history[-max_msgs:]

    # Persist
    _save_conversations()

    return {
        "question": question,
        "answer": answer,
        "sources": source_files[:8],
        "provider": provider_key,
        "buddy": buddy_mode,
        "context_chunks": len(context_parts),
        "web_sources": web_sources[:5],
        "search_mode": search_mode,
        "history_turns": len(conv_history) // 2,
    }


def clear_conversation(conversation_id: str = "default"):
    """Clear conversation history."""
    _conversations.pop(conversation_id, None)
    _conv_titles.pop(conversation_id, None)
    _save_conversations()


def get_conv_title(conversation_id: str) -> str:
    return _conv_titles.get(conversation_id, "")


def set_conv_title(conversation_id: str, title: str):
    _conv_titles[conversation_id] = title
    _save_conversations()


def generate_title(conversation_id: str, settings: dict = None) -> str:
    """Auto-generate a short title from the first Q&A in a conversation."""
    settings = settings or {}
    msgs = _conversations.get(conversation_id, [])
    if not msgs:
        return ""
    # Use first user message + first assistant reply
    first_q = ""
    first_a = ""
    for m in msgs[:4]:
        if m["role"] == "user" and not first_q:
            first_q = m["content"][:300]
        elif m["role"] == "assistant" and not first_a:
            first_a = m["content"][:300]
    if not first_q:
        return ""
    # Simple heuristic: extract short title from question
    # If LLM is available, use it; otherwise fallback to truncation
    provider_key = settings.get("llm_provider", "claude-sonnet")
    provider = LLM_PROVIDERS.get(provider_key, LLM_PROVIDERS.get("claude-sonnet"))
    try:
        prompt = (
            f"Generate a short title (max 20 chars) for this conversation. "
            f"Use the SAME LANGUAGE as the user's message. No quotes, no punctuation.\n\n"
            f"User: {first_q}\n\n"
            f"Assistant: {first_a[:200] if first_a else '(no reply)'}"
        )
        title = _call_llm(provider, [{"role": "user", "content": prompt}],
                          "You are a title generator. Output ONLY the title itself, nothing else. Match the language of the user's message.", settings)
        title = title.strip().strip('"\'""''').strip()[:30]
    except Exception:
        # Fallback: use first question truncated
        title = first_q.replace('\n', ' ').strip()[:25]
    _conv_titles[conversation_id] = title
    _save_conversations()
    return title


# === Global Memory System ===

def get_memories() -> list:
    return list(_global_memories)


def add_memory(content: str, source: str = "manual") -> dict:
    """Add a memory entry."""
    entry = {
        "id": f"mem-{int(time.time()*1000)}",
        "content": content.strip(),
        "source": source,
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    _global_memories.append(entry)
    _save_memories()
    return entry


def delete_memory(mem_id: str):
    """Delete a memory by id."""
    _global_memories[:] = [m for m in _global_memories if m["id"] != mem_id]
    _save_memories()


def extract_memories_from_conversation(conversation_id: str, settings: dict = None) -> list:
    """Use LLM to extract key facts/preferences from a conversation."""
    settings = settings or {}
    msgs = _conversations.get(conversation_id, [])
    if not msgs or len(msgs) < 4:
        return []

    # Build conversation text (last 10 messages)
    conv_text = ""
    for m in msgs[-10:]:
        role = "用户" if m["role"] == "user" else "助手"
        conv_text += f"{role}：{m['content'][:300]}\n\n"

    # Existing memories to avoid duplicates
    existing = "\n".join(m["content"] for m in _global_memories[-20:])

    provider_key = settings.get("llm_provider", "claude-sonnet")
    provider = LLM_PROVIDERS.get(provider_key, LLM_PROVIDERS.get("claude-sonnet"))

    try:
        prompt = (
            f"从以下对话中提取值得长期记住的关键信息（用户偏好、角色背景、重要决策、常用术语等）。\n"
            f"每条记忆一行，简洁准确，不超过50字。只输出新的信息，不要重复已有记忆。\n"
            f"如果没有值得记忆的内容，输出'无'。\n\n"
            f"已有记忆：\n{existing[:500] if existing else '(无)'}\n\n"
            f"对话内容：\n{conv_text[:2000]}"
        )
        result = _call_llm(provider, [{"role": "user", "content": prompt}],
                           "你是记忆提取器，只输出记忆条目，每行一条。", settings)
        lines = [l.strip().strip("-").strip("•").strip("0123456789.").strip()
                 for l in result.strip().split("\n") if l.strip() and len(l.strip()) > 5]
        if lines and lines[0] != "无":
            new_mems = []
            for line in lines[:5]:
                entry = add_memory(line, source=f"conv:{conversation_id}")
                new_mems.append(entry)
            # Deduplicate and enforce cap after each extraction
            _deduplicate_memories()
            return new_mems
    except Exception:
        pass
    return []


def _assess_question_clarity(question: str) -> dict:
    """Assess if a research question is clear enough, or needs clarification.

    Returns {"needs_clarification": bool, "response": str}
    """
    q = question.strip()
    word_count = len(q)

    # Very short or vague queries need clarification
    vague_patterns = [
        "怎么样", "如何", "什么情况", "有什么", "说说", "讲讲",
        "帮我看看", "分析一下", "告诉我", "介绍",
        "how", "what about", "tell me about", "summarize",
    ]

    is_vague = word_count < 10 and any(p in q.lower() for p in vague_patterns)
    is_too_short = word_count < 6
    is_broad = not any(c.isdigit() for c in q) and word_count < 15 and any(
        p in q for p in ["所有", "全部", "各", "每个", "all", "every", "each"]
    )

    if is_vague or is_too_short or is_broad:
        # Generate clarifying questions
        response = _generate_clarification(q)
        return {"needs_clarification": True, "response": response}

    return {"needs_clarification": False}


def _generate_clarification(question: str) -> str:
    """Generate clarifying questions to help user refine their research query."""
    # Detect language
    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in question)

    if has_chinese:
        return f"""我想更好地帮你研究这个问题。能否进一步明确：

**关于「{question}」，请告诉我：**

1. **时间范围** — 你关注哪个时间段？（如：2025年Q1、最近3个月）
2. **具体方面** — 你最关心哪个维度？（如：进展/问题/数据/方案/对比）
3. **目的** — 这个研究结果用来做什么？（如：汇报材料、决策参考、学习了解）
4. **深度** — 需要概要还是详细分析？

你可以直接补充说明，我会基于你的要求进行深度搜索和分析。也可以直接回复"开始"，我会用当前问题直接研究。"""
    else:
        return f"""I'd like to help you research this thoroughly. Could you clarify:

**About "{question}":**

1. **Time range** — Which period? (e.g., Q1 2025, last 3 months)
2. **Focus area** — What aspect matters most? (e.g., progress, issues, data, comparison)
3. **Purpose** — What's this for? (e.g., report, decision-making, learning)
4. **Depth** — Overview or detailed analysis?

Reply with more details, or just say "go" to research with the current question."""


def _enhance_query(question: str, history: list) -> str:
    """Enhance search query with conversation context for better retrieval."""
    if not history:
        return question

    # Take last 2 turns for context
    recent_context = []
    for msg in history[-4:]:
        if msg["role"] == "user":
            recent_context.append(msg["content"])

    if recent_context:
        combined = " ".join(recent_context[-2:]) + " " + question
        # Keep it reasonable length
        if len(combined) > 500:
            combined = combined[:500]
        return combined
    return question


def _call_llm(provider: dict, messages: list, system: str, settings: dict) -> str:
    ptype = provider["type"]
    if ptype == "anthropic":
        return _call_anthropic(provider, messages, system, settings)
    elif ptype == "openai":
        return _call_openai(provider, messages, system, settings)
    elif ptype == "openai-compatible":
        return _call_openai_compatible(provider, messages, system, settings)
    elif ptype == "ollama":
        return _call_ollama(provider, messages, system, settings)
    elif ptype == "cli":
        return _call_cli(provider, messages, system, settings)
    elif ptype == "dify":
        return _call_dify(provider, messages, system, settings)
    return f"Unsupported: {ptype}"


def _call_anthropic(provider, messages, system, settings):
    api_key = settings.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Configure in Settings.")
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=provider["model"],
        max_tokens=2048,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def _call_openai(provider, messages, system, settings):
    api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set. Configure in Settings.")
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    full_msgs = [{"role": "system", "content": system}] + messages
    response = client.chat.completions.create(
        model=provider["model"], messages=full_msgs, max_tokens=2048,
    )
    return response.choices[0].message.content


def _call_openai_compatible(provider, messages, system, settings):
    key_env = provider.get("key_env", "")
    api_key = settings.get(key_env.lower()) or os.environ.get(key_env, "")
    if not api_key:
        raise ValueError(f"{key_env} not set. Configure in Settings.")
    from openai import OpenAI
    # Support custom model/base_url override
    base_url = settings.get("custom_base_url") or provider.get("base_url", "")
    model = settings.get("custom_model") or provider.get("model", "")
    if not model:
        raise ValueError("Model name not set. Configure in Settings.")
    client = OpenAI(api_key=api_key, base_url=base_url)
    full_msgs = [{"role": "system", "content": system}] + messages
    response = client.chat.completions.create(
        model=model, messages=full_msgs, max_tokens=2048,
    )
    return response.choices[0].message.content


def _call_ollama(provider, messages, system, settings):
    import urllib.request
    model = settings.get("ollama_model") or provider["model"]
    url = settings.get("ollama_url", "http://localhost:11434") + "/api/chat"
    full_msgs = [{"role": "system", "content": system}] + messages
    payload = json.dumps({"model": model, "messages": full_msgs, "stream": False}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data.get("message", {}).get("content", "No response")
    except Exception as e:
        raise ValueError(f"Ollama error (running?): {e}")


def _call_cli(provider, messages, system, settings):
    """Call LLM via local CLI command (claude -p, llm, qwen -p, etc.).
    Uses the system's installed CLI tool with local OAuth/auth.
    """
    import subprocess
    import shutil
    from pathlib import Path

    cmd_template = settings.get("cli_command") or provider.get("cmd", "claude -p")
    cmd_parts = cmd_template.split()
    executable = cmd_parts[0]

    # Expand PATH for macOS .app bundles (which don't inherit user shell PATH)
    extra_paths = [
        "/usr/local/bin", "/opt/homebrew/bin",
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".npm-global" / "bin"),
    ]
    # Also check nvm-managed node paths
    nvm_dir = Path.home() / ".nvm" / "versions" / "node"
    if nvm_dir.exists():
        for node_ver in sorted(nvm_dir.iterdir(), reverse=True):
            extra_paths.append(str(node_ver / "bin"))
    # Check cargo, go, etc.
    for p in [".cargo/bin", "go/bin", ".bun/bin"]:
        extra_paths.append(str(Path.home() / p))

    import os
    env_path = os.environ.get("PATH", "")
    full_path = os.pathsep.join(extra_paths) + os.pathsep + env_path
    os.environ["PATH"] = full_path

    # Check if CLI tool exists
    if not shutil.which(executable):
        raise ValueError(
            f"'{executable}' not found in PATH. "
            f"Install it first, then ensure it's authenticated (e.g., '{executable} login' or '{executable} --help').\n"
            f"Searched: {', '.join(extra_paths[:5])}..."
        )

    # Build prompt — keep it concise for CLI tools (they're slow with long input)
    user_question = messages[-1]["content"] if messages else ""
    # CLI tools have limited throughput — cap prompt at ~4000 chars
    max_prompt = 4000
    if len(system) > max_prompt:
        # Keep the first part (instructions) and truncate context
        system = system[:max_prompt] + "\n... (context truncated for CLI mode)"
    full_prompt = f"{system}\n\nUser question: {user_question}"

    cli_timeout = int(settings.get("cli_timeout", 120))
    try:
        result = subprocess.run(
            cmd_parts,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=cli_timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise ValueError(f"CLI error (exit {result.returncode}): {stderr[:500]}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise ValueError(f"CLI timed out after {cli_timeout}s. Try a shorter question or switch to a cloud LLM.")
    except FileNotFoundError:
        raise ValueError(f"'{executable}' not found")


def _call_dify(provider, messages, system, settings):
    """Call Dify API (/v1/chat-messages format)."""
    import urllib.request
    api_key = settings.get("custom_api_key") or settings.get("dify_api_key", "")
    if not api_key:
        raise ValueError("Dify API key not set. Configure in Settings.")
    base_url = (settings.get("custom_base_url") or provider.get("base_url", "")).rstrip("/")
    if not base_url:
        raise ValueError("Dify Base URL not set. Configure in Settings.")

    # Dify expects: {query, user, inputs, response_mode}
    # Combine system prompt + messages into query
    user_msg = messages[-1]["content"] if messages else ""
    query = f"{system}\n\n{user_msg}" if system else user_msg

    payload = json.dumps({
        "inputs": {},
        "query": query,
        "response_mode": "blocking",
        "user": "kbase-user",
    }).encode()

    url = f"{base_url}/chat-messages"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data.get("answer", "") or data.get("message", "No response")
    except Exception as e:
        raise ValueError(f"Dify API error: {e}")


# ---- Knowledge Compilation (Karpathy LLM Wiki-inspired) ----

def generate_document_summary(text: str, file_name: str, settings: dict = None) -> str:
    """Generate a structured summary for a document during ingest.

    Inspired by Karpathy's LLM Wiki: instead of just chunking and embedding,
    we "compile" each document into a structured summary with:
    - One-line description
    - Key topics/tags
    - Core concepts and findings
    - Potential relationships to other topics
    """
    settings = settings or {}
    provider_key = settings.get("llm_provider", "")
    provider = LLM_PROVIDERS.get(provider_key)
    if not provider:
        return ""

    # Take first ~3000 chars for summary (enough for understanding, saves tokens)
    excerpt = text[:3000].strip()
    if not excerpt:
        return ""

    prompt = (
        f"File: {file_name}\n\n"
        f"Content excerpt:\n{excerpt}\n\n"
        f"Generate a structured summary in the SAME LANGUAGE as the document content:\n"
        f"1. **Description**: One sentence describing what this document is about\n"
        f"2. **Topics**: 3-5 topic tags (comma separated)\n"
        f"3. **Key Points**: 3-5 bullet points of the most important content\n"
        f"4. **Entities**: Key names, organizations, dates, project names mentioned (comma separated)\n"
        f"5. **Questions**: 2-3 questions that someone might ask that would lead to this document\n"
        f"6. **Related Topics**: 2-3 topics this document likely connects to\n\n"
        f"Keep it concise (under 250 words). Use the document's language."
    )

    try:
        return _call_llm(
            provider,
            [{"role": "user", "content": prompt}],
            "You are a knowledge librarian. Generate concise, accurate document summaries.",
            settings,
        )
    except Exception as e:
        print(f"[KBase] Summary generation failed for {file_name}: {e}")
        return ""


def generate_edge_descriptions(file_pairs: list[dict], settings: dict = None) -> list[str]:
    """Generate semantic descriptions for document relationships.

    Instead of just a similarity score, describe WHY two documents are related.
    Batch multiple pairs in one LLM call to save tokens.

    Args:
        file_pairs: list of {"source_name": str, "source_summary": str,
                             "target_name": str, "target_summary": str}
    Returns:
        list of description strings, one per pair
    """
    settings = settings or {}
    provider_key = settings.get("llm_provider", "")
    provider = LLM_PROVIDERS.get(provider_key)
    if not provider or not file_pairs:
        return [""] * len(file_pairs)

    pairs_text = ""
    for i, pair in enumerate(file_pairs):
        pairs_text += (
            f"Pair {i+1}:\n"
            f"  A: {pair['source_name']}"
        )
        if pair.get("source_summary"):
            pairs_text += f" — {pair['source_summary'][:150]}"
        pairs_text += (
            f"\n  B: {pair['target_name']}"
        )
        if pair.get("target_summary"):
            pairs_text += f" — {pair['target_summary'][:150]}"
        pairs_text += "\n\n"

    prompt = (
        f"For each document pair below, write a SHORT relationship label (5-10 words) "
        f"describing how they are connected. Use the documents' language.\n\n"
        f"{pairs_text}"
        f"Return ONLY the labels, one per line, numbered. Example:\n"
        f"1. Same project technical specs\n"
        f"2. Budget report for Q3 initiative\n"
    )

    try:
        result = _call_llm(
            provider,
            [{"role": "user", "content": prompt}],
            "You are a knowledge graph expert. Generate precise, short relationship labels.",
            settings,
        )
        # Parse numbered lines
        lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
        labels = []
        for line in lines:
            # Remove numbering like "1. " or "1: "
            import re
            cleaned = re.sub(r"^\d+[\.\):]\s*", "", line)
            labels.append(cleaned)
        # Pad if needed
        while len(labels) < len(file_pairs):
            labels.append("")
        return labels[:len(file_pairs)]
    except Exception as e:
        print(f"[KBase] Edge description generation failed: {e}")
        return [""] * len(file_pairs)
