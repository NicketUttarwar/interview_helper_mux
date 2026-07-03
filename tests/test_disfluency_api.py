from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_server_ctx


def test_disfluency_review_api(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(
        monkeypatch,
        tmp_path,
        disfluency_extract={"enabled": True},
        disfluency_restore={"enabled": True},
    )
    ctx = RunContext("exec_200_20260101T000200Z", create=True)
    init_run_meta_for_test(ctx)
    ctx.write_json(
        "transcript/disfluencies.json",
        {
            "schema_version": 1,
            "status": "ready",
            "events": [
                {
                    "event_id": "fill_0001",
                    "start_ms": 100,
                    "end_ms": 400,
                    "text": "um",
                    "review_status": "pending",
                    "include_in_restore": True,
                }
            ],
            "stats": {"total": 1, "pending": 1, "confirmed": 0, "rejected": 0},
        },
    )
    ctx.mark_done("disfluency_extract")
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    rid = ctx.run_id

    r = client.get(f"/api/runs/{rid}/disfluency-review")
    assert r.status_code == 200
    assert r.json()["pending_count"] == 1

    r = client.post(f"/api/runs/{rid}/disfluency-review/complete")
    assert r.status_code == 400

    r = client.post(
        f"/api/runs/{rid}/disfluency-review/complete",
        json={"accept_unreviewed": True},
    )
    assert r.status_code == 200
    assert r.json()["disfluency_review_clear"] is True

    r = client.patch(f"/api/runs/{rid}/disfluency-restore", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["disfluency_restore_enabled"] is False


def test_disfluency_clip_audio_served(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(
        monkeypatch,
        tmp_path,
        disfluency_extract={"enabled": True},
    )
    ctx = RunContext("exec_200_20260101T000202Z", create=True)
    init_run_meta_for_test(ctx)
    clip_rel = "transcript/disfluency_clips/fill_0001.wav"
    clip_path = ctx.path("transcript", "disfluency_clips", "fill_0001.wav")
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"RIFF\x24\x08\x00\x00WAVEfmt ")
    ctx.write_json(
        "transcript/disfluencies.json",
        {
            "schema_version": 1,
            "status": "ready",
            "events": [
                {
                    "event_id": "fill_0001",
                    "start_ms": 100,
                    "end_ms": 400,
                    "text": "um",
                    "clip_path": clip_rel,
                    "review_status": "pending",
                    "include_in_restore": True,
                }
            ],
            "stats": {"total": 1, "pending": 1, "confirmed": 0, "rejected": 0},
        },
    )
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    rid = ctx.run_id
    r = client.get(f"/api/runs/{rid}/audio", params={"path": clip_rel})
    assert r.status_code == 200
    assert r.content


def test_disfluency_review_confirm_then_complete(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(
        monkeypatch,
        tmp_path,
        disfluency_extract={"enabled": True},
    )
    ctx = RunContext("exec_200_20260101T000201Z", create=True)
    init_run_meta_for_test(ctx)
    ctx.write_json(
        "transcript/disfluencies.json",
        {
            "schema_version": 1,
            "status": "ready",
            "events": [
                {
                    "event_id": "fill_0001",
                    "start_ms": 100,
                    "end_ms": 400,
                    "text": "um",
                    "review_status": "pending",
                    "include_in_restore": True,
                }
            ],
            "stats": {"total": 1, "pending": 1, "confirmed": 0, "rejected": 0},
        },
    )
    ctx.mark_done("disfluency_extract")
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    rid = ctx.run_id

    r = client.put(
        f"/api/runs/{rid}/disfluency-review/fill_0001",
        json={"review_status": "confirmed"},
    )
    assert r.status_code == 200
    assert r.json()["stats"]["confirmed"] == 1
    assert r.json().get("review_complete") is True

    r = client.post(f"/api/runs/{rid}/disfluency-review/complete")
    assert r.status_code == 200
    assert r.json()["disfluency_review_clear"] is True
