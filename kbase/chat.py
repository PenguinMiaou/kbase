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
}

# Buddy personality presets
BUDDY_PRESETS = {
    "professional": {
        "name": "Professional",
        "emoji": "",
        "desc": "严肃专业，适合工作场景",
        "system_extra": "You are a professional knowledge assistant. Be precise, structured, and formal.",
    },
    "buddy": {
        "name": "Buddy",
        "emoji": "",
        "desc": "友好随和，像个靠谱同事",
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
        "emoji": "",
        "desc": "数据分析师，擅长从数据中挖掘洞察",
        "system_extra": (
            "You are a sharp data analyst assistant. Focus on numbers, trends, comparisons. "
            "When answering, structure with: Key Finding → Supporting Data → Implication. "
            "Proactively point out anomalies or interesting patterns in the data."
        ),
    },
    "tutor": {
        "name": "Tutor",
        "emoji": "",
        "desc": "耐心的老师，善于解释复杂概念",
        "system_extra": (
            "You are a patient tutor. Explain concepts step by step. "
            "Use analogies the user would understand. Ask clarifying questions when needed. "
            "Break complex topics into digestible pieces."
        ),
    },
}

SYSTEM_PROMPT = """You are a knowledgeable assistant with access to the user's local knowledge base.
Answer based on the retrieved context below.

{buddy_extra}

Rules:
- Answer in the same language as the user's question.
- Cite source files using [filename] format.
- Files ending in .mbox are email archives — treat their content as emails.
- If context is insufficient, say so honestly.
- Be concise and direct. Include specific numbers when available.

Retrieved Context:
{context}
"""

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

    # 0. Research mode: check if question is clear enough
    search_mode = settings.get("search_mode", "kb")
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

    # KB search (for kb, hybrid, research modes)
    if search_mode in ("kb", "hybrid", "research"):
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
            web_results = web_search(search_query, max_results=5)
            for wr in web_results:
                context_parts.append(f"[Web: {wr['title']}]\n{wr['snippet']}")
                web_sources.append({"name": wr["title"], "url": wr["url"], "source": "web"})

    context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant context found."

    # 3. Build buddy personality
    buddy_info = BUDDY_PRESETS.get(buddy_mode, BUDDY_PRESETS["buddy"])
    buddy_extra = buddy_info.get("system_extra", "")

    # 4. Build system prompt (inject global memories if available)
    memory_context = ""
    if _global_memories:
        mem_lines = [m["content"] for m in _global_memories[-20:]]
        memory_context = "\n\nUser Memory (facts learned from previous conversations):\n" + "\n".join(f"- {l}" for l in mem_lines)
    system = SYSTEM_PROMPT.format(context=context, buddy_extra=buddy_extra) + memory_context

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
        prompt = f"根据以下对话内容，生成一个简短的标题（不超过20个字，不要引号，不要标点）：\n\n用户：{first_q}\n\n助手：{first_a[:200] if first_a else '(无回复)'}"
        title = _call_llm(provider, [{"role": "user", "content": prompt}],
                          "你是标题生成器，只输出标题本身，不要任何额外文字。", settings)
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

    # Build prompt — keep it concise for CLI tools
    # For claude -p: just send the user question with context as a single prompt
    user_question = messages[-1]["content"] if messages else ""
    # Trim system prompt to essentials (context + rules)
    full_prompt = f"{system}\n\nUser question: {user_question}"

    try:
        result = subprocess.run(
            cmd_parts,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise ValueError(f"CLI error (exit {result.returncode}): {stderr[:500]}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise ValueError(f"CLI timed out after 120s")
    except FileNotFoundError:
        raise ValueError(f"'{executable}' not found")
