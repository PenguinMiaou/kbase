# KBase - Local Knowledge Base
Copyright@PenguinMiaou

## Project Overview
Local knowledge base system: RAG + Text2SQL + Full-text Search with Web UI and CLI.
Turn any directory of files into a searchable, AI-powered knowledge base.

## Tech Stack
- **Backend**: Python 3.10, FastAPI, ChromaDB, SQLite FTS5
- **Frontend**: Vanilla HTML/CSS/JS (Claude-style 3-column layout with artifact panel)
- **Search**: Hybrid (vector + BM25 + LIKE fallback + filename + RRF fusion) + Re-ranking + Query Expansion + Chinese segmentation
- **LLM**: 20 providers (Claude/GPT/Gemini/DeepSeek/Qwen/GLM/Kimi/Doubao/Ollama/Claude CLI/Qwen CLI/LLM CLI/Custom)
- **File types**: PPTX, DOCX, XLSX, PDF, MD, HTML, MP3/M4A (Whisper), ZIP, EML, MBOX
- **Memory**: Global cross-conversation memory system with auto-extraction
- **Distribution**: Tauri native app (DMG/MSI) + PyPI (`pip install kbase-app`) + uv installer + install.sh/bat

## Project Structure
```
kbase/
├── kbase/
│   ├── cli.py           # CLI (13 commands: search, chat, ingest, sql, web, etc.)
│   ├── web.py           # FastAPI server + legacy inline UI (/v1) + model/update/memory APIs
│   ├── chat.py          # LLM chat with 20 providers + buddy presets + memory + title generation
│   ├── store.py         # ChromaDB + SQLite FTS5 + tabular storage + filename search + LIKE fallback
│   ├── search.py        # Enhanced pipeline: expand→multi-retrieve→fuse→dedup→rerank→dir-priority
│   ├── enhance.py       # Re-ranking, query expansion (60+ synonyms), Chinese segmentation
│   ├── extract.py       # File extractors (PPTX/DOCX/XLSX/PDF/MD/audio/mbox/archive)
│   ├── chunk.py         # Smart chunking (slide/page/heading aware)
│   ├── ingest.py        # Ingestion pipeline with contextual enrichment
│   ├── watch.py         # File watcher (watchdog)
│   ├── config.py        # Config (embedding/whisper/language models)
│   ├── websearch.py     # Web search (DuckDuckGo) + research module
│   ├── agent_loop.py    # Deep research agent (outline-first, multi-round, Claude Research-inspired)
│   ├── __init__.py      # Version (__version__ = "x.y.z")
│   ├── connectors/
│   │   ├── feishu.py    # Feishu/Lark connector (docs/chats/emails via API)
│   │   └── feishu_guide.py  # Setup guide (bilingual)
│   └── static/
│       ├── index.html   # Claude-style UI (3-column, artifact panel, error modal, drag-drop upload)
│       ├── css/app.css  # Styles (animations, transitions, source preview popup, skeleton loading)
│       ├── js/app.js    # Frontend logic (i18n, session titles, memory, model status, auto-update, progress)
│       └── logos/       # Provider logos (26+ SVG/PNG/WebP)
├── launcher.py          # Cross-platform app entry point (macOS menu bar / Windows system tray / generic)
├── kbase-desktop/       # Tauri native app shell (Rust + WebView)
│   ├── src-tauri/       # Rust: sidecar Python process, system tray, auto-update
│   ├── src/             # Splash page (loading → redirect to localhost)
│   └── scripts/         # Python env bootstrap (uv install)
├── kbase.spec           # PyInstaller spec for macOS DMG build (legacy)
├── kbase_win.spec       # PyInstaller spec for Windows EXE build (legacy)
├── .github/workflows/release.yml  # GitHub Actions CI — Tauri DMG/MSI + PyPI wheel
├── version.json         # Remote version manifest (multi-platform download URLs)
├── pyproject.toml       # Modern Python packaging (replaces setup.py)
├── install.sh / install.bat  # One-click install via uv (auto-installs Python 3.12)
├── requirements.txt
└── README.md
```

## Key Design Decisions
- **Inline HTML in web.py**: Legacy UI (`/v1`) has all HTML inline in a Python string. New UI uses separate static files.
- **Embedding model**: Default `BAAI/bge-small-zh-v1.5` (Chinese). Configurable in Settings. Cloud options: OpenAI, DashScope, Voyage AI.
- **Search pipeline**: 9-stage: expand → multi-path retrieve (semantic + keyword + filename + LIKE) → RRF fusion → time decay → dedup → rerank → recursive → directory priority → table hint
- **LIKE fallback search**: Handles jieba segmentation mismatches by searching with segmented terms, reversed bigrams, and spaced characters
- **Directory priority**: Files in `归档/40_归档` directories get 40% penalty, active directories get 20% boost.
- **Conversation persistence**: `~/.kbase/default/conversations.json` (messages + sources + search_mode)
- **Conversation titles**: `~/.kbase/default/conv_titles.json` (auto-generated via LLM, manually editable)
- **Global memory**: `~/.kbase/default/global_memories.json` (auto-extracted every 3 turns, injected into system prompt)
- **Settings storage**: `~/.kbase/default/settings.json` (includes API keys, base URLs, update_url, all model configs)
- **Artifact panel**: Long research reports displayed as Document cards (like Claude.ai), only for research mode
- **Source preview**: Hover shows chunk preview popup with keyword highlighting; click opens file
- **i18n**: Chinese/English full UI translation (sidebar, tabs, mode buttons, placeholders, date groups)
- **CLI wrapper naming**: `kbase-cli` (not `kbase`) to avoid conflict with the `kbase/` Python package directory
- **Model status API split**: `/api/model-status` returns all models (bulk), `/api/model-status/check?model_name=X` checks single model

## Search Architecture
1. **Query expansion**: 60+ Chinese business/tech synonyms (数用↔用数, 治理↔governance, etc.)
2. **Semantic search**: ChromaDB vector similarity (over-fetch 5x for later filtering)
3. **Keyword search**: FTS5 with jieba segmentation + raw query fallback + character bigrams
4. **Filename search**: LIKE on files table for file name matching
5. **LIKE fallback**: Handles jieba segmentation mismatches (reversed bigrams, spaced characters)
6. **RRF fusion**: Reciprocal Rank Fusion merging all retrieval paths
7. **Time decay**: Newer documents boosted (half-life 180 days)
8. **Dedup**: SequenceMatcher at 0.92 threshold
9. **Re-ranking**: Cross-encoder (BAAI/bge-reranker-v2-m3) on top candidates
10. **Directory priority**: Archive penalty, active directory boost

## LLM Providers (20)
### International
claude-sonnet, claude-haiku, gpt-4o, gpt-4o-mini, gemini-pro, gemini-flash, deepseek-chat, deepseek-reasoner
### China (国内)
qwen-plus, qwen-turbo, glm-4-flash, kimi-moonshot, doubao-pro, minimax, hunyuan, wenxin
### Local/CLI
ollama, claude-cli (`claude -p`), qwen-cli (`qwen -p`), llm-cli (`llm`), custom (OpenAI-compatible)

## Auto-Update System
- **`/api/version`**: Returns current version + install type (git/dmg/pip)
- **`/api/update/check`**: Checks remote `version.json` URL (configurable in Settings as `update_url`)
- **`/api/update/apply`**: For git installs: `git pull --ff-only` + `pip install -e .`
- **DMG installs**: Shows download link to new DMG from `version.json.download_url`
- **`version.json` format**: `{"version": "0.4.0", "download_url": "...", "download_url_mac": "...", "download_url_win": "...", "changelog": "..."}`
- **One-click update**: `/api/update/download` (SSE with progress) → `/api/update/install` (download DMG/ZIP, run updater script, restart)

## Distribution
- **Tauri desktop app** (primary): Native window (WKWebView/WebView2), system tray, ~4MB DMG
  - `kbase-desktop/` — Rust shell spawns Python sidecar, loads localhost in WebView
  - `npm run build` in kbase-desktop/ → `.app` + `.dmg` (macOS) / `.msi` + `.exe` (Windows)
- **PyPI**: `pip install kbase-app` or `uv tool install kbase-app`
  - Entry points: `kbase` (CLI), `kbase-desktop` (native window via pywebview)
- **uv installer** (recommended for new users): `bash install.sh`
  - Auto-installs uv → Python 3.12 → kbase-app (isolated venv, no system pollution)
- **Legacy PyInstaller**: `kbase.spec` / `kbase_win.spec` still available but not recommended
- **GitHub Actions CI**: Push `v*` tag → Tauri DMG/MSI + PyPI wheel → GitHub Releases

## UI Features (New)
- **Session management**: Auto-generated titles, sidebar date grouping (Today/Yesterday/7 Days/Older), timestamps
- **Progress indicator**: 4-step animated progress (search → retrieve → analyze → generate) with progress bar + timer
- **Artifact panel**: Research reports open in right-side panel with title, summary, section tags, Download .md
- **Source preview**: Hover popup with chunk text + keyword highlighting; unmatched refs fetched on-demand
- **API Key config**: Click provider → inline config panel with Show/Hide toggle, Base URL, Get Key links
- **Model status**: Local/Cloud badges on cards, download status detection for local models, Ollama install guide
- **Global memory**: View/add/delete in Settings; auto-extraction from conversations; injected into chat prompt
- **Ingest redesign**: Two-column layout, drag & drop upload, supported formats display, sync status
- **Error modal**: Click Errors count → popup showing all failed files with error details
- **Auto-update**: Settings panel with Update URL config, Check for Updates button, one-click apply (git) or download (DMG)
- **Animations**: Message fade-in, tab transitions, skeleton loading, save confirmation
- **i18n**: Full Chinese/English UI switching

## Known Issues / TODO
- **PDF page rendering**: Text-only preview, PDF page images not wired to new UI
- **Dark mode**: Some edge cases in embedded content
- **Feishu connector**: OAuth works but `im:message` scope needs admin approval for message content
- **Streaming chat**: Normal mode is single POST; could upgrade to SSE for real-time token streaming
- **Image recognition**: Not yet implemented (could use vision LLMs for image-heavy documents)
- **Deep Research quality**: Basic agent loop exists, not yet at Claude Research level
- **Full i18n**: Partially done, some strings still hardcoded

## Commands
```bash
kbase ingest /path/to/files    # Index files
kbase search "query"           # Enhanced search
kbase chat "question"          # Chat with LLM
kbase sql "SELECT ..."         # Query spreadsheet data
kbase open "query"             # Search & open file in Finder
kbase errors                   # Show failed files
kbase web                      # Start web UI at :8765
kbase web -p 9000              # Custom port
```

## API Endpoints
- `GET  /api/search?q=&type=auto|semantic|keyword&top_k=10`
- `GET  /api/sql?q=SELECT...`
- `POST /api/chat` (SSE streaming)
- `POST /api/ingest` (file upload or directory path)
- `GET  /api/settings` / `POST /api/settings`
- `GET  /api/model-status` (bulk check all local models)
- `GET  /api/model-status/check?model_name=X` (single model)
- `GET  /api/version` / `GET /api/update/check` / `POST /api/update/apply`
- `GET  /api/memories` / `POST /api/memories` / `DELETE /api/memories/{id}`
- `GET  /api/connectors` / `POST /api/connectors/{name}/sync`

## URLs
- New UI: http://localhost:8765/
- Legacy UI: http://localhost:8765/v1
- Feishu Guide: http://localhost:8765/api/connectors/feishu/guide
- API docs: http://localhost:8765/docs

## Storage
```
~/.kbase/default/
├── metadata.db          # SQLite (file index, FTS5 chunks, tabular data)
├── chroma/              # ChromaDB vector database
├── settings.json        # All settings (LLM provider, API keys, update_url, embedding model, etc.)
├── conversations.json   # Chat history with sources and search_mode
├── conv_titles.json     # Session titles (auto-generated + manual)
└── global_memories.json # Cross-conversation memory entries
```
