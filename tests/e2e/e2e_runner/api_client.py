"""HTTP client for interview_mux GUI API."""

from __future__ import annotations

import time
from typing import Any

import httpx


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def health(self) -> dict[str, Any]:
        return self._get("/api/health")

    def config(self) -> dict[str, Any]:
        return self._get("/api/config")

    def assets(self) -> list[dict[str, Any]]:
        data = self._get("/api/assets")
        return list(data.get("files") or [])

    def create_run(
        self,
        input_audio_path: str,
        *,
        flow_intent: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"input_audio_path": input_audio_path}
        if flow_intent:
            body["flow_intent"] = flow_intent
        return self._post("/api/runs", body)

    def list_runs(self) -> list[dict[str, Any]]:
        data = self._get("/api/runs")
        return list(data.get("runs") or [])

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._get(f"/api/runs/{run_id}")

    def get_job(self, run_id: str) -> dict[str, Any]:
        return self._get(f"/api/runs/{run_id}/job")

    def get_log(self, run_id: str, *, tail: int = 200) -> list[dict[str, Any]]:
        data = self._get(f"/api/runs/{run_id}/log", params={"tail": tail})
        return list(data.get("entries") or data.get("log") or [])

    def set_active(self, run_id: str) -> dict[str, Any]:
        return self._put("/api/session/active", {"run_id": run_id})

    def clear_session(self) -> dict[str, Any]:
        resp = self._client.delete("/api/session/active")
        resp.raise_for_status()
        return resp.json()

    def execute(
        self,
        run_id: str,
        body: dict[str, Any],
        *,
        api_consents: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        payload = dict(body)
        if api_consents:
            payload["api_consents"] = api_consents
        return self._post(f"/api/runs/{run_id}/execute", payload)

    def select_flow(self, run_id: str, flow: str) -> dict[str, Any]:
        return self._post(f"/api/runs/{run_id}/flow", {"flow": flow})

    def complete_transcript_review(
        self,
        run_id: str,
        *,
        accept_unreviewed: bool = True,
    ) -> dict[str, Any]:
        return self._post(
            f"/api/runs/{run_id}/transcript-review/complete",
            {"accept_unreviewed": accept_unreviewed},
        )

    def verify_profile(self, run_id: str) -> dict[str, Any]:
        return self._post(f"/api/runs/{run_id}/analysis-profile/verify")

    def upload_vo(self, run_id: str, line_id: str, wav_bytes: bytes) -> dict[str, Any]:
        files = {"file": (f"{line_id}.wav", wav_bytes, "audio/wav")}
        resp = self._client.post(f"/api/runs/{run_id}/vo/{line_id}", files=files)
        resp.raise_for_status()
        return resp.json()

    def preclean_offer(
        self,
        run_id: str,
        checkpoint: str,
        action: str,
        *,
        scope: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"checkpoint": checkpoint, "action": action}
        if scope:
            body["scope"] = scope
        return self._post(f"/api/runs/{run_id}/preclean-offer", body)

    def handoff_ack(self, run_id: str, stage_id: str) -> dict[str, Any]:
        return self._post(f"/api/runs/{run_id}/handoff-ack", {"stage_id": stage_id})

    def preview_listened(self, run_id: str) -> dict[str, Any]:
        return self._post(f"/api/runs/{run_id}/milestones/preview-listened")

    def approve_elevenlabs_prompts(self, run_id: str) -> dict[str, Any]:
        return self._post(f"/api/runs/{run_id}/elevenlabs-prompts/approve", {})

    def wait_for_health(self, *, timeout_s: float = 120.0, interval_s: float = 1.0) -> None:
        deadline = time.monotonic() + timeout_s
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self.health()
                return
            except Exception as exc:
                last_err = exc
                time.sleep(interval_s)
        raise TimeoutError(f"Server not healthy after {timeout_s}s: {last_err}")

    def wait_for_job_terminal(
        self,
        run_id: str,
        *,
        timeout_s: float = 7200.0,
        poll_s: float = 2.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            job = self.get_job(run_id)
            status = str(job.get("status") or "idle")
            if status in ("complete", "error", "gate", "needs_operator", "idle"):
                if status == "running":
                    time.sleep(poll_s)
                    continue
                return job
            if status not in ("running", "running_with_warnings"):
                return job
            time.sleep(poll_s)
        raise TimeoutError(f"Job did not finish within {timeout_s}s for {run_id}")

    def _get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        resp = self._client.get(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._client.post(path, json=body or {})
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.put(path, json=body)
        resp.raise_for_status()
        return resp.json()


API_CONSENTS = {"openai": True, "aws": True, "elevenlabs": True}
