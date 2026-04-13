"""Ingestion pipeline: scan directory → extract → chunk → index.
Supports pause/stop signals and parallel extraction."""
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from kbase.config import SUPPORTED_EXTENSIONS
from kbase.extract import extract_file
from kbase.chunk import chunk_document
from kbase.store import KBaseStore
from kbase.enhance import enrich_chunk_context, segment_text

# Global control signals for pause/stop
_ingest_stop = threading.Event()
_ingest_pause = threading.Event()


def stop_ingest():
    """Signal the current ingest to stop."""
    _ingest_stop.set()


def pause_ingest():
    """Toggle pause on current ingest."""
    if _ingest_pause.is_set():
        _ingest_pause.clear()  # Resume
    else:
        _ingest_pause.set()    # Pause


def resume_ingest():
    """Resume paused ingest."""
    _ingest_pause.clear()


def ingest_directory(
    store: KBaseStore,
    directory: str,
    force: bool = False,
    progress_callback: Optional[Callable] = None,
    workers: int = 4,
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
        "stopped": False,
        "paused_time": 0,
    }

    # Reset control signals
    _ingest_stop.clear()
    _ingest_pause.clear()

    for i, file_path in enumerate(sorted(files)):
        # Check stop signal
        if _ingest_stop.is_set():
            stats["stopped"] = True
            if progress_callback:
                progress_callback(i + 1, len(files), file_path.name, "stopped")
            break

        # Check pause signal — block until resumed
        while _ingest_pause.is_set() and not _ingest_stop.is_set():
            if progress_callback:
                progress_callback(i + 1, len(files), file_path.name, "paused")
            time.sleep(0.5)
            stats["paused_time"] += 0.5

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

            # Vision: extract and describe images from PPTX/PDF
            ext = file_path.suffix.lower()
            if ext in (".pptx", ".pdf"):
                try:
                    from kbase.vision import describe_document_images
                    from kbase.config import load_settings
                    vis_settings = load_settings()
                    if vis_settings.get("vision_model", "none") != "none":
                        image_descs = describe_document_images(fp, settings=vis_settings, max_images=10)
                        for desc in image_descs:
                            chunks.append({
                                "text": enrich_chunk_context(
                                    desc["text"], file_path.name,
                                    {"slide": desc.get("slide"), "page": desc.get("page")},
                                ),
                                "text_segmented": segment_text(desc["text"]),
                                "metadata": {
                                    "file_path": fp,
                                    "file_name": file_path.name,
                                    "is_image_desc": True,
                                    "slide": desc.get("slide"),
                                    "page": desc.get("page"),
                                },
                            })
                        if image_descs:
                            stats.setdefault("images_described", 0)
                            stats["images_described"] += len(image_descs)
                except Exception as e:
                    print(f"[KBase] Vision extraction failed for {file_path.name}: {e}")

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
