"""Selection packer — single shared pack-to-duration path (Plan 2 listenability spine).

Covers ``selection_auto_pack.pack_selection_to_duration`` (shared by both the
hard-budget safety net and the editorial soft-pack) and confirms the forced
minimum-trim "theater" that used to run on top of ``enforce_creative_selection_edit``
has been retired — a selection already within the ideal budget is left alone.
"""

from __future__ import annotations

from interview_mux.creative_delivery import enforce_creative_selection_edit
from interview_mux.selection_auto_pack import (
    auto_pack_selection_to_brief,
    pack_selection_to_duration,
)
from run_fixtures import isolated_run_ctx


def _seg(segment_id: str, *, start_ms: int, end_ms: int, speaker: str) -> dict:
    return {
        "segment_id": segment_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker_id": speaker,
        "speaker_role": "interviewee",
        "type": "interviewee_answer",
        "text": f"Segment {segment_id}.",
        "topic_tags": [],
        "flags": [],
    }


def _write_five_segments(ctx) -> None:
    # s1(A) s2(A) s3(A) s4(B) s5(B) — s2 is the only mid-monologue (A-A-A) segment.
    segments = [
        _seg("seg_001", start_ms=0, end_ms=10000, speaker="spk_a"),
        _seg("seg_002", start_ms=10000, end_ms=20000, speaker="spk_a"),
        _seg("seg_003", start_ms=20000, end_ms=30000, speaker="spk_a"),
        _seg("seg_004", start_ms=30000, end_ms=40000, speaker="spk_b"),
        _seg("seg_005", start_ms=40000, end_ms=50000, speaker="spk_b"),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segments}, skip_handoff=True)


def _write_delivery_brief(ctx, *, min_sec: float, ideal_sec: float, max_sec: float) -> None:
    ctx.write_json(
        "understanding/delivery_brief.json",
        {
            "version": 1,
            "source_duration_ms": 60_000,
            "target_duration_sec": {"min": min_sec, "ideal": ideal_sec, "max": max_sec},
            "question_budget": {"min": 0, "ideal": 1, "max": 2},
            "chapter_budget": {"min": 1, "ideal": 2, "max": 4},
            "selection_mode": "coverage_first",
            "sfx_density": {"max_beds": 1, "max_punctuators": 1, "max_foley": 0},
            "ranking_weights": {},
            "rationale": ["fixture"],
            "operator_overrides": {},
            "generated": {"at": "1970-01-01T00:00:00+00:00", "by": "test_fixture"},
        },
        skip_handoff=True,
    )


def _selection(ranks: dict[str, float]) -> dict:
    return {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_003", "seg_004", "seg_005"],
        "excluded_segment_ids": [],
        "segment_ranks": ranks,
    }


def test_pack_prefers_mid_monologue_drop_over_pure_rank(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pack_mid_mono")
    _write_five_segments(ctx)
    # Isolated / worst-rank clips drop before mid-monologue native points.
    ranks = {"seg_001": 1, "seg_002": 2, "seg_003": 3, "seg_004": 4, "seg_005": 5}
    out = pack_selection_to_duration(
        ctx,
        _selection(ranks),
        target_sec=45.0,
        stage="test",
        meta_key="test_pack",
        action_id="pipeline.selection.test_pack",
        log_label="Test pack",
    )
    assert "seg_002" in out["ordered_segment_ids"]
    assert out["_meta"]["test_pack"]["dropped"]
    assert "seg_005" in out["_meta"]["test_pack"]["dropped"] or "seg_004" in out["_meta"]["test_pack"]["dropped"]


def test_pack_no_drop_when_already_within_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pack_within_budget")
    _write_five_segments(ctx)
    selection = _selection({})
    out = pack_selection_to_duration(
        ctx,
        selection,
        target_sec=60.0,
        stage="test",
        meta_key="test_pack",
        action_id="pipeline.selection.test_pack",
        log_label="Test pack",
    )
    assert out is selection  # unchanged object — no-op fast path


def test_auto_pack_selection_to_brief_targets_max(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "auto_pack_max")
    _write_five_segments(ctx)
    _write_delivery_brief(ctx, min_sec=10, ideal_sec=45, max_sec=45)
    ranks = {"seg_001": 1, "seg_002": 2, "seg_003": 3, "seg_004": 4, "seg_005": 5}
    out = auto_pack_selection_to_brief(ctx, _selection(ranks), stage="full_master_ranking")
    assert len(out["ordered_segment_ids"]) == 4
    assert "auto_pack" in out["_meta"]


def test_enforce_creative_selection_edit_single_pack_no_forced_extra_drop(tmp_path, monkeypatch):
    """Selection already within the ideal budget must be left alone — no forced
    minimum-trim on top of an already-tight pack (the retired "must-drop theater")."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "creative_no_theater")
    _write_five_segments(ctx)
    _write_delivery_brief(ctx, min_sec=10, ideal_sec=60, max_sec=90)
    selection = _selection({})
    out = enforce_creative_selection_edit(ctx, selection, stage="full_master_ranking")
    assert out["ordered_segment_ids"] == selection["ordered_segment_ids"]
    assert not out.get("excluded_segment_ids")
    assert "creative_trim" not in (out.get("_meta") or {})


def test_enforce_creative_selection_edit_packs_toward_ideal_when_over(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "creative_pack_ideal")
    _write_five_segments(ctx)
    _write_delivery_brief(ctx, min_sec=10, ideal_sec=45, max_sec=90)
    ranks = {"seg_001": 1, "seg_002": 2, "seg_003": 3, "seg_004": 4, "seg_005": 5}
    out = enforce_creative_selection_edit(ctx, _selection(ranks), stage="full_master_ranking")
    assert len(out["ordered_segment_ids"]) == 4
    assert out["_meta"]["creative_pack"]["target_sec"] == 45.0
