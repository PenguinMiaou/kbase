<div align="center">

# KBase

**The local-first knowledge base that actually finds what you need.**

Turn any folder of documents into a searchable, AI-powered knowledge base.
No cloud upload. No vendor lock-in. Your data stays on your machine.

[Quick Start](#quick-start) | [Features](#features) | [Knowledge Graph](#knowledge-graph) | [Architecture](#architecture) | [CLI](#cli) | [中文](README_zh.md)

</div>

---

## Why KBase?

You have 300GB of work files across PPTX, PDF, DOCX, XLSX, emails, meeting notes. Finding anything means opening 20 folders and Ctrl+F-ing through each file.

KBase indexes everything once, then lets you **search across all files in one place** and **chat with your documents** using any LLM.

```
"Find the Q3 revenue numbers from that finance deck"
-> Found in Revenue_Report_2024Q3.xlsx (Sheet: Revenue, Row 42)

"What did the architecture team propose for the data platform?"
-> Sources: IT_Architecture_v3.pptx (Slide 14), Data_Platform_Plan.docx (Section 2.3)
```

## Features

### 13-Stage Adaptive Search Pipeline

KBase doesn't just do keyword matching. It runs a **13-stage retrieval pipeline** that adapts based on query difficulty:

```
Query -> Synonym Expand -> [HyDE -> Multi-Query]* -> Semantic + Keyword + Filename
-> RRF Fusion -> Time Decay -> Dedup -> Cross-Encoder Rerank -> Parent Chunk Expand
-> Directory Priority -> Graph Boost -> Table Hint Detection
                                          * only when needed (adaptive)
```

| Technique | What it does |
|-----------|-------------|
| **HyDE** | LLM generates a hypothetical answer, uses its embedding to search (matches documents better than short queries) |
| **Multi-Query** | LLM rewrites your query from different angles for broader recall |
| **Parent-Child Chunks** | Small chunks for precise matching, large chunks returned for richer context |
| **Semantic Chunking** | Splits by paragraphs/sentences (Chinese-aware), not arbitrary character count |
| **Cross-Encoder Rerank** | BAAI/bge-reranker-v2-m3 re-scores top results for precision |
| **Adaptive Escalation** | Simple queries stay fast (<1s). Complex queries get full pipeline (2-3s) |
| **Auto-Glossary** | Extracts domain terminology from your docs, expands searches automatically |
| **Graph Boost** | Manually confirmed document relationships boost search ranking |

### Knowledge Graph

Obsidian-style graph visualization with **Graph + Canvas dual mode**:

- **Graph Mode** -- Force-directed layout (Cytoscape.js + fcose), auto-computed relationships via semantic similarity
- **Canvas Mode** -- Drag-to-pin whiteboard, manually draw edges between documents
- **Three-layer edges**: Auto (dashed, low opacity) / Confirmed (solid) / Labeled (solid + arrow + label)
- Hover to highlight neighborhood, double-click for local graph (2-hop subgraph)
- Right-click menus for nodes (open file, view local graph, pin) and edges (confirm, label, delete)
- Search filter: type keyword to highlight matching nodes, dim the rest
- Dark/Light theme matching Obsidian's aesthetic

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

### 5 Search Modes

| Mode | What it does |
|------|-------------|
| **Direct** | Pure LLM chat with global memory, no search |
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
| `.rar` | RAR archive extraction (rarfile pure-Python) |

### Claude-Inspired UI

- 3-column layout with artifact panel for research reports
- Session management with auto-generated titles
- 7 buddy presets with MBTI personalities (Professional, Buddy, Analyst, Tutor, Creative, Executive, Custom)
- Dark/Light theme + Chinese/English i18n
- Source preview popup with keyword highlighting
- Real-time ingest progress bar (SSE streaming) with pause/stop/resume
- Cross-tab sync (BroadcastChannel)
- Global memory system (auto-extracts key facts from conversations)
- Drag & drop file upload
- Knowledge Graph tab with Graph/Canvas dual mode

## Quick Start

### macOS (DMG)

Download `KBase-0.5.0.dmg` from [Releases](https://github.com/PenguinMiaou/kbase/releases) -> Drag to Applications -> Open.

### Windows (EXE)

Download `KBase-0.5.0-Windows.zip` from [Releases](https://github.com/PenguinMiaou/kbase/releases) -> Extract -> Run `KBase.exe`.

### From Source

```bash
git clone https://github.com/PenguinMiaou/kbase.git
cd kbase
bash install.sh          # macOS/Linux: creates venv + kbase-cli wrapper
# or
install.bat              # Windows: creates venv + kbase.bat wrapper

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
├── store.py         # ChromaDB (vectors) + SQLite FTS5 (keyword) + tabular + graph tables
├── search.py        # 13-stage adaptive pipeline (+ graph boost)
├── graph.py         # Knowledge graph computation + edge management
├── enhance.py       # HyDE, multi-query, reranking, glossary, query expansion
├── vision.py        # Vision LLM image description (8 models)
├── extract.py       # File extractors (PPTX/PDF/DOCX/XLSX/audio/email/archive/RAR)
├── chunk.py         # Semantic chunking + parent-child hierarchy
├── ingest.py        # Ingestion pipeline with pause/stop/resume
├── websearch.py     # 6-engine web search with language routing
├── agent_loop.py    # Deep research agent (multi-round)
├── config.py        # Models config (embedding/whisper/vision/language)
├── connectors/      # Feishu/Lark integration
└── static/          # Claude-style frontend (HTML/CSS/JS + Cytoscape.js graph)
```

### Storage

```
~/.kbase/default/
├── metadata.db          # SQLite: file index, FTS5 chunks, tabular data, graph edges
├── chroma/              # ChromaDB vector database
├── settings.json        # All settings (models, API keys, preferences)
├── conversations.json   # Chat history with sources
├── conv_titles.json     # Auto-generated session titles
├── global_memories.json # Cross-conversation memory
└── glossary.json        # Auto-extracted domain terminology
```

## Scalability

Tested with 300GB+ document collections (800+ files, 26K+ chunks):
- SQLite indexes on all lookup columns
- Large file support (up to 500MB per file)
- Deep directory support (15 levels)
- Incremental ingest with pause/stop/resume
- Adaptive search: simple queries stay fast, complex queries escalate
- Per-file result aggregation (max 3 chunks/file for diversity)

## Auto-Update

KBase checks for updates from a configurable URL (default: this repo's `version.json`).

- **Source installs**: One-click `git pull` + pip install from Settings
- **DMG/EXE installs**: One-click download + auto-install + restart from Settings
- **GitHub Actions CI**: Push a `v*` tag to auto-build DMG + Windows EXE

## Feedback

Found a bug? Have a feature request?
- [Open an Issue](https://github.com/PenguinMiaou/kbase/issues)
- Settings -> Feedback -> Report an Issue

## Contributing

```bash
git clone https://github.com/PenguinMiaou/kbase.git
cd kbase && pip install -e .
python -m kbase.cli web    # Dev server at :8765
```

## License

[MIT License](LICENSE) - use it however you want.
