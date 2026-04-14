"""KBase Cross-Platform App Launcher — starts web server + opens UI."""
import multiprocessing
import os
import platform
import sys
import time
import webbrowser
import signal

# Set process name to "kbase" instead of "python3"
try:
    import setproctitle
    setproctitle.setproctitle("kbase")
except ImportError:
    pass

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"


def check_libreoffice():
    """Check and install LibreOffice if missing (background, non-blocking)."""
    import shutil, subprocess, threading
    if shutil.which("soffice"):
        return
    def _install():
        try:
            if IS_MACOS:
                if shutil.which("brew"):
                    subprocess.run(["brew", "install", "--cask", "libreoffice"],
                                   capture_output=True, timeout=300)
                else:
                    # No brew — try downloading DMG directly
                    import urllib.request, tempfile
                    url = "https://download.documentfoundation.org/libreoffice/stable/25.2.3/mac/aarch64/LibreOffice_25.2.3_MacOS_aarch64.dmg"
                    dmg = os.path.join(tempfile.gettempdir(), "LibreOffice.dmg")
                    if not os.path.exists(dmg):
                        urllib.request.urlretrieve(url, dmg)
                    subprocess.run(["hdiutil", "attach", dmg, "-nobrowse", "-quiet"], capture_output=True, timeout=30)
                    import glob
                    apps = glob.glob("/Volumes/LibreOffice*/LibreOffice.app")
                    if apps:
                        subprocess.run(["cp", "-R", apps[0], "/Applications/"], capture_output=True, timeout=120)
                        vol = apps[0].split("/")[2]
                        subprocess.run(["hdiutil", "detach", f"/Volumes/{vol}", "-quiet"], capture_output=True)
                    os.remove(dmg)
            elif IS_WINDOWS:
                subprocess.run(["winget", "install", "--id",
                                "TheDocumentFoundation.LibreOffice", "-e", "--silent"],
                               capture_output=True, timeout=300)
        except Exception:
            pass  # silent fail — preview falls back to Python HTML
    threading.Thread(target=_install, daemon=True).start()


def start_server():
    """Start the FastAPI server."""
    import uvicorn
    from kbase.web import create_app
    app = create_app("default")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


def open_browser():
    """Wait for server to be ready, then open browser."""
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:8765/", timeout=1)
            webbrowser.open("http://127.0.0.1:8765/")
            return
        except Exception:
            time.sleep(0.5)


def check_existing_instance(port=8765):
    """Check if KBase is already running and healthy."""
    import socket, urllib.request
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('127.0.0.1', port)) != 0:
            return "not_running"
    # Port in use — check if it's a healthy KBase
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=2) as resp:
            return "healthy"
    except Exception:
        return "zombie"  # Port occupied but not responding


def kill_zombie(port=8765):
    """Kill zombie process holding the port (cross-platform)."""
    import subprocess
    if IS_WINDOWS:
        # Use netstat to find PID on Windows
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                try:
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True, timeout=5)
                except Exception:
                    pass
    else:
        # macOS/Linux: lsof
        result = subprocess.run(["lsof", f"-ti:{port}"], capture_output=True, text=True)
        for pid in result.stdout.strip().split("\n"):
            if pid.strip():
                try:
                    os.kill(int(pid.strip()), 9)
                except (ValueError, ProcessLookupError):
                    pass
    time.sleep(1)


def open_existing_browser():
    """Open browser for existing healthy instance (cross-platform)."""
    if IS_MACOS:
        import subprocess
        subprocess.Popen(["open", "http://127.0.0.1:8765/"])
    else:
        webbrowser.open("http://127.0.0.1:8765/")
    time.sleep(1)
    os._exit(0)


def keep_alive_macos():
    """Keep app alive with macOS native menu bar icon."""
    try:
        import objc
        from Foundation import NSObject
        from AppKit import NSApplication, NSApp, NSMenu, NSMenuItem, NSStatusBar

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory

        status_bar = NSStatusBar.systemStatusBar()
        status_item = status_bar.statusItemWithLength_(-1)
        status_item.setTitle_("KB")

        menu = NSMenu.new()
        menu.addItemWithTitle_action_keyEquivalent_("Open KBase in Browser", "openBrowser:", "")
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItemWithTitle_action_keyEquivalent_("Quit KBase", "terminate:", "q")
        status_item.setMenu_(menu)

        class AppDelegate(NSObject):
            def openBrowser_(self, sender):
                webbrowser.open("http://127.0.0.1:8765/")

        delegate = AppDelegate.new()
        app.setDelegate_(delegate)
        app.run()
    except ImportError:
        keep_alive_generic()


def keep_alive_windows():
    """Keep app alive on Windows with system tray icon (or simple loop)."""
    try:
        import pystray
        from PIL import Image

        # Create a simple tray icon
        def create_icon():
            img = Image.new('RGB', (64, 64), color=(30, 60, 180))
            try:
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(img)
                draw.text((18, 10), "K", fill=(255, 255, 255))
            except Exception:
                pass
            return img

        def on_open(icon, item):
            webbrowser.open("http://127.0.0.1:8765/")

        def on_quit(icon, item):
            icon.stop()

        icon = pystray.Icon(
            "KBase",
            create_icon(),
            "KBase",
            menu=pystray.Menu(
                pystray.MenuItem("Open in Browser", on_open, default=True),
                pystray.MenuItem("Quit", on_quit),
            )
        )
        icon.run()
    except ImportError:
        keep_alive_generic()


def keep_alive_generic():
    """Fallback keep-alive loop for any platform."""
    try:
        print("[KBase] Server running at http://127.0.0.1:8765 (Ctrl+C to quit)")
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass


def show_splash():
    """Show a splash screen with KBase logo while server starts (Windows/Linux)."""
    if IS_MACOS:
        return None  # macOS has menu bar icon, no splash needed
    try:
        import tkinter as tk
        from pathlib import Path

        splash = tk.Tk()
        splash.overrideredirect(True)  # No title bar
        splash.attributes('-topmost', True)

        # Center on screen
        w, h = 360, 200
        x = (splash.winfo_screenwidth() - w) // 2
        y = (splash.winfo_screenheight() - h) // 2
        splash.geometry(f'{w}x{h}+{x}+{y}')
        splash.configure(bg='#1a1a2e')

        # Try to load logo
        logo_path = None
        for p in [
            Path(__file__).parent / 'kbase' / 'static' / 'logos' / 'kbase-logo.svg',
            Path(getattr(sys, '_MEIPASS', '.')) / 'kbase' / 'static' / 'logos' / 'kbase-logo.svg',
        ]:
            if p.exists():
                logo_path = p
                break

        # Title
        tk.Label(splash, text='KBase', font=('Segoe UI', 28, 'bold'),
                 fg='#818cf8', bg='#1a1a2e').pack(pady=(30, 5))
        tk.Label(splash, text='Local Knowledge Base',
                 font=('Segoe UI', 11), fg='#94a3b8', bg='#1a1a2e').pack()

        # Progress
        status_label = tk.Label(splash, text='Starting server...',
                                font=('Segoe UI', 9), fg='#64748b', bg='#1a1a2e')
        status_label.pack(pady=(20, 5))

        # Animated dots
        dot_count = [0]
        def animate():
            dot_count[0] = (dot_count[0] + 1) % 4
            dots = '.' * dot_count[0]
            status_label.config(text=f'Starting server{dots}')
            splash.after(500, animate)
        animate()

        splash.update()
        return splash
    except Exception:
        return None


def main():
    status = check_existing_instance()
    if status == "healthy":
        open_existing_browser()
    elif status == "zombie":
        kill_zombie()

    # Show splash screen while starting
    splash = show_splash()

    # Check LibreOffice (background install if missing)
    check_libreoffice()

    # Start server in a subprocess
    server_proc = multiprocessing.Process(target=start_server, daemon=True)
    server_proc.start()

    # Open browser (closes splash when ready)
    def _open_and_close_splash():
        import urllib.request
        for _ in range(30):
            try:
                urllib.request.urlopen("http://127.0.0.1:8765/", timeout=1)
                webbrowser.open("http://127.0.0.1:8765/")
                if splash:
                    try:
                        splash.destroy()
                    except Exception:
                        pass
                return
            except Exception:
                time.sleep(0.5)
    import threading
    threading.Thread(target=_open_and_close_splash, daemon=True).start()

    # Keep splash alive until server ready (Windows needs mainloop for tkinter)
    if splash:
        def check_server():
            try:
                import urllib.request
                urllib.request.urlopen("http://127.0.0.1:8765/", timeout=1)
                splash.destroy()
            except Exception:
                splash.after(500, check_server)
        splash.after(1000, check_server)
        try:
            splash.mainloop()
        except Exception:
            pass

    try:
        if IS_MACOS:
            keep_alive_macos()
        elif IS_WINDOWS:
            keep_alive_windows()
        else:
            keep_alive_generic()
    finally:
        server_proc.terminate()
        server_proc.join(timeout=3)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
