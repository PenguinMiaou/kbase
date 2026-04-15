"""Shared fixtures for kbase tests."""
import sqlite3

import pytest


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace directory mimicking ~/.kbase/default/."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "chroma").mkdir()
    return ws


@pytest.fixture
def tmp_db(tmp_workspace):
    """Create a temporary SQLite database with kbase schema."""
    db_path = tmp_workspace / "metadata.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            filename TEXT,
            file_type TEXT,
            file_size INTEGER,
            mtime REAL,
            hash TEXT,
            status TEXT DEFAULT 'ok',
            error TEXT,
            indexed_at REAL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
            content, file_path, metadata
        );
    """)
    conn.close()
    return str(db_path)


@pytest.fixture
def sample_texts():
    """Sample texts for chunking and search tests."""
    return {
        "short": "这是一段简短的测试文本。",
        "medium": "数据治理是企业数字化转型的核心能力。" * 50,
        "long": "# 第一章\n\n" + "内容段落。" * 200 + "\n\n# 第二章\n\n" + "更多内容。" * 200,
        "english": "This is a test document about machine learning and artificial intelligence.",
        "mixed": "KBase 是一个本地知识库系统，支持 RAG + Text2SQL + Full-text Search。",
    }
