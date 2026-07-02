#!/usr/bin/env python3
"""Verify run-scoped mutating FastAPI routes use operator_guard or _guarded_run."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.web.route_guard_registry import (  # noqa: E402
    GUARDED_RUN_ROUTE_KEYS,
    GUARD_EXEMPT_RUN_ROUTE_KEYS,
)
from interview_mux.web.server import create_app  # noqa: E402


def _route_key(method: str, path: str) -> tuple[str, str]:
    return method.upper(), path


def main() -> int:
    app = create_app()
    missing: list[str] = []
    for method, path in sorted(GUARDED_RUN_ROUTE_KEYS):
        if _route_key(method, path) in GUARD_EXEMPT_RUN_ROUTE_KEYS:
            continue
        route = next(
            (
                r
                for r in app.routes
                if getattr(r, "path", None) == path and method in getattr(r, "methods", set())
            ),
            None,
        )
        if route is None:
            missing.append(f"{method} {path} — route not registered")
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            missing.append(f"{method} {path} — no endpoint")
            continue
        try:
            src = inspect.getsource(endpoint)
        except OSError:
            src = ""
        if "_guarded_run" not in src and "operator_guard" not in src and "run_guard(" not in src:
            missing.append(f"{method} {path} — handler missing _guarded_run/operator_guard")

    if missing:
        print("Run guard audit failures:", file=sys.stderr)
        for line in missing:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"OK — {len(GUARDED_RUN_ROUTE_KEYS)} guarded run routes verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
