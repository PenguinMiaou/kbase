"""Configuration for kbase."""
import json
import os
from pathlib import Path

# Default storage location
DEFAULT_BASE_DIR = Path.home() / ".kbase"

# Supported file types
SUPPORTED_EXTENSIONS = {
    ".md", ".txt",
    ".pptx", ".ppt",
    ".docx", ".doc",
    ".xlsx", ".xls", ".csv",
    ".pdf",
    ".html",
    ".eml", ".msg", ".mbox",
    # Audio (requires whisper)
    ".mp3", ".m4a", ".wav", ".mp4", ".ogg", ".flac", ".webm",
    # Archives (auto-extract)
    ".zip", ".rar", ".7z", ".tar", ".gz", ".tgz",
}

# Chunking
CHUNK_MAX_CHARS = 1500
CHUNK_OVERLAP_CHARS = 400

# Search defaults
DEFAULT_TOP_K = 10

# Available embedding models
EMBEDDING_MODELS = {
    # --- China / Local (国内/本地) ---
    "bge-small-zh": {
        "name": "BAAI/bge-small-zh-v1.5", "type": "local", "group": "china",
        "desc": "BGE Small - 轻量中文 (90MB)", "dim": 512,
        "logo": "/static/logos/bge_logo.jpeg",
    },
    "bge-base-zh": {
        "name": "BAAI/bge-base-zh-v1.5", "type": "local", "group": "china",
        "desc": "BGE Base - 中文推荐 (400MB)", "dim": 768,
        "logo": "/static/logos/bge_logo.jpeg",
    },
    "bge-large-zh": {
        "name": "BAAI/bge-large-zh-v1.5", "type": "local", "group": "china",
        "desc": "BGE Large - 最强中文 (1.2GB)", "dim": 1024,
        "logo": "/static/logos/bge_logo.jpeg",
    },
    "bge-m3": {
        "name": "BAAI/bge-m3", "type": "local", "group": "china",
        "desc": "BGE-M3 - 多语言 (2.2GB, 中英日韩)", "dim": 1024,
        "logo": "/static/logos/bge_logo.jpeg",
    },
    "acge-text": {
        "name": "aspire/acge_text_embedding", "type": "local", "group": "china",
        "desc": "ACGE - 阿里达摩院中文 Embedding", "dim": 1024,
        "logo": "/static/logos/qwen-new.png",
    },
    "gte-qwen2": {
        "name": "Alibaba-NLP/gte-Qwen2-1.5B-instruct", "type": "local", "group": "china",
        "desc": "GTE-Qwen2 - 阿里通义实验室", "dim": 1536,
        "logo": "/static/logos/qwen-new.png",
    },
    "dashscope-emb": {
        "name": "text-embedding-v3", "type": "openai-compatible-emb", "group": "china",
        "desc": "阿里 DashScope Embedding API",
        "dim": 1024, "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "key_env": "DASHSCOPE_API_KEY",
        "logo": "/static/logos/qwen-new.png",
    },
    "zhipu-emb": {
        "name": "embedding-3", "type": "openai-compatible-emb", "group": "china",
        "desc": "智谱 Embedding-3 API",
        "dim": 2048, "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "key_env": "ZHIPU_API_KEY",
        "logo": "/static/logos/zhipu-color.png",
    },
    # --- International (国际) ---
    "multilingual-e5": {
        "name": "intfloat/multilingual-e5-base", "type": "local", "group": "global",
        "desc": "E5 Multilingual - 多语言通用", "dim": 768,
        "logo": "/static/logos/bge_logo.jpeg",
    },
    "openai": {
        "name": "text-embedding-3-small", "type": "openai", "group": "global",
        "desc": "OpenAI Embedding Small", "dim": 1536,
        "logo": "/static/logos/openai.svg",
    },
    "openai-large": {
        "name": "text-embedding-3-large", "type": "openai", "group": "global",
        "desc": "OpenAI Embedding Large (最强)", "dim": 3072,
        "logo": "/static/logos/openai.svg",
    },
    "voyageai": {
        "name": "voyage-3", "type": "voyageai", "group": "global",
        "desc": "Voyage AI (中文效果极好)", "dim": 1024,
        "logo": "/static/logos/voyageai.webp",
    },
    "gemini-emb": {
        "logo": "/static/logos/gemini.webp",
        "name": "text-embedding-004", "type": "openai-compatible-emb", "group": "global",
        "desc": "Google Gemini Embedding",
        "dim": 768, "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
    },
}

# Default embedding model
DEFAULT_EMBEDDING_MODEL = os.environ.get("KBASE_EMBEDDING_MODEL", "bge-small-zh")

# Available Whisper ASR models
WHISPER_MODELS = {
    # --- Local (本地) ---
    "whisper-tiny": {
        "name": "tiny", "type": "local", "group": "local",
        "desc": "Whisper Tiny - 最快 (75MB)",
        "logo": "/static/logos/openai.svg",
    },
    "whisper-base": {
        "name": "base", "type": "local", "group": "local",
        "desc": "Whisper Base - 平衡 (140MB, 推荐)",
        "logo": "/static/logos/openai.svg",
    },
    "whisper-small": {
        "name": "small", "type": "local", "group": "local",
        "desc": "Whisper Small - 较好 (460MB)",
        "logo": "/static/logos/openai.svg",
    },
    "whisper-medium": {
        "name": "medium", "type": "local", "group": "local",
        "desc": "Whisper Medium - 高精度 (1.5GB)",
        "logo": "/static/logos/openai.svg",
    },
    "whisper-large-v3": {
        "name": "large-v3", "type": "local", "group": "local",
        "desc": "Whisper Large V3 - 最强 (3GB)",
        "logo": "/static/logos/openai.svg",
    },
    "faster-whisper-large": {
        "name": "large-v3", "type": "faster-whisper", "group": "local",
        "desc": "Faster Whisper - CTranslate2加速 (推荐)",
        "logo": "/static/logos/openai.svg",
    },
    # --- China Cloud (国内云) ---
    "dashscope-asr": {
        "name": "paraformer-v2", "type": "dashscope-asr", "group": "china",
        "desc": "阿里 Paraformer - 中文识别最强",
        "logo": "/static/logos/qwen-new.png",
    },
    "tencent-asr": {
        "name": "tencent-asr", "type": "tencent-asr", "group": "china",
        "desc": "腾讯云语音识别",
        "logo": "/static/logos/hunyuan-color.png",
    },
    # --- International Cloud (国际云) ---
    "openai-whisper-api": {
        "name": "whisper-1", "type": "openai-api", "group": "global",
        "desc": "OpenAI Whisper API (25MB限制)",
        "logo": "/static/logos/openai.svg",
    },
    "gemini-asr": {
        "name": "gemini-2.0-flash", "type": "gemini-asr", "group": "global",
        "desc": "Google Gemini 音频理解",
        "logo": "/static/logos/gemini.webp",
    },
}

DEFAULT_WHISPER_MODEL = os.environ.get("KBASE_WHISPER_MODEL", "whisper-base")

# Vision models for image description in documents
VISION_MODELS = {
    # --- Global ---
    "gpt-4o-mini": {
        "name": "GPT-4o Mini", "type": "openai", "model": "gpt-4o-mini",
        "desc": "OpenAI - fast and cheap vision", "group": "global",
        "key_env": "OPENAI_API_KEY",
        "logo": "/static/logos/gpt.png",
    },
    "gpt-4o": {
        "name": "GPT-4o", "type": "openai", "model": "gpt-4o",
        "desc": "OpenAI - best quality vision", "group": "global",
        "key_env": "OPENAI_API_KEY",
        "logo": "/static/logos/gpt.png",
    },
    "gemini-flash": {
        "name": "Gemini 2.5 Flash", "type": "gemini", "model": "gemini-2.5-flash",
        "desc": "Google - fast, free tier available", "group": "global",
        "key_env": "GEMINI_API_KEY",
        "logo": "/static/logos/gemini-new.webp",
        "signup_url": "https://aistudio.google.com/apikey",
    },
    "claude-vision": {
        "name": "Claude Sonnet", "type": "anthropic", "model": "claude-sonnet-4-20250514",
        "desc": "Anthropic - excellent for charts/diagrams", "group": "global",
        "key_env": "ANTHROPIC_API_KEY",
        "logo": "/static/logos/claude.svg",
    },
    # --- China (国内) ---
    "qwen-vl": {
        "name": "Qwen-VL Plus", "type": "dashscope", "model": "qwen-vl-plus",
        "desc": "通义千问 - 中文图片理解最佳", "group": "china",
        "key_env": "DASHSCOPE_API_KEY",
        "logo": "/static/logos/qwen-new.png",
        "signup_url": "https://dashscope.console.aliyun.com/apiKey",
    },
    "glm-vision": {
        "name": "GLM-4V Flash", "type": "openai-compatible", "model": "glm-4v-flash",
        "desc": "智谱 - 免费视觉模型", "group": "china",
        "key_env": "GLM_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "logo": "/static/logos/zhipu-color.png",
    },
    # --- Local ---
    "ollama-vision": {
        "name": "Ollama (minicpm-v)", "type": "ollama", "model": "minicpm-v",
        "desc": "Local - free offline vision", "group": "local",
        "logo": "/static/logos/Ollama-logo.svg.png",
    },
    "none": {
        "name": "Disabled", "type": "none",
        "desc": "Skip image extraction", "group": "local",
        "logo": "/static/logos/llm.png",
    },
}

DEFAULT_VISION_MODEL = os.environ.get("KBASE_VISION_MODEL", "none")

# Language profiles for search optimization
LANGUAGE_PROFILES = {
    "zh": {
        "name": "Chinese (中文)",
        "desc": "Optimized for Simplified/Traditional Chinese",
        "segmenter": "jieba",
        "recommended_embedding": "bge-base-zh",
        "synonym_expansion": True,
        "notes": "Uses jieba segmentation + Chinese synonym expansion",
    },
    "zh-en": {
        "name": "Chinese + English (中英混合)",
        "desc": "Mixed Chinese and English content (default)",
        "segmenter": "jieba",
        "recommended_embedding": "bge-m3",
        "synonym_expansion": True,
        "notes": "Best for Chinese-English mixed documents",
    },
    "en": {
        "name": "English",
        "desc": "Optimized for English content",
        "segmenter": "whitespace",
        "recommended_embedding": "multilingual-e5",
        "synonym_expansion": False,
        "notes": "Standard whitespace tokenization",
    },
    "ja": {
        "name": "Japanese (日本語)",
        "desc": "Optimized for Japanese content",
        "segmenter": "mecab",
        "recommended_embedding": "bge-m3",
        "synonym_expansion": False,
        "notes": "Requires: pip install mecab-python3 unidic-lite",
    },
    "ko": {
        "name": "Korean (한국어)",
        "desc": "Optimized for Korean content",
        "segmenter": "mecab",
        "recommended_embedding": "bge-m3",
        "synonym_expansion": False,
        "notes": "Requires: pip install mecab-python3",
    },
    "multi": {
        "name": "Multilingual (多语言)",
        "desc": "Best for mixed-language content",
        "segmenter": "auto",
        "recommended_embedding": "bge-m3",
        "synonym_expansion": True,
        "notes": "Auto-detects language per document",
    },
}

DEFAULT_LANGUAGE = os.environ.get("KBASE_LANGUAGE", "zh-en")


def get_workspace_dir(workspace: str = "default") -> Path:
    base = Path(os.environ.get("KBASE_DIR", str(DEFAULT_BASE_DIR)))
    return base / workspace


def get_db_path(workspace: str = "default") -> Path:
    return get_workspace_dir(workspace) / "metadata.db"


def get_chroma_path(workspace: str = "default") -> Path:
    return get_workspace_dir(workspace) / "chroma"


def get_settings_path(workspace: str = "default") -> Path:
    return get_workspace_dir(workspace) / "settings.json"


def load_settings(workspace: str = "default") -> dict:
    """Load workspace settings."""
    path = get_settings_path(workspace)
    if path.exists():
        return json.loads(path.read_text())
    return {"embedding_model": DEFAULT_EMBEDDING_MODEL, "ingest_dirs": []}


def save_settings(workspace: str = "default", settings: dict = None):
    """Save workspace settings."""
    path = get_settings_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings or {}, ensure_ascii=False, indent=2))
