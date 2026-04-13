"""Ingestion pipeline: scan directory → extract → chunk → index."""
import time
from pathlib import Path
from typing import Callable, Optional

from kbase.config import SUPPORTED_EXTENSIONS
from kbase.extract import extract_file
from kbase.chunk import chunk_document
from kbase.store import KBaseStore
from kbase.enhance import enrich_chunk_context, segment_text


def ingest_directory(
    store: KBaseStore,
    directory: str,
    force: bool = False,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Ingest all supported files from a directory.

    Returns stats dict with counts of processed/skipped/failed files.
    """
    dir_path = Path(directory).resolve()
    if not dir_path.is_dir():
        return {"error": f"Not a directory: {directory}"}

    # Collect all supported files (max depth 15 to handle deep nesting)
    NOISE_DIRS = {
        "__pycache__", "node_modules", ".venv", ".git", ".svn",
        "$RECYCLE.BIN", "System Volume Information", ".Trash",
        "~$", ".tmp", "Thumbs.db",
    }
    files = []
    for ext in SUPPORTED_EXTENSIONS:
        for f in dir_path.rglob(f"*{ext}"):
            # Filter: hidden dirs, noise dirs, max depth
            parts = f.relative_to(dir_path).parts
            if len(parts) > 15:
                continue  # Too deeply nested
            if any(part.startswith(".") or part.startswith("~$") for part in parts):
                continue
            if any(noise in str(f) for noise in NOISE_DIRS):
                continue
            files.append(f)

    stats = {
        "total": len(files),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "start_time": time.time(),
    }

    for i, file_path in enumerate(sorted(files)):
        fp = str(file_path)

        # Skip if already indexed and up-to-date
        if not force and store.is_indexed(fp):
            stats["skipped"] += 1
            if progress_callback:
                progress_callback(i + 1, len(files), file_path.name, "skipped")
            continue

        if progress_callback:
            progress_callback(i + 1, len(files), file_path.name, "processing")

        try:
            # Extract
            result = extract_file(fp)
            if result["metadata"].get("error"):
                stats["failed"] += 1
                stats["errors"].append({"file": fp, "error": result["metadata"]["error"]})
                # Still index with metadata for tracking
                store.index_document(fp, "", [], [], result["metadata"])
                continue

            # Chunk
            chunks = chunk_document(
                result["text"],
                file_type=result["metadata"].get("type", ""),
                metadata={
                    "file_path": fp,
                    "file_name": file_path.name,
                    "title": result["metadata"].get("title", file_path.stem),
                },
            )

            # Contextual enrichment: prepend document context to each chunk
            for chunk in chunks:
                chunk["text"] = enrich_chunk_context(
                    chunk["text"], file_path.name, chunk.get("metadata", {})
                )
                # Also segment Chinese for better FTS
                chunk["text_segmented"] = segment_text(chunk["text"])

            # Index
            store.index_document(
                fp,
                result["text"],
                chunks,
                result.get("tables", []),
                result["metadata"],
            )

            stats["processed"] += 1

        except Exception as e:
            stats["failed"] += 1
            stats["errors"].append({"file": fp, "error": str(e)})

    # Clean up: remove index entries for files that no longer exist in this directory
    existing_paths = {str(f) for f in files}
    indexed_files = store.list_files(str(dir_path))
    removed = 0
    for indexed in indexed_files:
        fp = indexed.get("file_path", "")
        if fp and fp.startswith(str(dir_path)) and fp not in existing_paths:
            if not Path(fp).exists():
                store.remove_file(fp)
                removed += 1

    stats["removed"] = removed
    stats["elapsed_seconds"] = round(time.time() - stats["start_time"], 1)
    return stats


def ingest_file(store: KBaseStore, file_path: str, force: bool = False) -> dict:
    """Ingest a single file."""
    fp = str(Path(file_path).resolve())

    if not force and store.is_indexed(fp):
        return {"status": "skipped", "file": fp, "reason": "already indexed"}

    try:
        result = extract_file(fp)
        if result["metadata"].get("error"):
            return {"status": "failed", "file": fp, "error": result["metadata"]["error"]}

        chunks = chunk_document(
            result["text"],
            file_type=result["metadata"].get("type", ""),
            metadata={
                "file_path": fp,
                "file_name": Path(fp).name,
                "title": result["metadata"].get("title", Path(fp).stem),
            },
        )

        store.index_document(fp, result["text"], chunks, result.get("tables", []), result["metadata"])
        return {"status": "ok", "file": fp, "chunks": len(chunks), "tables": len(result.get("tables", []))}

    except Exception as e:
        return {"status": "failed", "file": fp, "error": str(e)}
