"""G1.5 — MMAudio SFX prompt review API (BUILD-066 / steps-forward #20)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, isolated_run_ctx, patch_server_ctx


def test_sfx_prompts_get_put_approve(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_g15")
    init_run_meta_for_test(ctx)
    ctx.write_json(
        "sound_design/sfx_prompts.json",
        {
            "prompts": [
                {
                    "asset_id": "sting_a",
                    "sfx_prompt": "Warm podcast sting, no vocals.",
                    "duration_seconds": 1.5,
                    "negative_prompt": "speech",
                }
            ]
        },
    )
    patch_server_ctx(monkeypatch, ctx)
    client = TestClient(create_app())

    res = client.get(f"/api/runs/{ctx.run_id}/sfx-prompts")
    assert res.status_code == 200
    body = res.json()
    assert body["prompts"][0]["asset_id"] == "sting_a"
    assert body["review_required"] is True
    assert body["can_generate"] is False
    assert body["listen_results"] == []
    assert body["generated_assets"] == []

    res = client.put(
        f"/api/runs/{ctx.run_id}/sfx-prompts",
        json={
            "path": "sound_design/sfx_prompts.json",
            "data": {
                "prompts": [
                    {
                        "asset_id": "sting_a",
                        "sfx_prompt": "Edited warm sting.",
                        "duration_seconds": 1.5,
                        "negative_prompt": "speech",
                    }
                ]
            },
        },
    )
    assert res.status_code == 200
    assert res.json()["review"]["approved"] is False

    res = client.post(
        f"/api/runs/{ctx.run_id}/sfx-prompts/approve",
        json={"approved_by": "pytest"},
    )
    assert res.status_code == 200
    assert res.json()["review"]["approved"] is True

    meta = ctx.read_json("run_meta.json")
    assert meta["sfx_prompt_review"]["approved"] is True
    assert meta["sfx_prompt_review"]["approved_by"] == "pytest"
    log_text = (ctx.run_dir / "gui_log.jsonl").read_text(encoding="utf-8")
    assert "sfx_prompts_approved" in log_text

    res = client.get(f"/api/runs/{ctx.run_id}/sfx-prompts")
    assert res.json()["can_generate"] is True


def test_sfx_listen_result_appends_meta_and_logs(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_g15_listen")
    init_run_meta_for_test(ctx)
    patch_server_ctx(monkeypatch, ctx)
    client = TestClient(create_app())

    res = client.post(
        f"/api/runs/{ctx.run_id}/sfx-prompts/listen-result",
        json={"asset_id": "sting_a", "result": "pass", "note": "no vocals"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["entry"]["asset_id"] == "sting_a"
    assert body["entry"]["result"] == "pass"
    assert body["entry"]["note"] == "no vocals"
    assert len(body["sfx_listen_results"]) == 1

    res = client.post(
        f"/api/runs/{ctx.run_id}/sfx-prompts/listen-result",
        json={"asset_id": "bed_main", "result": "fail"},
    )
    assert res.status_code == 200
    assert len(res.json()["sfx_listen_results"]) == 2

    meta = ctx.read_json("run_meta.json")
    assert len(meta["sfx_listen_results"]) == 2
    log_text = (ctx.run_dir / "gui_log.jsonl").read_text(encoding="utf-8")
    assert "sfx_post_listen_pass" in log_text
    assert "sfx_post_listen_fail" in log_text


def test_sfx_generated_assets_on_prompts_get(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_g15_assets")
    init_run_meta_for_test(ctx)
    ctx.write_json(
        "sound_design/sfx_prompts.json",
        {
            "prompts": [
                {
                    "asset_id": "sting_a",
                    "sfx_prompt": "Warm sting.",
                    "duration_seconds": 1.5,
                    "negative_prompt": "speech",
                }
            ]
        },
    )
    assets_dir = ctx.path("sound_design/assets")
    assets_dir.mkdir(parents=True)
    (assets_dir / "sting_a.wav").write_bytes(b"RIFF")
    patch_server_ctx(monkeypatch, ctx)
    client = TestClient(create_app())

    res = client.get(f"/api/runs/{ctx.run_id}/sfx-prompts")
    assert res.status_code == 200
    body = res.json()
    assert len(body["generated_assets"]) == 1
    assert body["generated_assets"][0]["asset_id"] == "sting_a"
    assert body["generated_assets"][0]["path"] == "sound_design/assets/sting_a.wav"
