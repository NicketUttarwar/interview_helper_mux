"""Hard-refresh the GUI browser tab after scripts/run.sh launches the server."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from interview_mux.process_logging import launched_via_run_sh


def should_force_browser_refresh() -> bool:
    raw = os.environ.get("MUX_NO_BROWSER_REFRESH", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return False
    return launched_via_run_sh()


def cache_busted_url(base_url: str, *, now: float | None = None) -> str:
    root = base_url.split("?")[0].rstrip("/")
    stamp = int(now if now is not None else time.time())
    return f"{root}/?_mux_launch={stamp}"


def wait_for_server(url: str, *, timeout_s: float = 20.0) -> bool:
    """Poll until the GUI HTTP server responds."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.75) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.15)
    return False


def _darwin_hard_reload_script(url_prefix: str) -> str:
    esc = url_prefix.replace("\\", "\\\\").replace('"', '\\"')
    return f'''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
end tell

if frontApp is "Google Chrome" then
    tell application "Google Chrome"
        set found to false
        repeat with w in windows
            set ti to 1
            repeat with t in tabs of w
                if (URL of t) starts with "{esc}" then
                    set active tab index of w to ti
                    set index of w to 1
                    set found to true
                    exit repeat
                end if
                set ti to ti + 1
            end repeat
            if found then exit repeat
        end repeat
        activate
    end tell
else if frontApp is "Safari" then
    tell application "Safari" to activate
else if frontApp is "Firefox" then
    tell application "Firefox" to activate
end if

delay 0.15
tell application "System Events"
    keystroke "r" using {{command down, shift down}}
end tell
'''


def force_browser_hard_refresh(url_prefix: str) -> bool:
    """Hard-reload the GUI tab (Cmd+Shift+R on macOS). Returns True if attempted."""
    if sys.platform != "darwin":
        return False
    try:
        subprocess.run(
            ["osascript", "-e", _darwin_hard_reload_script(url_prefix)],
            check=False,
            capture_output=True,
            timeout=10,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def schedule_open_and_hard_refresh(
    *,
    url: str,
    host: str,
    port: int,
    open_fn: Callable[[str], None],
    delay_after_open_s: float = 0.35,
) -> None:
    """Background: wait for server, open cache-busted URL, then hard-refresh."""

    def _worker() -> None:
        base = f"http://{host}:{port}".rstrip("/")
        if not wait_for_server(f"{base}/"):
            return
        bust = cache_busted_url(base)
        open_fn(bust)
        if not should_force_browser_refresh():
            return
        time.sleep(delay_after_open_s)
        force_browser_hard_refresh(base)

    threading.Thread(target=_worker, daemon=True, name="mux-browser-refresh").start()
