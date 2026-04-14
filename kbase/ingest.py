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
from kbase.enhance import clean_text, deduplicate_chunks_cross_file
from kbase.enhance import enrich_chunk_context, segment_text

# Global control signals for pause/stop
_ingest_stop = threading.Event()
_ingest_pause = threading.Event()
_ingest_active = False  # True while ingest is running
_ingest_progress = {}   # {current, total, name, status} — last known progress


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
    global _ingest_active, _ingest_progress
    _ingest_active = True
    _ingest_progress = {"current": 0, "total": len(files), "name": "", "status": "scanning"}

    for i, file_path in enumerate(sorted(files)):
        # Check stop signal
        if _ingest_stop.is_set():
            stats["stopped"] = True
            if progress_callback:
                progress_callback(i + 1, len(files), file_path.name, "stopped")
            break

        # Check pause signal — block until resumed
        while _ingest_pause.is_set() and not _ingest_stop.is_set():
            _ingest_progress["status"] = "paused"
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

        _ingest_progress = {"current": i + 1, "total": len(files), "name": file_path.name, "status": "processing"}
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

            # Clean: normalize whitespace, remove headers/footers/watermarks
            result["text"] = clean_text(result["text"])

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

            # Dedup: remove near-duplicate chunks from older file versions
            before_dedup = len(chunks)
            chunks = deduplicate_chunks_cross_file(store, chunks, fp)
            if len(chunks) < before_dedup:
                stats.setdefault("chunks_deduped", 0)
                stats["chunks_deduped"] += before_dedup - len(chunks)

            # Contextual enrichment: clean + prepend document context to each chunk
            for chunk in chunks:
                chunk["text"] = clean_text(chunk["text"])
                chunk["text"] = enrich_chunk_context(
                    chunk["text"], file_path.name, chunk.get("metadata", {})
                )
                # Also segment Chinese for better FTS
                chunk["text_segmented"] = segment_text(chunk["text"])

            # Vision: extract and describe images from PPTX/PDF
            # RAGFlow pattern: merge image descriptions into the same page/slide chunk
            ext = file_path.suffix.lower()
            if ext in (".pptx", ".pdf"):
                try:
                    from kbase.vision import describe_document_images
                    from kbase.config import load_settings
                    vis_settings = load_settings()
                    if vis_settings.get("vision_model", "none") != "none":
                        image_descs = describe_document_images(fp, settings=vis_settings, max_images=10)
                        for desc in image_descs:
                            desc_text = f"\n[Image: {desc['text']}]"
                            slide_or_page = desc.get("slide") or desc.get("page")
                            merged = False
                            # Try to merge into existing chunk with same slide/page
                            if slide_or_page:
                                for chunk in chunks:
                                    cm = chunk.get("metadata", {})
                                    chunk_ref = cm.get("slide") or cm.get("page")
                                    if chunk_ref and str(chunk_ref) == str(slide_or_page):
                                        chunk["text"] += desc_text
                                        chunk["text_segmented"] = segment_text(chunk["text"])
                                        merged = True
                                        break
                            # If no matching chunk found, add as separate chunk
                            if not merged:
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

            # Compile: generate LLM summary (Karpathy LLM Wiki-inspired)
            summary = ""
            try:
                from kbase.config import load_settings as _load_settings
                _settings = _load_settings()
                if _settings.get("llm_provider") and _settings.get("auto_summary", False):
                    from kbase.chat import generate_document_summary
                    summary = generate_document_summary(
                        result["text"], file_path.name, _settings
                    )
                    if summary:
                        stats.setdefault("summaries_generated", 0)
                        stats["summaries_generated"] += 1
            except Exception as e:
                print(f"[KBase] Summary skipped for {file_path.name}: {e}")

            # Index (with chunk-level progress for large files)
            def _chunk_cb(done, total):
                _ingest_progress["status"] = f"embedding {done}/{total}"
                if progress_callback:
                    progress_callback(i + 1, len(files), file_path.name, f"embedding {done}/{total} chunks")

            store.index_document(
                fp,
                result["text"],
                chunks,
                result.get("tables", []),
                result["metadata"],
                summary=summary,
                chunk_progress_cb=_chunk_cb if len(chunks) > 20 else None,
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
    _ingest_active = False
    _ingest_progress = {"current": 0, "total": 0, "name": "", "status": "done"}
    return stats


def ingest_file(store: KBaseStore, file_path: str, force: bool = False) -> dict:
    """Ingest a single file. For mbox files, splits into individual emails."""
    fp = str(Path(file_path).resolve())
    ext = Path(fp).suffix.lower()

    # Special handling: mbox -> split into individual emails
    if ext == '.mbox':
        return _ingest_mbox(store, fp, force)

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


def _ingest_mbox(store: KBaseStore, file_path: str, force: bool = False) -> dict:
    """Split mbox into individual emails and index each separately."""
    from kbase.extract import split_mbox

    try:
        emails = split_mbox(file_path)
        if not emails:
            return {"status": "failed", "file": file_path, "error": "No emails found in mbox"}

        indexed = 0
        for em in emails:
            # Virtual file path: mbox_path#email_index
            virtual_path = f"{file_path}#email_{em['email_index']}"

            if not force and store.is_indexed(virtual_path):
                continue

            chunks = chunk_document(
                em["text"],
                file_type=".eml",
                metadata={
                    "file_path": virtual_path,
                    "file_name": em["virtual_name"],
                    "title": em["metadata"]["title"],
                },
            )

            meta = {
                "type": ".eml",
                "title": em["metadata"]["title"],
                "source_mbox": file_path,
                "email_from": em["metadata"].get("from", ""),
                "email_to": em["metadata"].get("to", ""),
                "email_date": em["metadata"].get("date", ""),
            }
            store.index_document(virtual_path, em["text"], chunks, [], meta)
            indexed += 1

        return {"status": "ok", "file": file_path, "chunks": indexed,
                "message": f"Split into {len(emails)} emails, indexed {indexed}"}

    except Exception as e:
        return {"status": "failed", "file": file_path, "error": str(e)}
