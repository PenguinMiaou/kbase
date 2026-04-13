"""KBase macOS App Launcher — starts web server, shows in Dock, opens browser."""
import multiprocessing
import os
import sys
import time
import webbrowser
import signal

# Fix for PyInstaller bundled app
if getattr(sys, 'frozen', False):
    os.environ['MPLCONFIGDIR'] = os.path.join(os.path.expanduser('~'), '.kbase', 'mpl')
    bundle_dir = sys._MEIPASS
    os.environ['PATH'] = bundle_dir + os.pathsep + os.environ.get('PATH', '')
    # Add user-installed packages
    user_pkgs = os.path.join(os.path.expanduser('~'), '.kbase', 'python_packages')
    if os.path.isdir(user_pkgs) and user_pkgs not in sys.path:
        sys.path.insert(0, user_pkgs)


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


def is_port_in_use(port=8765):
    """Check if KBase is already running."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def main():
    # If already running, just open browser and exit
    if is_port_in_use():
        webbrowser.open("http://127.0.0.1:8765/")
        return

    # Start server in a subprocess
    server_proc = multiprocessing.Process(target=start_server, daemon=True)
    server_proc.start()

    # Open browser
    open_browser()

    # Keep app alive and visible in Dock using native macOS API
    try:
        import objc
        from Foundation import NSObject
        from AppKit import NSApplication, NSApp, NSMenu, NSMenuItem, NSStatusBar

        app = NSApplication.sharedApplication()
        # Accessory mode: shows in menu bar, not in Dock (avoids bouncing icon issue)
        app.setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory = 1

        # Create status bar item (menu bar icon)
        status_bar = NSStatusBar.systemStatusBar()
        status_item = status_bar.statusItemWithLength_(-1)  # NSVariableStatusItemLength
        status_item.setTitle_("KB")

        # Status bar menu
        menu = NSMenu.new()
        menu.addItemWithTitle_action_keyEquivalent_("Open KBase in Browser", "openBrowser:", "")
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItemWithTitle_action_keyEquivalent_("Quit KBase", "terminate:", "q")
        status_item.setMenu_(menu)

        # Delegate
        class AppDelegate(NSObject):
            def openBrowser_(self, sender):
                webbrowser.open("http://127.0.0.1:8765/")

        delegate = AppDelegate.new()
        app.setDelegate_(delegate)
        app.run()

    except ImportError:
        # PyObjC not available — fallback to signal.pause()
        try:
            print("[KBase] Server running at http://127.0.0.1:8765 (Ctrl+C to quit)")
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
            signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass

    finally:
        server_proc.terminate()
        server_proc.join(timeout=3)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
