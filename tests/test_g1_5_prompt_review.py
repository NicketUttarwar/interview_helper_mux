"""G1.5 — MMAudio SFX prompt review API (BUILD-066 / steps-forward #20)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interview_mux.artifact_ownership import AuthorityDenied

from interview_mux.sfx_prompt_review import (
    can_run_sfx_generation,
    maybe_auto_approve_prompt_review,
)
from interview_mux.web.server import create_app
from run_fixtures import (
    init_run_meta_for_test,
    isolated_run_ctx,
    patch_merged_config,
    patch_server_ctx,
    write_fixture_json,
)


def _write_prompts_with_soft_warning(ctx) -> None:
    """Prompts pass schema but SDP alignment warning fires (missing SDP)."""
    write_fixture_json(
        ctx,
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
        stage_key="sfx_prompt_craft",
    )


def test_g15_full_auto_auto_approves_with_soft_warnings(tmp_path, monkeypatch) -> None:
    """SPC-B2: Full-auto auto-approves G1.5 even when completeness QA has soft warnings."""
    patch_merged_config(monkeypatch, {"g1_5_require_prompt_approval": True})
    ctx = isolated_run_ctx(tmp_path, "run_g15_fa_warn")
    init_run_meta_for_test(ctx)
    meta = ctx.read_json("run_meta.json")
    meta["full_auto"] = True
    meta["run_mode"] = "full-auto"
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    _write_prompts_with_soft_warning(ctx)

    assert maybe_auto_approve_prompt_review(ctx) is True
    review = ctx.read_json("run_meta.json")["sfx_prompt_review"]
    assert review["approved"] is True
    assert review["approved_by"] == "auto_full_auto"
    ok, _ = can_run_sfx_generation(ctx)
    assert ok is True


def test_g15_partial_does_not_auto_approve_with_soft_warnings(tmp_path, monkeypatch) -> None:
    """SPC-B2: Partial keeps G1.5 wait when soft warnings present."""
    patch_merged_config(monkeypatch, {"g1_5_require_prompt_approval": True})
    ctx = isolated_run_ctx(tmp_path, "run_g15_partial_warn")
    init_run_meta_for_test(ctx)
    meta = ctx.read_json("run_meta.json")
    meta["partial_auto"] = True
    meta["run_mode"] = "partially-accelerated"
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    _write_prompts_with_soft_warning(ctx)

    assert maybe_auto_approve_prompt_review(ctx) is False
    ok, msg = can_run_sfx_generation(ctx)
    assert ok is False
    assert "G1.5" in msg


def test_g15_first_try_green_still_auto_approves(tmp_path, monkeypatch) -> None:
    """first_try + green QA still auto-approves outside Full-auto."""
    patch_merged_config(
        monkeypatch,
        {
            "g1_5_require_prompt_approval": True,
            "journey_ui": {"first_try_mode": True},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "run_g15_ft_green")
    init_run_meta_for_test(ctx)
    _write_prompts_with_soft_warning(ctx)
    monkeypatch.setattr(
        "interview_mux.sfx_prompt_review.prompt_completeness_warnings",
        lambda *_a, **_k: [],
    )

    assert maybe_auto_approve_prompt_review(ctx) is True
    assert ctx.read_json("run_meta.json")["sfx_prompt_review"]["approved_by"] == "auto_qa_green"


def test_sfx_prompts_get_put_approve(tmp_path, monkeypatch) -> None:
    patch_merged_config(monkeypatch, {"g1_5_require_prompt_approval": True})
    ctx = isolated_run_ctx(tmp_path, "run_g15")
    init_run_meta_for_test(ctx)
    write_fixture_json(
        ctx,
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
        stage_key="sfx_prompt_craft",
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

    with pytest.raises(AuthorityDenied, match="role_gui_pin_only"):
        client.put(
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
    write_fixture_json(
        ctx,
        "sound_design/sfx_prompts.json",
        {
            "prompts": [
                {
                    "asset_id": "sting_a",
                    "sfx_prompt": "Edited warm sting.",
                    "duration_seconds": 1.5,
                    "negative_prompt": "speech",
                }
            ]
        },
        stage_key="sfx_prompt_craft",
    )

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
    monkeypatch.setattr(
        "interview_mux.stages.sfx_mmaudio.maybe_auto_refine",
        lambda *_a, **_k: [],
    )
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
    write_fixture_json(
        ctx,
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
        stage_key="sfx_prompt_craft",
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
