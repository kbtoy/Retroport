"""The workbench as an application: no console, its page in a window of its own.

``Retroport Workbench.exe`` starts this with ``pythonw`` (``pythonw -m retroport.workbench.app`` does
the same):

* what the server says goes to ``<data>/workbench.log`` - there is no console to show it;
* the server starts; when one is running already: the same copy opens only a window, another copy
  (another folder, or this one with newer code since it started) asks to take its place - the old
  one stops (never in a kit job) and its window closes;
* the page opens in an Edge (or Chrome) *app window* - no tabs, no address bar - with a browser
  profile of its own, so it never mixes with your own browsing;
* the app ends with its last page: when the window closes (or every page says goodbye and none
  comes back), the server stops - after any kit job that's running has finished. A page left open
  in the background says it's still there every so often; one that stops saying so (a browser that
  crashed) ends the app a few minutes later.

Without Edge or Chrome the page opens in your default browser, and the same rule ends the app.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request

from . import server as SV

QUIET = 8            # seconds after a page says goodbye before the app ends (a reload says hello again)
SILENT = 240         # seconds without a word from any page before the app ends anyway
FIRST = 90           # seconds to wait for the first page


def browser() -> str:
    """Edge, else Chrome: the browser that opens the app window ("" when neither is installed)."""
    roots = [os.environ.get(v, "") for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
        for root in roots:
            path = os.path.join(root, rel) if root else ""
            if path and os.path.isfile(path):
                return path
    return ""


def open_window(url: str, profile: str) -> subprocess.Popen | None:
    """The page in an app window of its own (None: it went to the default browser)."""
    exe = browser()
    if not exe:
        import webbrowser
        webbrowser.open(url)
        return None
    return subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
                             "--no-default-browser-check", "--disable-background-mode", "--window-size=1500,950"],
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def running(url: str) -> bool:
    """Whether a workbench already answers at ``url``."""
    try:
        with urllib.request.urlopen(url + "api/meta", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def running_app(url: str) -> dict:
    """The running workbench's ``app_info`` ({} from one too old to say)."""
    try:
        with urllib.request.urlopen(url + "api/status", timeout=5) as r:
            return json.load(r).get("app") or {}
    except Exception:
        return {}


def same_copy(other: dict, mine: dict) -> bool:
    """Whether the running workbench is this copy with this code (only a window is needed then)."""
    return bool(other) and os.path.normcase(other.get("from", "")) == os.path.normcase(mine["from"]) and \
        other.get("code", 0) >= mine["code"] - 1


def take_over(url: str, wait: float = 30.0) -> str:
    """Ask the running workbench to stop and wait until it has: "" when it did, else why not."""
    try:
        req = urllib.request.Request(url + "api/quit", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).close()
    except urllib.error.HTTPError as e:
        try:
            return json.load(e).get("error") or str(e)
        except Exception:
            return str(e)
    except Exception as e:
        return str(e)
    end = time.time() + wait
    while time.time() < end:
        time.sleep(0.5)
        if not running(url):
            return ""
    return "it didn't stop"


def ask(text: str) -> bool:
    """A yes/no question box."""
    try:
        import ctypes
        return ctypes.windll.user32.MessageBoxW(None, text, "Retroport Workbench", 0x4 | 0x20) == 6
    except Exception:
        return False


def should_end(wb: SV.Workbench, started: float, now: float, window_open: bool) -> bool:
    """The app's rule for ending (see the module doc)."""
    if wb.quitting and not wb.busy():
        return True
    if wb.busy() or window_open:
        return False
    hello, bye = wb.last_hello, wb.last_bye
    if not hello:
        return now - started > FIRST
    if bye >= hello:
        return now - bye > QUIET
    return now - hello > SILENT


def message(text: str) -> None:
    """A message box: the app has no console to say it in."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Retroport Workbench", 0x10)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    settings = SV.Settings.load()
    data = settings.data_dir
    os.makedirs(data, exist_ok=True)
    log_path = os.path.join(data, "workbench.log")
    if os.path.isfile(log_path) and os.path.getsize(log_path) > 4 << 20:
        os.replace(log_path, log_path + ".old")
    log = open(log_path, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None or getattr(sys, "frozen", False) or os.path.basename(sys.executable).lower() == "pythonw.exe":
        sys.stdout = sys.stderr = log                       # pythonw: no console to write to
    port = SV.PORT
    url = f"http://127.0.0.1:{port}/"
    profile = os.path.join(data, "window")
    print(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} Retroport Workbench starting ({sys.executable})", flush=True)
    mine = SV.app_info()
    print(f"version {mine['version']} from {mine['from']}", flush=True)
    try:
        try:
            httpd, wb = SV.start_server(settings, port)
        except OSError:
            if not running(url):
                raise
            other = running_app(url)
            if same_copy(other, mine):
                print("already running: opening a window on it", flush=True)
                open_window(url, profile)
                return 0
            who = (f"Retroport Workbench {other['version']} from {other['from']}" if other else
                   "An older Retroport Workbench")
            if not other:                                    # too old to be asked to stop
                message(f"{who} is still running. Close its window, wait a few seconds, then start this one "
                        f"({mine['version']} from {mine['from']}) again.")
                return 1
            if not ask(f"{who} is running.\n\nStop it and start this one instead?\n"
                       f"{mine['version']} from {mine['from']}"):
                open_window(url, profile)
                return 0
            why = take_over(url)
            if why:
                message(f"{who} can't stop now: {why}.")
                return 1
            print(f"took over from {other['version']} ({other['from']})", flush=True)
            httpd, wb = SV.start_server(settings, port)
    except OSError as e:
        message(f"Port {port} is taken by another program ({e.strerror or e}), so the workbench can't start.")
        return 1
    except Exception as e:
        traceback.print_exc()
        message(f"The workbench could not start:\n\n{type(e).__name__}: {e}\n\nSee {log_path}")
        return 1
    threading.Thread(target=httpd.serve_forever, name="http", daemon=True).start()
    print(f"listening at {url}", flush=True)
    window = open_window(url, profile)
    started = time.time()
    try:
        while True:
            time.sleep(1)
            window_open = window is not None and window.poll() is None
            if should_end(wb, started, time.time(), window_open):
                break
    except KeyboardInterrupt:
        pass
    print(f"{time.strftime('%H:%M:%S')} the last page closed: stopping", flush=True)
    httpd.shutdown()
    httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
