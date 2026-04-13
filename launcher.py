"""KBase macOS App Launcher — starts web server and opens browser."""
import multiprocessing
import os
import sys
import time
import webbrowser
import signal

# Fix for PyInstaller bundled app
if getattr(sys, 'frozen', False):
    os.environ['MPLCONFIGDIR'] = os.path.join(os.path.expanduser('~'), '.kbase', 'mpl')
    # Ensure bundled dir is in path
    bundle_dir = sys._MEIPASS
    os.environ['PATH'] = bundle_dir + os.pathsep + os.environ.get('PATH', '')


def start_server():
    """Start the FastAPI server."""
    import uvicorn
    from kbase.web import create_app

    app = create_app("default")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


def open_browser():
    """Wait for server to be ready, then open browser."""
    import urllib.request
    for _ in range(30):  # Wait up to 15 seconds
        try:
            urllib.request.urlopen("http://127.0.0.1:8765/", timeout=1)
            webbrowser.open("http://127.0.0.1:8765/")
            return
        except Exception:
            time.sleep(0.5)


def show_dock_icon():
    """Show a simple status window using Tkinter (bundled with Python)."""
    try:
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.title("KBase")
        root.geometry("360x200")
        root.resizable(False, False)

        # Center on screen
        root.update_idletasks()
        x = (root.winfo_screenwidth() // 2) - 180
        y = (root.winfo_screenheight() // 2) - 100
        root.geometry(f"+{x}+{y}")

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="KBase", font=("Helvetica", 24, "bold")).pack(pady=(0, 5))
        ttk.Label(frame, text="Local Knowledge Base", font=("Helvetica", 12)).pack()

        status = ttk.Label(frame, text="Server running at http://127.0.0.1:8765", font=("Helvetica", 10))
        status.pack(pady=(15, 5))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=10)

        ttk.Button(btn_frame, text="Open in Browser",
                   command=lambda: webbrowser.open("http://127.0.0.1:8765/")).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Quit",
                   command=lambda: (os.kill(os.getpid(), signal.SIGTERM))).pack(side="left", padx=5)

        def on_close():
            os.kill(os.getpid(), signal.SIGTERM)

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.mainloop()
    except Exception:
        # If Tkinter fails, just keep the process alive
        signal.pause()


def main():
    # Start server in a subprocess
    server_proc = multiprocessing.Process(target=start_server, daemon=True)
    server_proc.start()

    # Open browser
    open_browser()

    # Show status window (keeps app alive)
    try:
        show_dock_icon()
    except KeyboardInterrupt:
        pass
    finally:
        server_proc.terminate()
        server_proc.join(timeout=3)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
