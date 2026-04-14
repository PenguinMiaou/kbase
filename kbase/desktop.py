"""KBase Desktop — native window using pywebview + uvicorn sidecar."""
import multiprocessing
import os
import platform
import signal
import sys
import threading
import time

IS_MACOS = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"
HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"


def _start_server():
    """Start FastAPI server in subprocess."""
    import uvicorn
    from kbase.web import create_app
    app = create_app("default")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def _wait_for_server(timeout=30):
    """Block until server is ready."""
    import urllib.request
    for _ in range(timeout * 2):
        try:
            urllib.request.urlopen(URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _check_existing():
    """Check if KBase is already running."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, PORT)) == 0


def main():
    """Entry point for kbase-desktop command."""
    multiprocessing.freeze_support()

    # If already running, just open a window to it
    already_running = _check_existing()

    server_proc = None
    if not already_running:
        server_proc = multiprocessing.Process(target=_start_server, daemon=True)
        server_proc.start()
        if not _wait_for_server():
            print("[KBase] Server failed to start")
            sys.exit(1)

    try:
        import webview
    except ImportError:
        print("[KBase] pywebview not installed. Install with: pip install pywebview")
        print(f"[KBase] Falling back to browser mode: {URL}")
        import webbrowser
        webbrowser.open(URL)
        if server_proc:
            try:
                signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
                signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
                while True:
                    time.sleep(1)
            except (KeyboardInterrupt, SystemExit):
                pass
        return

    # Create native window
    window = webview.create_window(
        "KBase",
        URL,
        width=1280,
        height=860,
        min_size=(900, 600),
    )

    # On macOS, pywebview uses WKWebView (native Safari engine)
    # On Windows, it uses Edge WebView2
    webview.start(
        debug=False,
        private_mode=False,
    )

    # Window closed — clean up
    if server_proc:
        server_proc.terminate()
        server_proc.join(timeout=3)


if __name__ == "__main__":
    main()
