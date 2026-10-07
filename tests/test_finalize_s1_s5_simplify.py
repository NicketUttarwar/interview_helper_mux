"""master_finalize safest S1–S5: loudnorm+thin ship gate; no nested kitchen."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from interview_mux.aspirational_quality import (
    STRUCTURAL_PMQ_CHECKS,
    is_rubric_pmq_check,
    is_structural_pmq_check,
)
from interview_mux.post_master_quality import (
    evaluate_post_master_quality,
    run_post_master_quality,
)
from interview_mux.stages import mastering
from run_fixtures import isolated_run_ctx


def _raw(ctx, rel: str, data: dict) -> None:
    path = Path(ctx.run_dir) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "finalize_s1_s5")


def test_s1_no_nested_junction_or_take_best() -> None:
    src = inspect.getsource(mastering.run_master_finalize)
    assert "take_best_candidate" not in src
    assert "run_junction_snip_qa" not in src
    assert "optimizer_best_unpaid" in src


def test_s4_no_entry_book_heals() -> None:
    src = inspect.getsource(mastering.run_master_finalize)
    assert "heal_omit_ledger_air_contract" not in src
    assert "sync_edl_vo_script_metadata" not in src
    assert "ensure_layup_gap_authority" not in src


def test_s3_pmq_does_not_rewrite_autopsy() -> None:
    src = inspect.getsource(run_post_master_quality)
    assert "build_autopsy" not in src
    assert "write_autopsy" not in src


def test_s2_pmq_does_not_rescore_delight_floors(ctx, monkeypatch) -> None:
    master = Path(ctx.run_dir) / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "master.wav").write_bytes(b"RIFF" + (b"\x00" * 2048))
    _raw(
        ctx,
        "master/seam_autopsy.json",
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "phase": "post_master",
            "commitment": {"status": "committed", "reasons": []},
            "scores": {
                "continuity": 0.95,
                "finishability": 0.95,
                "information_clarity": 0.95,
                "music_completeness": 0.95,
                "sonic_density_fit": 0.9,
            },
            "seams": [],
            "blocking_reasons": [],
        },
    )
    _raw(
        ctx,
        "master/junction_snip_qa.json",
        {"version": 1, "residual_findings": [], "blocking_reasons": []},
    )
    monkeypatch.setattr(
        "interview_mux.aspirational_quality.is_aspirational_enabled",
        lambda _ctx=None: True,
    )
    quality = evaluate_post_master_quality(ctx)
    ids = [c["check_id"] for c in quality["checks"]]
    assert "listen_delight_floors" not in ids


def test_s5_thin_structural_ship_bar() -> None:
    # Only "the master is missing or not the one the EDL describes" (ISSUES 185).
    assert STRUCTURAL_PMQ_CHECKS == frozenset(
        {
            "master_exists_nonempty",
            "seam_commitment",
            "audible_script_hash_agreement",
        }
    )
    assert is_structural_pmq_check("seam_commitment") is True
    for cid in (
        "opening_music_quality",
        "opening_orientation_contract",
        "air_order_integrity",
        "no_open_ship_bar_defects",
        "stage_output_semantics",
        "ship_reachability_analysis",
        "scorecard_overall_floor",
        "planned_music_preserved",
    ):
        assert is_structural_pmq_check(cid) is False
        assert is_rubric_pmq_check(cid) is True


def test_s1_refuses_unpaid_optimizer(ctx, monkeypatch) -> None:
    from interview_mux.loud_fail import LoudStageFailure

    master = Path(ctx.run_dir) / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "assembly.wav").write_bytes(b"RIFF" + (b"\x00" * 2048))
    _raw(
        ctx,
        "master/selection.json",
        {"ordered_segment_ids": ["a", "b"], "order_hash": "sel"},
    )

    monkeypatch.setattr(
        "interview_mux.gates.require_timeline_optimizer_clear",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.gates.require_g_listen_clear",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.air_order.assert_consumer",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.timeline_optimizer.state.load_optimizer_state",
        lambda _ctx: {"finalize_applied_best": False, "promoted_needs_remaster": True},
    )
    monkeypatch.setattr(
        "interview_mux.timeline_optimizer.state.load_best",
        lambda _ctx: {
            "score": 1.0,
            "ordered_segment_ids": ["x"],
            "order_hash": "best",
        },
    )
    with pytest.raises(LoudStageFailure) as ei:
        mastering.run_master_finalize(ctx)
    assert ei.value.reason == "optimizer_best_unpaid"
