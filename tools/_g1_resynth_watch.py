#!/usr/bin/env python3
"""Watch g1_resynth3.log until DONE or parent death; print progress."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "ASSETS"
LOG = ASSETS / "g1_resynth3.log"
PIDF = ASSETS / "g1_resynth3.pid"


def main() -> int:
    last = ""
    while True:
        text = LOG.read_text(errors="ignore") if LOG.is_file() else ""
        lines = [ln for ln in text.splitlines() if ln.strip()]
        cur = lines[-1] if lines else ""
        if cur != last:
            print(time.strftime("%H:%M:%S"), cur[:240], flush=True)
            last = cur
        alive = False
        try:
            pid = int(PIDF.read_text().strip())
            alive = (
                subprocess.call(
                    ["ps", "-p", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                == 0
            )
        except Exception:
            alive = False
        if "DONE missing" in text:
            print("COMPLETE", cur, flush=True)
            return 0
        if not alive:
            print("RESYNTH_DIED", cur, flush=True)
            return 1
        time.sleep(30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
