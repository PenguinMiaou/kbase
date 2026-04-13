<div align="center">

# KBase

**The local-first knowledge base that actually finds what you need.**

Turn any folder of documents into a searchable, AI-powered knowledge base.
No cloud upload. No vendor lock-in. Your data stays on your machine.

[Quick Start](#quick-start) | [Features](#features) | [Architecture](#architecture) | [CLI](#cli)

</div>

---

## Why KBase?

You have 300GB of work files across PPTX, PDF, DOCX, XLSX, emails, meeting notes. Finding anything means opening 20 folders and Ctrl+F-ing through each file.

KBase indexes everything once, then lets you **search across all files in one place** and **chat with your documents** using any LLM.

```
"Find the Q3 revenue numbers from that finance deck"
→ Found in 财务报告_2024Q3.xlsx (Sheet: Revenue, Row 42)

"What did the architecture team propose for the data platform?"
→ Sources: IT架构方案v3.pptx (Slide 14), 数据平台规划.docx (Section 2.3)
```

## Features

### Search That Actually Works

KBase doesn't just do keyword matching. It runs a **12-stage retrieval pipeline** that adapts based on query difficulty:

```
Query → Synonym Expand → [HyDE → Multi-Query]* → Semantic + Keyword + Filename
→ RRF Fusion → Time Decay → Dedup → Cross-Encoder Rerank → Parent Chunk Expand
→ Directory Priority → Table Hint Detection
                                          * only when needed (adaptive)
```

| Technique | What it does |
|-----------|-------------|
| **HyDE** | LLM generates a hypothetical answer, uses its embedding to search (matches documents better than short queries) |
| **Multi-Query** | LLM rewrites your query from different angles for broader recall |
| **Parent-Child Chunks** | Small chunks for precise matching, large chunks returned for richer context |
| **Semantic Chunking** | Splits by paragraphs/sentences, not arbitrary character count |
| **Cross-Encoder Rerank** | BAAI/bge-reranker-v2-m3 re-scores top results for precision |
| **Adaptive Escalation** | Simple queries stay fast (<1s). Complex queries get full pipeline (2-3s) |
| **Auto-Glossary** | Extracts domain terminology from your docs, expands searches automatically |

### 20+ LLM Providers

| International | China | Local |
|--------------|-------|-------|
| Claude Sonnet/Opus | Qwen Plus/Max | Ollama |
| GPT-4o / Mini | DeepSeek Chat/R1 | Claude CLI |
| Gemini 2.5 Flash/Pro | GLM-4 Flash | Qwen CLI |
| | Kimi / Doubao / MiniMax | LLM CLI |
| | Hunyuan / Wenxin | Custom (OpenAI-compatible) |

### Vision: See What's In Your Slides

KBase can extract images from PPTX and PDF, then describe them using Vision LLMs:

| Vision Model | Best For |
|-------------|----------|
| GPT-4o / GPT-4o Mini | General image understanding |
| Gemini 2.5 Flash | Fast, free tier available |
| Claude Sonnet | Charts, diagrams, org charts |
| Qwen-VL Plus | Chinese document images |
| GLM-4V Flash | Free Chinese vision |
| Ollama (minicpm-v) | Offline, local |

Architecture diagrams, flowcharts, org charts in your PPTs are no longer invisible to search.

### Multi-Engine Web Search

| Engine | Type | Needs Key |
|--------|------|-----------|
| DuckDuckGo | API | No |
| Brave | Scrape | No |
| Google (Serper) | API | Yes |
| Bing CN | Scrape | No |
| Sogou | Scrape | No |
| WeChat Articles | Scrape | No |

Auto-routes by language: Chinese queries hit Bing CN + DuckDuckGo, English queries hit Brave + DuckDuckGo.

### 4 Search Modes

| Mode | What it does |
|------|-------------|
| **Knowledge** | Search your local indexed files only |
| **Web** | Search the internet (multi-engine) |
| **Hybrid** | Local KB + Web combined |
| **Research** | Multi-round deep research with iterative search and synthesis (generates a full report) |

### File Support

| Format | Processing |
|--------|-----------|
| `.pptx` `.ppt` | Slide-by-slide text + tables + image extraction (Vision LLM) |
| `.docx` `.doc` | Paragraphs, headings, tables |
| `.xlsx` `.xls` `.csv` | Full-text search + SQL queries on structured data |
| `.pdf` | Page-by-page + image extraction (Vision LLM) |
| `.md` `.txt` `.html` | Direct text indexing |
| `.mp3` `.m4a` `.wav` `.mp4` | Speech-to-text (Whisper / DashScope / Gemini) |
| `.eml` `.mbox` | Email parsing with MIME header decoding |
| `.zip` `.tar` `.gz` `.7z` | Auto-extract and index contents |

### Claude-Inspired UI

- 3-column layout with artifact panel for research reports
- Session management with auto-generated titles
- 7 buddy presets with MBTI personalities (Professional, Buddy, Analyst, Tutor, Creative, Executive, Custom)
- Dark/Light theme + Chinese/English i18n
- Source preview popup with keyword highlighting
- Real-time ingest progress bar (SSE streaming)
- Cross-tab sync (BroadcastChannel)
- Global memory system (auto-extracts key facts from conversations)
- Drag & drop file upload

## Quick Start

### macOS (DMG)

Download `KBase-0.3.0.dmg` from [Releases](https://github.com/PenguinMiaou/kbase/releases) → Drag to Applications → Open.

### From Source

```bash
git clone https://github.com/PenguinMiaou/kbase.git
cd kbase
bash install.sh          # Creates venv, installs deps, creates kbase-cli wrapper

./kbase-cli ingest ~/Documents/work    # Index your files
./kbase-cli web                        # Open http://localhost:8765
```

### pip

```bash
pip install -e .
pip install jieba
kbase ingest /path/to/files
kbase web
```

## CLI

```bash
kbase ingest /path/to/files           # Index (skips unchanged files)
kbase ingest /path --force            # Force re-index everything
kbase search "query"                  # Hybrid search (adaptive pipeline)
kbase chat "question"                 # Chat with LLM + KB context
kbase sql "SELECT * FROM table"       # Query spreadsheet data
kbase tables                          # List SQL-queryable tables
kbase open "query"                    # Search & open file in Finder
kbase files                           # List indexed files
kbase errors                          # Show failed files
kbase watch /path                     # Auto re-index on file changes
kbase web                             # Start web UI at :8765
kbase web -p 9000                     # Custom port
kbase -w team-a search "query"        # Separate workspace
kbase -f json search "query"          # JSON output for scripts
```

## Architecture

```
kbase/
├── web.py           # FastAPI server + all API endpoints
├── chat.py          # 20 LLM providers + buddy presets + memory
├── store.py         # ChromaDB (vectors) + SQLite FTS5 (keyword) + tabular
├── search.py        # 12-stage adaptive pipeline
├── enhance.py       # HyDE, multi-query, reranking, glossary, query expansion
├── vision.py        # Vision LLM image description (8 models)
├── extract.py       # File extractors (PPTX/PDF/DOCX/XLSX/audio/email/archive)
├── chunk.py         # Semantic chunking + parent-child hierarchy
├── ingest.py        # Ingestion pipeline with resume-from-checkpoint
├── websearch.py     # 6-engine web search with language routing
├── agent_loop.py    # Deep research agent (multi-round)
├── config.py        # Models config (embedding/whisper/vision/language)
├── connectors/      # Feishu/Lark integration
└── static/          # Claude-style frontend (HTML/CSS/JS)
```

### Storage

```
~/.kbase/default/
├── metadata.db          # SQLite: file index, FTS5 chunks, tabular data
├── chroma/              # ChromaDB vector database
├── settings.json        # All settings (models, API keys, preferences)
├── conversations.json   # Chat history with sources
├── conv_titles.json     # Auto-generated session titles
├── global_memories.json # Cross-conversation memory
└── glossary.json        # Auto-extracted domain terminology
```

## Scalability

Tested with 300GB+ document collections:
- SQLite indexes on all lookup columns
- Large file guard (>200MB skip)
- Deep directory support (15 levels)
- Incremental ingest = natural resume-from-checkpoint
- Adaptive search: simple queries stay fast, complex queries escalate

## Auto-Update

KBase checks for updates from a configurable URL (default: this repo's `version.json`).
Settings → Update → Check for Updates.

For source installs: one-click `git pull` + pip install.
For DMG installs: download link to latest release.

## Contributing

```bash
git clone https://github.com/PenguinMiaou/kbase.git
cd kbase && pip install -e .
python -m kbase.web     # Dev server at :8765
```

## License

Copyright@PenguinMiaou. All rights reserved.
