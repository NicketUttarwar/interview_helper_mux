"""FastAPI route inventory matches guarded-run registry."""

from __future__ import annotations

import inspect

from interview_mux.web.route_guard_registry import (
    GUARDED_RUN_ROUTE_KEYS,
    GUARD_EXEMPT_RUN_ROUTE_KEYS,
)
from interview_mux.web.server import create_app


def _mutating_run_routes(app) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if not path.startswith("/api/runs/{run_id}/"):
            continue
        for method in methods:
            if method in {"GET", "HEAD", "OPTIONS"}:
                continue
            out.add((method.upper(), path))
    return out


def _handler_guarded(src: str) -> bool:
    return "_guarded_run" in src or "operator_guard" in src or "run_guard(" in src


def test_guarded_registry_covers_mutating_run_routes():
    app = create_app()
    mutating = _mutating_run_routes(app)
    covered = GUARDED_RUN_ROUTE_KEYS | GUARD_EXEMPT_RUN_ROUTE_KEYS
    missing = sorted(mutating - covered)
    assert not missing, f"Unregistered mutating run routes: {missing}"


def test_guarded_handlers_use_run_lock():
    app = create_app()
    failures: list[str] = []
    for method, path in GUARDED_RUN_ROUTE_KEYS:
        route = next(
            (
                r
                for r in app.routes
                if getattr(r, "path", None) == path and method in getattr(r, "methods", set())
            ),
            None,
        )
        assert route is not None, f"{method} {path} missing from app"
        endpoint = route.endpoint
        src = inspect.getsource(endpoint)
        if not _handler_guarded(src):
            failures.append(f"{method} {path}")
    assert not failures, f"Handlers without guard: {failures}"
