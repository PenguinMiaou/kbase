"""Storage layer: ChromaDB (vector) + SQLite (FTS + tabular + metadata)."""
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional


import chromadb
from chromadb.utils import embedding_functions

from kbase.config import (
    get_chroma_path, get_db_path, get_workspace_dir,
    load_settings, EMBEDDING_MODELS, DEFAULT_EMBEDDING_MODEL,
)


def _create_embedding_function(model_key: str = None):
    """Create embedding function based on model key."""
    import sys
    model_key = model_key or DEFAULT_EMBEDDING_MODEL
    model_info = EMBEDDING_MODELS.get(model_key)

    if not model_info:
        # Fallback: treat as direct sentence-transformer model name
        return _safe_sentence_transformer(model_key)

    if model_info["type"] == "local":
        return _safe_sentence_transformer(model_info["name"])
    elif model_info["type"] == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set. Export it or use a local model.")
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name=model_info["name"],
        )
    elif model_info["type"] == "voyageai":
        api_key = os.environ.get("VOYAGE_API_KEY", "")
        if not api_key:
            raise ValueError("VOYAGE_API_KEY not set.")
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name=model_info["name"],
            api_base="https://api.voyageai.com/v1/",
        )
    elif model_info["type"] == "dashscope":
        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        settings = {}
        try:
            from kbase.config import load_settings
            settings = load_settings()
        except Exception:
            pass
        api_key = api_key or settings.get("dashscope_api_key", "")
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY not set. Configure in Settings.")
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name=model_info["name"],
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1/",
        )
    else:
        return _safe_sentence_transformer(model_info["name"])


def _safe_sentence_transformer(model_name: str):
    """Try SentenceTransformer, fallback to ChromaDB default + trigger background install."""
    try:
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name
        )
    except Exception as e:
        import sys
        if getattr(sys, 'frozen', False):
            # In DMG mode: use ChromaDB default now, install proper model in background
            print(f"[KBase] SentenceTransformer failed ({e}), using ChromaDB default embedding")
            _background_install_st(model_name)
            return embedding_functions.DefaultEmbeddingFunction()
        raise


_bg_install_started = False


def _background_install_st(model_name: str):
    """Background download embedding model (on first launch)."""
    global _bg_install_started
    if _bg_install_started:
        return
    _bg_install_started = True

    import threading
    def do_install():
        try:
            print(f"[KBase] Downloading model {model_name} ...")
            from sentence_transformers import SentenceTransformer
            SentenceTransformer(model_name)
            print(f"[KBase] Model ready! Restart KBase to use it.")
        except Exception as e:
            print(f"[KBase] Model download failed: {e}")

    threading.Thread(target=do_install, daemon=True).start()


class KBaseStore:
    """Unified store wrapping vector, FTS, tabular, and metadata storage."""

    def __init__(self, workspace: str = "default", embedding_model: str = None):
        self.workspace = workspace
        ws_dir = get_workspace_dir(workspace)
        ws_dir.mkdir(parents=True, exist_ok=True)

        # Load settings
        settings = load_settings(workspace)
        self.embedding_model = embedding_model or settings.get("embedding_model", DEFAULT_EMBEDDING_MODEL)

        # SQLite for metadata + FTS + tabular
        self.db_path = get_db_path(workspace)
        self.conn = sqlite3.connect(str(self.db_path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        # Enable WAL mode: allows concurrent reads during writes (critical for ingest + UI)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_sqlite()

        # ChromaDB for vector search
        chroma_path = get_chroma_path(workspace)
        chroma_path.mkdir(parents=True, exist_ok=True)

        self.ef = _create_embedding_function(self.embedding_model)

        # Pre-flight: check dimension mismatch BEFORE opening ChromaDB client
        # This must happen first because ChromaDB's Rust backend locks the file
        self._preflight_dimension_check(chroma_path)

        self.chroma_client = chromadb.PersistentClient(path=str(chroma_path))
        try:
            self.collection = self.chroma_client.get_or_create_collection(
                name="documents",
                embedding_function=self.ef,
                metadata={"hnsw:space": "cosine"},
            )
        except (ValueError, Exception) as e:
            # Embedding function conflict — delete and recreate collection
            if "conflict" in str(e).lower() or "embedding" in str(e).lower():
                print(f"[KBase] ChromaDB embedding conflict, rebuilding: {e}")
                try:
                    self.chroma_client.delete_collection("documents")
                except Exception:
                    pass
                self.collection = self.chroma_client.get_or_create_collection(
                    name="documents",
                    embedding_function=self.ef,
                    metadata={"hnsw:space": "cosine"},
                )
            else:
                raise

    def _preflight_dimension_check(self, chroma_path):
        """Pre-flight check: detect dimension mismatch BEFORE creating ChromaDB client.

        Reads the chroma.sqlite3 schema directly (no Rust client needed).
        If mismatch found, wipes the entire chroma directory so a fresh
        client + collection can be created with the correct dimension.
        """
        import shutil
        chroma_db = Path(chroma_path) / "chroma.sqlite3"
        if not chroma_db.exists():
            return

        try:
            _conn = sqlite3.connect(str(chroma_db))
            row = _conn.execute("SELECT dimension FROM collections WHERE name = 'documents'").fetchone()
            _conn.close()

            if not row or not row[0]:
                return
            stored_dim = row[0]

            # Get expected dimension
            model_info = EMBEDDING_MODELS.get(self.embedding_model, {})
            expected_dim = model_info.get("dim", 0)
            if expected_dim == 0:
                try:
                    test_emb = self.ef(["test"])
                    if test_emb and len(test_emb) > 0:
                        expected_dim = len(test_emb[0])
                except Exception:
                    return

            if expected_dim > 0 and stored_dim != expected_dim:
                print(f"[KBase] Embedding dimension mismatch: {stored_dim}d → {expected_dim}d "
                      f"(model: {self.embedding_model}). Wiping ChromaDB...")
                # Wipe entire chroma directory BEFORE any client opens it
                for item in Path(chroma_path).iterdir():
                    if item.name == "__pycache__":
                        continue
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                # Reset chunk counts
                c = self.conn.cursor()
                c.execute("UPDATE files SET chunk_count = 0")
                self.conn.commit()
                print(f"[KBase] ChromaDB wiped. Will rebuild with {expected_dim}d embeddings.")
        except Exception as e:
            print(f"[KBase] Dimension pre-flight check skipped: {e}")

    def rebuild_chromadb(self, new_model: str = None):
        """Clear ChromaDB and recreate collection for new embedding model.

        Preserves FTS5 keyword data — only vector embeddings are cleared.
        Files remain indexed; re-sync directories to rebuild embeddings.
        """
        if new_model:
            self.embedding_model = new_model
            self.ef = _create_embedding_function(new_model)

        # Must fully reset ChromaDB: delete collection + wipe persistent storage
        # to clear dimension constraints baked into collection schema
        try:
            self.chroma_client.delete_collection("documents")
        except Exception:
            pass

        # Remove stale HNSW segment directories that retain old dimension config
        import shutil
        chroma_path = get_chroma_path(self.workspace)
        for item in chroma_path.iterdir():
            if item.is_dir() and item.name != "__pycache__":
                shutil.rmtree(item, ignore_errors=True)
        # Also clear the chroma sqlite to remove stale segment references
        chroma_sqlite = chroma_path / "chroma.sqlite3"
        if chroma_sqlite.exists():
            chroma_sqlite.unlink()

        # Recreate client and collection from scratch
        self.chroma_client = chromadb.PersistentClient(path=str(chroma_path))
        self.collection = self.chroma_client.get_or_create_collection(
            name="documents",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )

        # Reset chunk counts so re-ingest knows to rebuild
        c = self.conn.cursor()
        c.execute("UPDATE files SET chunk_count = 0")
        self.conn.commit()
        print(f"[KBase] ChromaDB fully rebuilt for {self.embedding_model}. Re-sync to rebuild embeddings.")

    def _init_sqlite(self):
        c = self.conn.cursor()
        # File metadata
        c.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY,
                file_path TEXT UNIQUE,
                file_name TEXT,
                file_type TEXT,
                file_size INTEGER,
                modified_time REAL,
                indexed_time REAL,
                chunk_count INTEGER DEFAULT 0,
                title TEXT,
                source_dir TEXT,
                error TEXT,
                summary TEXT DEFAULT ''
            )
        """)
        # Migration: add summary column if missing (existing DBs)
        try:
            c.execute("SELECT summary FROM files LIMIT 1")
        except Exception:
            try:
                c.execute("ALTER TABLE files ADD COLUMN summary TEXT DEFAULT ''")
            except Exception:
                pass
        # FTS5 for full-text keyword search
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
                chunk_id, file_id, file_name, file_path, text
            )
        """)
        # Registry of tabular data tables
        c.execute("""
            CREATE TABLE IF NOT EXISTS tabular_registry (
                table_name TEXT PRIMARY KEY,
                file_id TEXT,
                file_path TEXT,
                sheet_name TEXT,
                headers TEXT,
                row_count INTEGER,
                FOREIGN KEY (file_id) REFERENCES files(file_id)
            )
        """)
        # Performance indexes for large datasets (300GB+ / 100K+ files)
        c.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(file_path)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_files_source_dir ON files(source_dir)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_files_type ON files(file_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_files_name ON files(file_name)")

        # Knowledge graph: document relationships
        c.execute("""
            CREATE TABLE IF NOT EXISTS document_edges (
                edge_id TEXT PRIMARY KEY,
                source_file_id TEXT NOT NULL,
                target_file_id TEXT NOT NULL,
                edge_type TEXT DEFAULT 'auto',
                label TEXT DEFAULT '',
                direction TEXT DEFAULT 'none',
                score REAL DEFAULT 0.0,
                method TEXT DEFAULT 'semantic',
                created_at REAL,
                updated_at REAL,
                FOREIGN KEY (source_file_id) REFERENCES files(file_id),
                FOREIGN KEY (target_file_id) REFERENCES files(file_id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON document_edges(source_file_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON document_edges(target_file_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON document_edges(edge_type)")

        # Knowledge graph: node positions for canvas/whiteboard mode
        c.execute("""
            CREATE TABLE IF NOT EXISTS graph_node_positions (
                file_id TEXT PRIMARY KEY,
                x REAL NOT NULL DEFAULT 0,
                y REAL NOT NULL DEFAULT 0,
                pinned INTEGER DEFAULT 0,
                color_group TEXT DEFAULT '',
                updated_at REAL,
                FOREIGN KEY (file_id) REFERENCES files(file_id)
            )
        """)

        # User interest tracking (lightweight, no LLM needed)
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_interests (
                term TEXT PRIMARY KEY,
                frequency INTEGER DEFAULT 1,
                last_queried REAL,
                first_queried REAL
            )
        """)

        # Search feedback / click tracking (harness sensor)
        c.execute("""
            CREATE TABLE IF NOT EXISTS search_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                file_id TEXT,
                file_name TEXT,
                position INTEGER DEFAULT 0,
                action TEXT DEFAULT 'click',
                timestamp REAL,
                FOREIGN KEY (file_id) REFERENCES files(file_id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_feedback_file ON search_feedback(file_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_feedback_query ON search_feedback(query)")

        self.conn.commit()

    def file_id(self, file_path: str) -> str:
        return hashlib.md5(file_path.encode()).hexdigest()

    def is_indexed(self, file_path: str) -> bool:
        """Check if file is already indexed and up-to-date.
        Files with errors are NOT considered indexed (will be retried)."""
        fid = self.file_id(file_path)
        c = self.conn.cursor()
        c.execute("SELECT modified_time, error FROM files WHERE file_id = ?", (fid,))
        row = c.fetchone()
        if not row:
            return False
        # If previous attempt had error, retry
        if row["error"]:
            return False
        try:
            current_mtime = Path(file_path).stat().st_mtime
            return row["modified_time"] >= current_mtime
        except FileNotFoundError:
            return False

    def index_document(self, file_path: str, text: str, chunks: list[dict],
                       tables: list[dict], metadata: dict, summary: str = "",
                       chunk_progress_cb=None):
        """Index a document: vector + FTS + tabular."""
        fid = self.file_id(file_path)
        p = Path(file_path)

        # Remove old data first
        self._remove_document(fid)

        # Store file metadata
        c = self.conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO files
            (file_id, file_path, file_name, file_type, file_size, modified_time,
             indexed_time, chunk_count, title, source_dir, error, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fid, str(p), p.name, p.suffix.lower(),
            metadata.get("file_size", 0),
            p.stat().st_mtime if p.exists() else 0,
            time.time(),
            len(chunks),
            metadata.get("title", p.stem),
            str(p.parent),
            metadata.get("error", ""),
            summary,
        ))

        # Index chunks in ChromaDB + FTS
        if chunks:
            chunk_ids = []
            chunk_texts = []
            chunk_metas = []

            for i, chunk in enumerate(chunks):
                cid = f"{fid}_{i}"
                chunk_ids.append(cid)
                chunk_texts.append(chunk["text"])
                # ChromaDB metadata must be flat str/int/float
                meta = {
                    "file_id": fid,
                    "file_path": str(p),
                    "file_name": p.name,
                    "file_type": p.suffix.lower(),
                    "chunk_index": i,
                    "title": metadata.get("title", p.stem),
                }
                for k, v in chunk.get("metadata", {}).items():
                    if isinstance(v, (str, int, float, bool)):
                        meta[k] = v
                chunk_metas.append(meta)

                # FTS - use segmented text if available for better Chinese matching
                fts_text = chunk.get("text_segmented", chunk["text"])
                c.execute(
                    "INSERT INTO fts_chunks(chunk_id, file_id, file_name, file_path, text) VALUES (?, ?, ?, ?, ?)",
                    (cid, fid, p.name, str(p), fts_text),
                )

            # Batch add to ChromaDB (embedding happens here — slowest step)
            batch_size = 50
            total_chunks = len(chunk_ids)
            for start in range(0, total_chunks, batch_size):
                end = start + batch_size
                self.collection.add(
                    ids=chunk_ids[start:end],
                    documents=chunk_texts[start:end],
                    metadatas=chunk_metas[start:end],
                )
                if chunk_progress_cb:
                    chunk_progress_cb(min(end, total_chunks), total_chunks)

        # Index tables in SQLite
        for table_data in tables:
            self._store_table(fid, file_path, table_data)

        self.conn.commit()

    def _store_table(self, file_id: str, file_path: str, table_data: dict):
        """Store structured table data in SQLite for Text2SQL."""
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])
        source = table_data.get("source", "table")
        fname = table_data.get("file_name", Path(file_path).stem)

        if not headers or not rows:
            return

        # Create safe table name
        safe_name = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "_", f"t_{fname}_{source}")
        safe_name = safe_name[:60]

        # Create sanitized column names
        columns = []
        for h in headers:
            col = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "_", h) or f"col_{len(columns)}"
            if col[0].isdigit():
                col = "c_" + col
            columns.append(col)

        # Deduplicate column names
        seen = {}
        for i, col in enumerate(columns):
            if col in seen:
                seen[col] += 1
                columns[i] = f"{col}_{seen[col]}"
            else:
                seen[col] = 0

        c = self.conn.cursor()

        # Drop existing table
        c.execute(f'DROP TABLE IF EXISTS "{safe_name}"')

        # Create table
        cols_def = ", ".join(f'"{col}" TEXT' for col in columns)
        c.execute(f'CREATE TABLE "{safe_name}" ({cols_def})')

        # Insert data
        placeholders = ", ".join(["?"] * len(columns))
        for row in rows:
            padded = row + [""] * (len(columns) - len(row))
            c.execute(f'INSERT INTO "{safe_name}" VALUES ({placeholders})', padded[:len(columns)])

        # Register
        c.execute("""
            INSERT OR REPLACE INTO tabular_registry
            (table_name, file_id, file_path, sheet_name, headers, row_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (safe_name, file_id, file_path, source, json.dumps(headers, ensure_ascii=False), len(rows)))

    def _remove_document(self, file_id: str):
        """Remove all data for a document."""
        c = self.conn.cursor()

        # Remove from FTS
        c.execute("DELETE FROM fts_chunks WHERE file_id = ?", (file_id,))

        # Remove tabular tables
        c.execute("SELECT table_name FROM tabular_registry WHERE file_id = ?", (file_id,))
        for row in c.fetchall():
            c.execute(f'DROP TABLE IF EXISTS "{row["table_name"]}"')
        c.execute("DELETE FROM tabular_registry WHERE file_id = ?", (file_id,))

        # Remove from ChromaDB (try both where filter and id prefix)
        try:
            existing = self.collection.get(where={"file_id": file_id})
            if existing["ids"]:
                self.collection.delete(ids=existing["ids"])
        except Exception:
            pass
        # Fallback: delete by ID prefix (file_id_chunkindex)
        try:
            all_data = self.collection.get()
            orphan_ids = [aid for aid, meta in zip(all_data["ids"], all_data["metadatas"])
                          if meta.get("file_id") == file_id]
            if orphan_ids:
                self.collection.delete(ids=orphan_ids)
        except Exception:
            pass

        # Remove file record
        c.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
        self.conn.commit()

    def remove_file(self, file_path: str):
        """Remove a file from the index."""
        fid = self.file_id(file_path)
        self._remove_document(fid)

    def get_file_summary(self, file_id: str) -> str:
        """Get the LLM-generated summary for a file."""
        c = self.conn.cursor()
        c.execute("SELECT summary FROM files WHERE file_id = ?", (file_id,))
        row = c.fetchone()
        return row["summary"] if row and row["summary"] else ""

    def update_file_summary(self, file_id: str, summary: str):
        """Update the LLM-generated summary for a file."""
        c = self.conn.cursor()
        c.execute("UPDATE files SET summary = ? WHERE file_id = ?", (summary, file_id))
        self.conn.commit()

    def get_files_without_summary(self, limit: int = 50) -> list[dict]:
        """Get files that don't have a summary yet."""
        c = self.conn.cursor()
        c.execute("""
            SELECT file_id, file_path, file_name, file_type
            FROM files
            WHERE (summary IS NULL OR summary = '') AND (error IS NULL OR error = '')
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in c.fetchall()]

    # ---- User Interest Tracking (lightweight memory, no LLM) ----

    def record_query_interests(self, query: str):
        """Extract and record key terms from user query (no LLM needed)."""
        import jieba
        now = time.time()
        # Segment query and filter short/stop words
        stop_words = {"的", "了", "是", "在", "和", "有", "与", "对", "到", "为",
                      "把", "被", "让", "给", "从", "能", "会", "要", "可以", "什么",
                      "哪些", "怎么", "如何", "多少", "哪个", "这个", "那个", "一个",
                      "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
                      "to", "for", "of", "with", "and", "or", "not", "what", "how",
                      "which", "where", "when", "who", "why", "do", "does", "did"}
        terms = [w.strip() for w in jieba.cut(query) if len(w.strip()) >= 2 and w.strip().lower() not in stop_words]
        if not terms:
            return
        c = self.conn.cursor()
        for term in terms[:10]:  # Cap at 10 terms per query
            c.execute("""
                INSERT INTO user_interests (term, frequency, last_queried, first_queried)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(term) DO UPDATE SET
                    frequency = frequency + 1,
                    last_queried = ?
            """, (term, now, now, now))
        self.conn.commit()

    def get_top_interests(self, limit: int = 20) -> list[dict]:
        """Get user's most frequent query terms."""
        c = self.conn.cursor()
        c.execute("""
            SELECT term, frequency, last_queried
            FROM user_interests
            ORDER BY frequency DESC, last_queried DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in c.fetchall()]

    # ---- Search Feedback (harness sensor) ----

    def record_click(self, query: str, file_id: str, file_name: str, position: int):
        """Record when user clicks a search result."""
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO search_feedback (query, file_id, file_name, position, action, timestamp)
            VALUES (?, ?, ?, ?, 'click', ?)
        """, (query, file_id, file_name, position, time.time()))
        self.conn.commit()

    def record_feedback(self, query: str, file_id: str, action: str):
        """Record thumbs up/down on an answer."""
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO search_feedback (query, file_id, action, timestamp)
            VALUES (?, ?, ?, ?)
        """, (query, file_id, action, time.time()))
        self.conn.commit()

    def get_click_scores(self, file_ids: list[str]) -> dict[str, float]:
        """Get click frequency scores for a set of files (for search boost)."""
        if not file_ids:
            return {}
        c = self.conn.cursor()
        placeholders = ",".join("?" for _ in file_ids)
        c.execute(f"""
            SELECT file_id, COUNT(*) as clicks
            FROM search_feedback
            WHERE file_id IN ({placeholders}) AND action = 'click'
            GROUP BY file_id
        """, file_ids)
        max_clicks = 1
        scores = {}
        for row in c.fetchall():
            scores[row["file_id"]] = row["clicks"]
            max_clicks = max(max_clicks, row["clicks"])
        # Normalize to 0-1
        return {fid: count / max_clicks for fid, count in scores.items()}

    def get_disabled_dirs(self) -> list[str]:
        """Get list of disabled directory paths from settings (always fresh, no cache)."""
        try:
            settings = load_settings(self.workspace)
            dirs = settings.get("ingest_dirs", {})
            if not isinstance(dirs, dict):
                return []
            return [p.rstrip("/").rstrip(os.sep) for p, info in dirs.items()
                    if isinstance(info, dict) and not info.get("enabled", True)]
        except Exception:
            return []

    def _is_path_disabled(self, file_path: str) -> bool:
        """Check if a file path belongs to a disabled directory."""
        disabled = self.get_disabled_dirs()
        if not disabled:
            return False
        return any(file_path.startswith(d + "/") for d in disabled)

    def _sql_disabled_filter(self, column: str = "source_dir") -> tuple:
        """Return (SQL AND clause, params) to exclude disabled dirs."""
        disabled = self.get_disabled_dirs()
        if not disabled:
            return ("", [])
        clauses = " AND ".join(f"{column} NOT LIKE ?" for _ in disabled)
        params = [d + "%" for d in disabled]
        return (f" AND ({clauses})", params)

    # ---- Search methods ----

    def semantic_search(self, query: str, top_k: int = 10, file_type: str = None) -> list[dict]:
        """Vector similarity search."""
        where = {"file_type": file_type} if file_type else None
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )

        items = []
        for i in range(len(results["ids"][0])):
            items.append({
                "chunk_id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "score": 1 - results["distances"][0][i],  # cosine similarity
                "metadata": results["metadatas"][0][i],
                "method": "semantic",
            })
        # Filter out files from disabled directories
        items = [r for r in items if not self._is_path_disabled(r.get("metadata", {}).get("file_path", ""))]
        return items

    def keyword_search(self, query: str, top_k: int = 10) -> list[dict]:
        """Full-text keyword search using SQLite FTS5."""
        # Escape FTS5 special characters
        safe_query = re.sub(r'["\'\-*()]', " ", query).strip()
        if not safe_query:
            return []

        # Use OR for better recall with Chinese
        terms = [t for t in safe_query.split() if t and len(t) >= 1]
        # Also add character bigrams for Chinese (catches partial matches)
        bigrams = []
        for t in terms:
            if len(t) >= 4 and any('\u4e00' <= c <= '\u9fff' for c in t):
                for i in range(len(t) - 1):
                    bg = t[i:i+2]
                    if any('\u4e00' <= c <= '\u9fff' for c in bg):
                        bigrams.append(bg)
        all_terms = terms + bigrams[:10]  # Cap bigrams to avoid too many
        fts_query = " OR ".join(f'"{t}"' for t in all_terms if t)

        c = self.conn.cursor()
        try:
            c.execute("""
                SELECT chunk_id, file_id, file_name, file_path, text,
                       rank as score
                FROM fts_chunks
                WHERE fts_chunks MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, top_k))

            items = []
            for row in c.fetchall():
                items.append({
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "score": -row["score"],  # FTS5 rank is negative, lower is better
                    "metadata": {
                        "file_id": row["file_id"],
                        "file_name": row["file_name"],
                        "file_path": row["file_path"],
                    },
                    "method": "keyword",
                })
            # Filter out files from disabled directories
            items = [r for r in items if not self._is_path_disabled(r.get("metadata", {}).get("file_path", ""))]
            return items
        except sqlite3.OperationalError:
            return []

    def filename_search(self, query: str, top_k: int = 10) -> list:
        """Search by file name matching + LIKE text fallback for when FTS5 segmentation misses."""
        c = self.conn.cursor()
        items = []
        seen_files = set()
        try:
            # 1. Search files table by name
            terms = [t.strip() for t in query.split() if len(t.strip()) >= 2]
            if not terms:
                terms = [query.strip()]
            for term in terms:
                c.execute("""
                    SELECT file_path, file_name FROM files
                    WHERE file_name LIKE '%' || ? || '%'
                    LIMIT ?
                """, (term, top_k))
                for row in c.fetchall():
                    fpath = row["file_path"]
                    if fpath in seen_files or self._is_path_disabled(fpath):
                        continue
                    seen_files.add(fpath)
                    # Get first chunk of this file
                    c2 = self.conn.cursor()
                    c2.execute("SELECT chunk_id, file_id, text FROM fts_chunks WHERE file_path=? LIMIT 1", (fpath,))
                    chunk = c2.fetchone()
                    if chunk:
                        items.append({
                            "chunk_id": chunk["chunk_id"],
                            "text": chunk["text"],
                            "score": 0.6,
                            "metadata": {"file_id": chunk["file_id"], "file_name": row["file_name"], "file_path": fpath},
                            "method": "filename",
                        })

            # 2. LIKE fallback (text is jieba-segmented)
            import jieba as _jieba
            # Segment query and search each word with LIKE (also try character-level variants)
            seg_words = [w.strip() for w in _jieba.cut(query, cut_all=False) if len(w.strip()) >= 2]
            # Also add individual chars spaced (handles jieba splitting differently at ingest time)
            all_search_terms = list(seg_words)
            for w in seg_words:
                if len(w) == 2 and all('\u4e00' <= c <= '\u9fff' for c in w):
                    all_search_terms.append(w[1] + w[0])  # reversed: 数用 → 用数
                    all_search_terms.append(w[0] + " " + w[1])  # spaced: 数 用
            all_search_terms = list(set(all_search_terms))
            if all_search_terms:
                # Use OR for each term to maximize recall
                or_conditions = " OR ".join(f"text LIKE '%' || ? || '%'" for _ in all_search_terms)
                c.execute(f"""
                    SELECT chunk_id, file_id, file_name, file_path, text
                    FROM fts_chunks WHERE {or_conditions}
                    LIMIT ?
                """, all_search_terms + [top_k * 3])
                for row in c.fetchall():
                    fpath = row["file_path"]
                    if fpath in seen_files and len(items) >= top_k:
                        continue
                    seen_files.add(fpath)
                    items.append({
                        "chunk_id": row["chunk_id"],
                        "text": row["text"],
                        "score": 0.4,
                        "metadata": {"file_id": row["file_id"], "file_name": row["file_name"], "file_path": row["file_path"]},
                        "method": "like",
                    })
            return items[:top_k * 2]
        except Exception:
            return []

    def sql_query(self, sql: str, max_rows: int = 1000) -> dict:
        """Execute SQL query on tabular data (SELECT only, row-limited).

        Security: rejects DDL/DML (DROP, DELETE, INSERT, UPDATE, ALTER, CREATE).
        """
        # Security: only allow SELECT queries
        sql_stripped = sql.strip().upper()
        dangerous = ["DROP ", "DELETE ", "INSERT ", "UPDATE ", "ALTER ", "CREATE ",
                      "ATTACH ", "DETACH ", "PRAGMA ", "GRANT ", "REVOKE "]
        if any(sql_stripped.startswith(d) for d in dangerous):
            return {"columns": [], "rows": [], "error": "Only SELECT queries are allowed"}
        if not sql_stripped.startswith("SELECT") and not sql_stripped.startswith("WITH"):
            return {"columns": [], "rows": [], "error": "Only SELECT queries are allowed"}

        c = self.conn.cursor()
        try:
            c.execute(sql)
            columns = [desc[0] for desc in c.description] if c.description else []
            rows = [list(row) for row in c.fetchmany(max_rows)]
            truncated = len(rows) >= max_rows
            return {"columns": columns, "rows": rows, "error": None,
                    "truncated": truncated, "max_rows": max_rows}
        except Exception as e:
            # Security: don't expose internal paths in error messages
            err_msg = str(e)
            if "/" in err_msg or "\\" in err_msg:
                err_msg = "Query execution failed"
            return {"columns": [], "rows": [], "error": err_msg}

    def list_tables(self) -> list[dict]:
        """List all tabular data tables (excludes disabled directories)."""
        c = self.conn.cursor()
        c.execute("SELECT * FROM tabular_registry ORDER BY file_path")
        tables = [dict(row) for row in c.fetchall()]
        return [t for t in tables if not self._is_path_disabled(t.get("file_path", ""))]

    def get_table_schema(self, table_name: str) -> dict:
        """Get schema of a tabular data table."""
        c = self.conn.cursor()
        c.execute(f'PRAGMA table_info("{table_name}")')
        columns = [{"name": row[1], "type": row[2]} for row in c.fetchall()]

        c.execute("SELECT * FROM tabular_registry WHERE table_name = ?", (table_name,))
        reg = c.fetchone()
        return {
            "table_name": table_name,
            "columns": columns,
            "headers": json.loads(reg["headers"]) if reg else [],
            "row_count": reg["row_count"] if reg else 0,
            "file_path": reg["file_path"] if reg else "",
        }

    # ---- Stats ----

    def get_stats(self) -> dict:
        """Get knowledge base statistics (excludes disabled directories)."""
        c = self.conn.cursor()
        disabled_sql, disabled_params = self._sql_disabled_filter("source_dir")
        where_active = disabled_sql.replace(" AND ", " WHERE ", 1) if disabled_sql else ""
        and_active = disabled_sql

        c.execute(f"SELECT COUNT(*) as cnt FROM files{where_active}", disabled_params)
        file_count = c.fetchone()["cnt"]

        c.execute(f"SELECT file_type, COUNT(*) as cnt FROM files{where_active} GROUP BY file_type ORDER BY cnt DESC", disabled_params)
        type_counts = {row["file_type"]: row["cnt"] for row in c.fetchall()}

        c.execute("SELECT COUNT(*) as cnt FROM tabular_registry")
        table_count = c.fetchone()["cnt"]

        c.execute(f"SELECT COUNT(*) as cnt FROM files WHERE error != '' AND error IS NOT NULL{and_active}", disabled_params)
        error_count = c.fetchone()["cnt"]

        c.execute(f"SELECT SUM(chunk_count) as cnt FROM files{where_active}", disabled_params)
        row = c.fetchone()
        chunk_count = row["cnt"] or 0

        return {
            "workspace": self.workspace,
            "file_count": file_count,
            "chunk_count": chunk_count,
            "table_count": table_count,
            "error_count": error_count,
            "type_counts": type_counts,
            "db_path": str(self.db_path),
        }

    def list_files(self, source_dir: str = None) -> list[dict]:
        """List indexed files (excludes disabled directories)."""
        c = self.conn.cursor()
        disabled_sql, disabled_params = self._sql_disabled_filter("source_dir")
        if source_dir:
            c.execute(f"SELECT * FROM files WHERE source_dir LIKE ?{disabled_sql} ORDER BY file_path",
                       [f"%{source_dir}%"] + disabled_params)
        else:
            where = disabled_sql.replace(" AND ", " WHERE ", 1) if disabled_sql else ""
            c.execute(f"SELECT * FROM files{where} ORDER BY file_path", disabled_params)
        return [dict(row) for row in c.fetchall()]

    def close(self):
        self.conn.close()
