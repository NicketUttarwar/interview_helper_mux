"""HPUB-1: e2e_soft may walk ship when publish_allowed is false.

Unreadable PMQ envelopes fail closed. Filter still keys off ship_path_ready.
Evaluate PMQ vocab (F6) is unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import filter_delivery_candidates, ship_path_ready
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw


def _write_raw(ctx: RunContext, rel: str, data: object) -> None:
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _plant_ship_preconditions(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    asm = ctx.path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + b"\x00" * 4096)
    mark_done_raw(ctx, "mix")
    mark_done_raw(ctx, "listen_delight_audit")
    _write_raw(ctx, "mastering/listen_delight_audit.json", {"status": "complete", "passed": True})
    _write_raw(ctx, "master/junction_snip_qa.json", {"critical_count": 0, "residuals": []})
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda._junction_commitment_matches_assembly",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"mix", "junction_snip_qa", "listen_delight_audit"},
    )


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.delenv("INTERVIEW_MUX_E2E_SOFT", raising=False)
    run = isolated_run_ctx(tmp_path, "hpub1_pmq")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hpub1_e2e_soft_walks_when_publish_allowed_false(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    _plant_ship_preconditions(ctx, monkeypatch)
    _write_raw(ctx, "master/post_master_quality.json", {"publish_allowed": False, "status": "fail"})
    ready, reason = ship_path_ready(ctx)
    assert ready is True
    assert reason == ""
    filtered = filter_delivery_candidates(
        ctx, ["junction_snip_qa", "master_finalize", "podcast_encode_mp3"]
    )
    assert "master_finalize" in filtered
    assert "podcast_encode_mp3" in filtered


def test_hpub1_non_soft_blocks_when_publish_allowed_false(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_ship_preconditions(ctx, monkeypatch)
    _write_raw(ctx, "master/post_master_quality.json", {"publish_allowed": False, "status": "fail"})
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "pmq_not_publishable"


def test_hpub1_unreadable_envelope_fail_closed_under_e2e_soft(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    _plant_ship_preconditions(ctx, monkeypatch)
    path = ctx.path("master/post_master_quality.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "pmq_not_publishable"


def test_hpub1_non_dict_envelope_fail_closed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    _plant_ship_preconditions(ctx, monkeypatch)
    _write_raw(ctx, "master/post_master_quality.json", ["publish_allowed", False])
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "pmq_not_publishable"


def test_hpub1_unreadable_envelope_fail_closed_without_e2e_soft(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_ship_preconditions(ctx, monkeypatch)
    path = ctx.path("master/post_master_quality.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "pmq_not_publishable"


def test_hpub1_publish_allowed_true_still_ready(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_ship_preconditions(ctx, monkeypatch)
    _write_raw(ctx, "master/post_master_quality.json", {"publish_allowed": True})
    ready, reason = ship_path_ready(ctx)
    assert ready is True
    assert reason == ""


def test_hpub1_remote_sync_refused_when_publish_allowed_false(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import remote_publish_allowed

    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    _plant_ship_preconditions(ctx, monkeypatch)
    _write_raw(ctx, "master/post_master_quality.json", {"publish_allowed": False})
    allowed, why = remote_publish_allowed(ctx)
    assert allowed is False
    assert why == "pmq_not_publishable"
    ready, _reason = ship_path_ready(ctx)
    # Local encode/cover/package may still walk under e2e_soft.
    assert ready is True
