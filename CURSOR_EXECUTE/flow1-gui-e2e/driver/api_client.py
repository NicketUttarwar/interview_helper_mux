"""Read-only HTTP client for GUI E2E (no POST /execute)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str, timeout: int = 60) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GET {path} -> {exc.code}: {body}") from exc

    def health(self) -> dict[str, Any]:
        return self._get("/api/health")

    def config(self) -> dict[str, Any]:
        return self._get("/api/config")

    def session(self) -> dict[str, Any]:
        return self._get("/api/session")

    def runs(self) -> dict[str, Any]:
        return self._get("/api/runs")

    def run(self, run_id: str) -> dict[str, Any]:
        return self._get(f"/api/runs/{run_id}")

    def job(self, run_id: str) -> dict[str, Any]:
        data = self._get(f"/api/runs/{run_id}/job")
        return data.get("job") or data

    def log_tail(self, run_id: str, tail: int = 20) -> list[dict[str, Any]]:
        data = self._get(f"/api/runs/{run_id}/log?tail={tail}")
        return list(data.get("entries") or [])

    def summary(self, run_id: str) -> dict[str, Any]:
        return self._get(f"/api/runs/{run_id}/summary")
