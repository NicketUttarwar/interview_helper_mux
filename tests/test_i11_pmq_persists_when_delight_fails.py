"""i11h: PMQ must persist even when authoritative delight loud-fails.

exec_13167: run_post_master_quality called delight first; floors failed before
persist → only master.wav staged → hollow mark_done:master_finalize thrash.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.post_master_quality import run_post_master_quality
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i11h_pmq_before_delight_fail")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_i11_pmq_persists_when_delight_loud_fails(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    master = ctx.run_dir / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "master.wav").write_bytes(b"RIFF" + (b"\x00" * 2048))
    (master / "junction_snip_qa.json").write_text('{"version":1,"blocking_reasons":[]}')

    def _boom(_ctx):
        raise RuntimeError("listen_delight_floors_failed: synthetic")

    monkeypatch.setattr(
        "interview_mux.listen_delight.run_authoritative_listen_delight_at_ship",
        _boom,
    )
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.build_autopsy",
        lambda *_a, **_k: {
            "version": 1,
            "phase": "post_master",
            "scores": {},
            "seams": [],
            "blocking_reasons": [],
            "commitment": {"status": "committed"},
        },
    )
    monkeypatch.setattr("interview_mux.seam_autopsy.write_autopsy", lambda *_a, **_k: None)
    monkeypatch.setattr("interview_mux.seam_autopsy.enrich_ledger", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "interview_mux.post_master_quality.evaluate_post_master_quality",
        lambda _ctx: {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "never_skipped": True,
            "status": "pass",
            "publish_allowed": True,
            "failed_checks": [],
            "structural_failed_checks": [],
            "rubric_failed_checks": [],
            "checks": [],
            "advisories": [],
            "aspirational": False,
            "scorecard_preview": {"overall": 1.0, "dimensions": {}, "failed_dimensions": []},
        },
    )

    persisted: list[str] = []

    def _persist(ctx_, quality):
        persisted.append("pmq")
        ctx_.write_json("master/post_master_quality.json", quality, skip_handoff=True)

    monkeypatch.setattr(
        "interview_mux.post_master_quality.persist_post_master_quality",
        _persist,
    )

    with pytest.raises(RuntimeError, match="listen_delight_floors_failed"):
        run_post_master_quality(ctx, block=False)

    assert persisted == ["pmq"]
    assert ctx.artifact_exists("master/post_master_quality.json"), (
        "PMQ must land even when delight aborts"
    )
    # Footgun #1: delight fail must not leave finalize seed-complete.
    from interview_mux.done_authority import (
        finalize_ship_gate_open,
        honest_finalize_seeded,
    )

    assert ctx.is_done("master_finalize") is False
    assert finalize_ship_gate_open(ctx) is True
    assert honest_finalize_seeded(ctx) is False
