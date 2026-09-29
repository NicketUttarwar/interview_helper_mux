#!/usr/bin/env python3
"""Kill a stale server on a port and orphaned workers, on any platform.

``scripts/run.sh`` did this inline with ``lsof -ti tcp:PORT`` and
``ps -ax -o pid=,command= | grep``. Both are guarded by ``command -v``, so on
Windows the port sweep was skipped entirely and a stale server on 8765 had to be
killed by hand before every launch. The ``ps`` sweep was worse than skipped: Git
Bash does provide a ``ps``, so the guard passed, but it does not report native
Windows command lines, so the greps silently matched nothing and the block looked
like it had run.

Routing both through ``interview_mux.proc_compat`` fixes Windows without
changing the Mac: that module tries ``lsof`` and ``pgrep`` first on POSIX even
when psutil is installed, precisely so macOS behaviour stays byte-identical, and
``terminate_pids`` sends SIGTERM there, which is what the inline ``kill`` did.

Best effort by design. Cleanup must never be the reason a launch fails, so this
always exits 0, mirroring the ``|| true`` the shell used.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from interview_mux.proc_compat import (  # noqa: E402
    pids_listening_on_port,
    pids_matching,
    terminate_pids,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=None, help="terminate listeners on this TCP port")
    ap.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="terminate processes whose command line contains this (repeatable)",
    )
    args = ap.parse_args()

    acted = False

    if args.port:
        try:
            pids = pids_listening_on_port(args.port)
        except Exception as exc:  # noqa: BLE001 - cleanup must not break a launch
            print(f"cleanup: port probe failed on {args.port}: {exc}", file=sys.stderr)
            pids = []
        if pids:
            killed = terminate_pids(pids)
            acted = acted or bool(killed)
            print(
                f"cleanup: stale listener on :{args.port} -> terminated {killed or 'none'}",
                file=sys.stderr,
            )

    for pattern in args.pattern:
        try:
            pids = pids_matching(pattern)
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup: scan failed for {pattern!r}: {exc}", file=sys.stderr)
            continue
        if pids:
            killed = terminate_pids(pids)
            acted = acted or bool(killed)
            print(
                f"cleanup: orphan {pattern!r} -> terminated {killed or 'none'}",
                file=sys.stderr,
            )

    # Communicated on stdout so the shell can decide whether to settle.
    print("acted" if acted else "clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
