"""Desktop launcher: runs an isolated Flask backend and opens pywebview.

Each launch uses an available loopback port.  The old fixed-port launcher could
silently connect a new window to an older Worldwalker process, which made stale
JavaScript, artwork, and campaign state appear in a freshly extracted build.
"""
import json, os, socket, sys, threading, time
from urllib.request import urlopen
from urllib.parse import quote
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

# Some machines (older/integrated GPUs, remote desktop sessions, certain
# hybrid-GPU laptops) can render the embedded WebView2 browser as a solid
# white window even though the Runtime itself is installed and healthy — a
# known WebView2/Chromium GPU-compositing bug, not a Worldwalker bug. This
# app used to force --disable-gpu up front as a preemptive fix, but that
# turned out to break the alpha-transparency of the embedded Godot canvases
# used for portrait/scene/map ambience: even with the WebGL context
# correctly requesting alpha (confirmed via getContextAttributes().alpha),
# WebView2's software rendering path doesn't composite that alpha channel
# onto the page correctly, and it shows as an opaque black square instead
# of a transparent overlay — invisible to any CSS/JS inspection, only
# visible as the actual rendered pixels. Since the white-window bug is
# hardware-specific (not universal) and blanket-forcing everyone into
# software rendering breaks a real, shipped feature for everyone, this now
# defaults to normal GPU-accelerated rendering. If the white-window bug
# resurfaces for a specific machine, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
# can still be set manually as an environment variable before launching.

import webview
from app import app
from worlds import APP_VERSION
from werkzeug.serving import make_server

LAN_MODE = "--lan" in sys.argv
HOST = "0.0.0.0" if LAN_MODE else "127.0.0.1"
SERVER = make_server(HOST, 0, app, threaded=True)
PORT = SERVER.server_port

WEBVIEW2_DOWNLOAD_URL = "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
# Microsoft's documented existence-check key/GUID for the WebView2 Runtime
# (the "Evergreen" client id) — see the WebView2 distribution docs.
_WEBVIEW2_CLIENT_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_WEBVIEW2_REG_PATHS = [
    (r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\%s" % _WEBVIEW2_CLIENT_GUID,),
    (r"SOFTWARE\Microsoft\EdgeUpdate\Clients\%s" % _WEBVIEW2_CLIENT_GUID,),
]


def webview2_installed():
    """Best-effort check for the Microsoft Edge WebView2 Runtime on Windows.

    pywebview silently falls back to the ancient IE/mshtml engine when this
    Runtime is missing, which can't run this app's JS at all — the result is
    a blank white window with no error, so we check up front instead.
    """
    if sys.platform != "win32":
        return True
    import winreg
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for (subkey,) in _WEBVIEW2_REG_PATHS:
            try:
                with winreg.OpenKey(hive, subkey):
                    return True
            except OSError:
                continue
    return False


def warn_missing_webview2():
    message = (
        "Worldwalker RPG needs the Microsoft Edge WebView2 Runtime to display "
        "its window, and it doesn't look like it's installed on this PC.\n\n"
        "This is a small, free, official Microsoft component (most Windows 10/11 "
        "PCs already have it from Windows Update, but some don't yet).\n\n"
        "Click \"Open Download Page\" to get it, then relaunch Worldwalker RPG."
    )
    try:
        import tkinter as tk
        from tkinter import messagebox
        import webbrowser
        root = tk.Tk()
        root.withdraw()
        if messagebox.askokcancel(
            "Worldwalker RPG — Missing Component",
            message,
            icon="warning",
            default="ok",
        ):
            webbrowser.open(WEBVIEW2_DOWNLOAD_URL)
        root.destroy()
    except Exception:
        # Tkinter unavailable for some reason — fall back to stderr so the
        # failure is at least visible instead of a silent blank window.
        print(message)
        print(WEBVIEW2_DOWNLOAD_URL)


def run_server():
    SERVER.serve_forever()


def local_network_ip():
    """Return the address another device on the same network can open."""
    try:
        address = socket.gethostbyname(socket.gethostname())
        if address and not address.startswith("127."):
            return address
    except OSError:
        pass
    return "127.0.0.1"


if __name__ == "__main__":
    if "--self-test" not in sys.argv and not webview2_installed():
        warn_missing_webview2()
        raise SystemExit(1)
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{PORT}/"
    for _ in range(80):
        try:
            with urlopen(f"{url}api/version", timeout=.25):
                break
        except Exception:
            time.sleep(.05)
    else:
        raise RuntimeError("Worldwalker could not start its local game server.")
    if "--self-test" in sys.argv:
        with urlopen(f"{url}api/version", timeout=3) as response:
            version = json.load(response)
        with urlopen(f"{url}api/state", timeout=3) as response:
            state = json.load(response)
        if version.get("version") != APP_VERSION or state.get("campaign_active") is not False or state.get("state", {}).get("turn") != 0:
            raise RuntimeError("Packaged fresh-launch self-test failed.")
        SERVER.shutdown()
        raise SystemExit(0)
    if LAN_MODE:
        phone_url = f"http://{local_network_ip()}:{PORT}/"
        window_url = f"{url}?phone_host=1&lan_url={quote(phone_url, safe='')}"
        title = f"Worldwalker Phone Host — {phone_url}"
        webview.create_window(title, window_url, width=1180, height=860, min_size=(720, 620))
    else:
        webview.create_window("Worldwalker RPG", url, width=1520, height=940, min_size=(1180, 720))
    try:
        webview.start()
    finally:
        SERVER.shutdown()
