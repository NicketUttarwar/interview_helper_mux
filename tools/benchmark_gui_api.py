#!/usr/bin/env python3
"""Quick timing harness for session-scoped GUI API endpoints."""

from __future__ import annotations

import argparse
import time
from urllib.parse import urljoin

import httpx


def _time_get(client: httpx.Client, path: str, *, label: str) -> float:
    start = time.perf_counter()
    res = client.get(path)
    elapsed = time.perf_counter() - start
    print(f"{label:28} {elapsed:6.3f}s  status={res.status_code}")
    return elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark hot GUI API routes")
    parser.add_argument("--base", default="http://127.0.0.1:8765", help="GUI server base URL")
    parser.add_argument("--run-id", required=True, help="Active run id to probe")
    args = parser.parse_args()

    base = args.base.rstrip("/") + "/"
    run_id = args.run_id
    with httpx.Client(timeout=120.0) as client:
        _time_get(client, urljoin(base, "/api/runs/session-scope"), label="session-scope")
        _time_get(client, urljoin(base, "/api/runs"), label="list-runs (scoped)")
        _time_get(client, urljoin(base, f"/api/runs/{run_id}"), label="get-run")
        _time_get(client, urljoin(base, f"/api/runs/{run_id}/log?tail=500"), label="log tail 500")


if __name__ == "__main__":
    main()
