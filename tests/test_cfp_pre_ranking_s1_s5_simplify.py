"""CFP pre_ranking S1–S5 simplify: pass-scoped rounds + peel HV/diar/lattice QC."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from interview_mux.artifact_ownership import write_permitted
from interview_mux.homunculus.agenda import stage_outputs_present
from interview_mux.run_context import RunContext
from interview_mux.segment_fuse import (
    FUSE_ROUNDS_PATH,
    FUSE_ROUNDS_PRE_RANKING_PATH,
    fuse_rounds_path,
    run_connector_fuse_pass,
)
from interview_mux.stage_completion import stage_artifact_incompleteness
from interview_mux.stage_contract import load_contract
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "cfp_pre_s1_s5")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_s1_fuse_rounds_path_is_pass_scoped() -> None:
    assert fuse_rounds_path("post_sanitize") == FUSE_ROUNDS_PATH
    assert fuse_rounds_path("pre_ranking") == FUSE_ROUNDS_PRE_RANKING_PATH
    assert FUSE_ROUNDS_PATH != FUSE_ROUNDS_PRE_RANKING_PATH


def test_s1_analysis_rounds_cannot_satisfy_pre_ranking(ctx: RunContext) -> None:
    ctx.write_json(
        FUSE_ROUNDS_PATH,
        {"pass_id": "pre_ranking", "total_applied": 0},
        skip_handoff=True,
    )
    assert stage_outputs_present(ctx, "connector_fuse_pass_pre_ranking") is False
    assert stage_artifact_incompleteness(ctx, "connector_fuse_pass_pre_ranking")
    ctx.write_json(
        FUSE_ROUNDS_PRE_RANKING_PATH,
        {"pass_id": "pre_ranking", "total_applied": 0},
        skip_handoff=True,
    )
    assert stage_outputs_present(ctx, "connector_fuse_pass_pre_ranking") is True
    assert stage_artifact_incompleteness(ctx, "connector_fuse_pass_pre_ranking") is None


def test_s1_pre_ranking_owns_dedicated_rounds_path(ctx: RunContext) -> None:
    ok, reason = write_permitted(
        ctx,
        FUSE_ROUNDS_PRE_RANKING_PATH,
        "connector_fuse_pass_pre_ranking",
        role="producer",
        verb="persist",
    )
    assert ok, reason
    ok_deny, _ = write_permitted(
        ctx,
        FUSE_ROUNDS_PATH,
        "connector_fuse_pass_pre_ranking",
        role="producer",
        verb="persist",
    )
    assert ok_deny is False


def test_s2_s3_pre_ranking_skips_hv_diar_and_lattice_qc(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, int] = {"hv": 0, "diar": 0, "air": 0, "encompass": 0, "split": 0}

    def _hv(*_a: Any, **_k: Any) -> dict[str, Any]:
        calls["hv"] += 1
        return {"total_applied": 0, "rounds": []}

    def _diar(*_a: Any, **_k: Any) -> list[dict[str, Any]]:
        calls["diar"] += 1
        return [{"pair_id": "a__b", "decision": "fuse"}]

    def _air(*_a: Any, **_k: Any) -> dict[str, Any]:
        calls["air"] += 1
        return {"trimmed": 0}

    def _encompass(*_a: Any, **_k: Any) -> dict[str, Any]:
        calls["encompass"] += 1
        return {"applied": 0}

    def _split(*_a: Any, **_k: Any) -> dict[str, Any]:
        calls["split"] += 1
        return {"ok": True}

    monkeypatch.setattr(
        "interview_mux.segment_fuse.run_high_value_cluster_fuse_rounds", _hv
    )
    monkeypatch.setattr(
        "interview_mux.diarization_suspicion.forced_diarization_fuse_verdicts", _diar
    )
    monkeypatch.setattr("interview_mux.segment_fuse.rerun_air_bounds_on_fused", _air)
    monkeypatch.setattr(
        "interview_mux.segment_fuse.encompass_straddling_islands", _encompass
    )
    monkeypatch.setattr(
        "interview_mux.segment_fuse.assert_no_split_suspect_islands", _split
    )
    monkeypatch.setattr(
        "interview_mux.segment_fuse.enumerate_seam_packets",
        lambda *_a, **_k: {"packets": []},
    )

    # Bypass schema: fuse body only needs artifact_exists(manifest).
    path = ctx.final_path("segments", "manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"segments":[{"segment_id":"seg_a","start_ms":0,"end_ms":500,'
        '"text":"hello","speaker_id":"spk_0","type":"speech",'
        '"speaker_role":"guest","topic_tags":[]}]}',
        encoding="utf-8",
    )
    result = run_connector_fuse_pass(ctx, pass_id="pre_ranking")
    assert calls == {"hv": 0, "diar": 0, "air": 0, "encompass": 0, "split": 0}
    assert (result.get("high_value_cluster_fuse") or {}).get("skipped") == "pre_ranking_peel"
    assert (result.get("diarization_forced_fuse") or {}).get("skipped") == "pre_ranking_peel"
    assert (result.get("air_bounds") or {}).get("skipped") == "pre_ranking_peel"
    assert result.get("encompassed") == 0
    assert (result.get("split_island_qc") or {}).get("skipped") == "pre_ranking_peel"
    assert ctx.artifact_exists(FUSE_ROUNDS_PRE_RANKING_PATH)
    assert not ctx.artifact_exists(FUSE_ROUNDS_PATH)


def test_s4_settle_and_remap_still_load_bearing(ctx: RunContext) -> None:
    """S4 keep: settle reopen + index remap mutation still permitted."""
    from interview_mux.segment_fuse import select_pending_seam_packets

    ctx.write_json(
        "analysis/connector_fuse_audit.json",
        {
            "version": 1,
            "stay_independent": [
                {
                    "pair_id": "seg_a__seg_b",
                    "seam_hash": "hash1",
                    "decision": "stay_independent",
                }
            ],
            "applied_fuses": [],
            "passes": [],
        },
        skip_handoff=True,
    )
    pending, _reopened, skipped = select_pending_seam_packets(
        ctx,
        [
            {
                "pair_id": "seg_a__seg_b",
                "seam_hash": "hash1",
                "earlier_segment_id": "seg_a",
                "later_segment_id": "seg_b",
                "earlier_end_ms": 1000,
                "later_start_ms": 1100,
            }
        ],
        pass_id="pre_ranking",
        force_readjudicate=False,
    )
    assert pending == []
    assert skipped == 1
    ok, reason = write_permitted(
        ctx,
        "transcripts/index.json",
        "connector_fuse_pass_pre_ranking",
        role="producer",
        verb="persist",
        mutation_class="segment_id_remap",
    )
    assert ok, reason


def test_s5_contract_manifest_is_hard() -> None:
    c = load_contract("connector_fuse_pass_pre_ranking")
    assert c is not None
    hard = {d.path for d in c.inputs if d.hard and d.path}
    soft = {d.path for d in c.inputs if not d.hard and d.path}
    outs = {o.path for o in c.outputs}
    assert "segments/manifest.json" in hard
    assert "segments/manifest.json" not in soft
    assert FUSE_ROUNDS_PRE_RANKING_PATH in outs
    assert FUSE_ROUNDS_PATH not in outs
