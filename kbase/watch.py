"""File watcher for dynamic updates - auto re-index on file changes."""
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from kbase.config import SUPPORTED_EXTENSIONS
from kbase.ingest import ingest_file
from kbase.store import KBaseStore


class KBaseHandler(FileSystemEventHandler):
    """Watch for file changes and auto-reindex."""

    def __init__(self, store: KBaseStore, log_func=None):
        self.store = store
        self.log = log_func or print
        self._debounce = {}

    def _should_process(self, path: str) -> bool:
        p = Path(path)
        if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False
        if any(part.startswith(".") for part in p.parts):
            return False
        return True

    def _debounced(self, path: str) -> bool:
        """Simple debounce: skip if same file changed within 2 seconds."""
        now = time.time()
        last = self._debounce.get(path, 0)
        if now - last < 2:
            return False
        self._debounce[path] = now
        return True

    def on_created(self, event):
        if event.is_directory:
            return
        if self._should_process(event.src_path) and self._debounced(event.src_path):
            self.log(f"[NEW] {event.src_path}")
            result = ingest_file(self.store, event.src_path, force=True)
            self.log(f"  -> {result.get('status', 'unknown')}")

    def on_modified(self, event):
        if event.is_directory:
            return
        if self._should_process(event.src_path) and self._debounced(event.src_path):
            self.log(f"[MODIFIED] {event.src_path}")
            result = ingest_file(self.store, event.src_path, force=True)
            self.log(f"  -> {result.get('status', 'unknown')}")

    def on_deleted(self, event):
        if event.is_directory:
            return
        if self._should_process(event.src_path):
            self.log(f"[DELETED] {event.src_path}")
            self.store.remove_file(event.src_path)


def start_watcher(store: KBaseStore, directory: str, log_func=None) -> Observer:
    """Start watching a directory for changes."""
    handler = KBaseHandler(store, log_func)
    observer = Observer()
    observer.schedule(handler, directory, recursive=True)
    observer.start()
    return observer
