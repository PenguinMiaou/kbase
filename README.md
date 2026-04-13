# KBase - Local Knowledge Base

Turn any directory into a searchable, AI-powered knowledge base.

**Three engines**: Semantic search (RAG) + Full-text keyword search + SQL on spreadsheet data.
**Enhanced pipeline**: Query expansion + Re-ranking + Chinese segmentation + Directory priority + Time decay + Deduplication.

## Quick Start

```bash
# macOS / Linux
chmod +x install.sh && ./install.sh

# Windows
install.bat
```

Or manually:
```bash
cd kbase
pip install -e .
pip install jieba FlagEmbedding
kbase ingest /path/to/your/files
kbase web    # Open http://localhost:8765
```

## Supported Files

| Format | Processing |
|--------|-----------|
| `.pptx` | Slide-by-slide, tables, SmartArt |
| `.docx` | Paragraphs, headings, tables |
| `.xlsx` `.csv` | Text for search + SQLite tables for SQL |
| `.pdf` | Page-by-page with table extraction |
| `.md` `.txt` `.html` | Direct text |
| `.mp3` `.m4a` `.wav` `.mp4` | Speech-to-text (Whisper) |
| `.zip` `.tar` `.gz` `.7z` | Auto-extract and index contents |
| `.ppt` `.doc` `.xls` | Legacy format (best-effort) |

## CLI Commands

```bash
# Index files
kbase ingest /path/to/files           # Skip unchanged files
kbase ingest /path/to/files --force    # Re-index everything
kbase add /path/to/file.pptx          # Single file

# Search (enhanced: expand → retrieve → fuse → dedup → rerank)
kbase search "数据治理最新进展"
kbase search "CRM architecture" --type semantic
kbase search "凌总" --type keyword
kbase search "query" --no-rerank       # Disable re-ranking
kbase search "query" --no-expand       # Disable query expansion

# Chat with LLM
kbase chat "4月经分会数据治理做得如何"
kbase chat "summarize Q1 progress" --provider qwen-plus
kbase chat "question" --provider ollama

# SQL on spreadsheet data
kbase sql "SELECT * FROM table_name LIMIT 10"
kbase tables                           # List all tables

# File management
kbase files                            # List indexed files
kbase errors                           # Show failed files
kbase open "数据治理"                    # Search & open in Finder
kbase remove /path/to/file.xlsx        # Remove from index

# Other
kbase status                           # Stats
kbase watch /path/to/files             # Auto re-index on change
kbase web                              # Web UI at :8765
kbase web -p 9000                      # Custom port

# Workspaces (separate knowledge bases)
kbase -w team-a ingest /path/to/files
kbase -w team-a search "query"

# JSON output (for LLM/script consumption)
kbase -f json search "query"
kbase -f json chat "question"
```

## Web UI

`kbase web` → http://localhost:8765

| Tab | Features |
|-----|----------|
| **Chat** | Multi-turn conversation, memory, buddy personality, rewind, source file click-to-open |
| **Search** | Hybrid search with re-ranking, query expansion, results highlighting |
| **SQL** | Query spreadsheet data, click table names to auto-fill |
| **Files** | Browse indexed files, click to open in Finder/Explorer |
| **Ingest** | Directory browser, folder upload, real-time progress |
| **Settings** | LLM providers, embedding models, whisper models, chunk settings, language, theme |

### LLM Providers (19 total)

**International**: Claude Sonnet/Opus, GPT-4o/Mini, Gemini 2.5 Flash/Pro
**China**: DeepSeek, Qwen Plus/Max, GLM-4, Kimi, Doubao, Ernie, Hunyuan, MiniMax
**Local**: Ollama, Claude CLI, LLM CLI, Custom (any OpenAI-compatible API)

### Features
- Dark/Light theme toggle
- Chinese/English UI
- Click `[filename]` in AI answers to open file
- Rewind button on each AI response
- Directory priority: archive files rank lower
- Conversation history management
- Error details modal (click Errors stat card)

## Search Pipeline

```
Query → Expand (synonyms) → Multi-path Retrieve (vector + BM25 + expanded)
→ RRF Fusion → Time Decay → Dedup → Re-rank (cross-encoder) → Dir Priority
```

## For Teams

```bash
# Add anyone's files — just point to the directory
kbase ingest /path/to/colleague/files

# Separate workspace per team member
kbase -w colleague-name ingest /their/files

# Someone leaves? Dump everything in
kbase ingest /path/to/their/entire/folder
```

## Storage

`~/.kbase/<workspace>/` — metadata.db (SQLite), chroma/ (vectors), settings.json

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `KBASE_DIR` | Storage directory (default: `~/.kbase`) |
| `KBASE_EMBEDDING_MODEL` | Default embedding model |
| `ANTHROPIC_API_KEY` | Claude |
| `OPENAI_API_KEY` | GPT / OpenAI embeddings |
| `GEMINI_API_KEY` | Gemini |
| `DASHSCOPE_API_KEY` | Qwen (通义千问) |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `ZHIPU_API_KEY` | GLM (智谱) |
| `MOONSHOT_API_KEY` | Kimi |
| `ARK_API_KEY` | Doubao (豆包) |
