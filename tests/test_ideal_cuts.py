"""Tests for talking-points-first ideal cuts snap + bind helpers."""

from __future__ import annotations

from interview_mux.ideal_cuts import (
    boundaries_from_snapped_cuts,
    resolve_ideal_cuts_air_order,
    selection_seed_from_snapped,
    snap_ideal_cuts,
)


def _words() -> list[dict]:
    # Two concepts with a pause between them. The second opens a new question.
    first = "the company shipped snack june".split()
    second = "what happened after that launch in the market today".split()
    out = []
    for i, tok in enumerate(first):
        out.append(
            {
                "word": tok,
                "start_ms": i * 500,
                "end_ms": i * 500 + 480,
                "speaker_id": "spk_0",
            }
        )
    base = 3700
    for i, tok in enumerate(second):
        out.append(
            {
                "word": tok,
                "start_ms": base + i * 500,
                "end_ms": base + i * 500 + 480,
                "speaker_id": "spk_1",
            }
        )
    return out


def test_snap_ideal_cuts_and_seed_order():
    cuts = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "start_ms": 0,
                "end_ms": 2490,
                "priority": "must_keep",
                "rationale": "proof",
            },
            {
                "cut_id": "c2",
                "talking_point_id": "tp_2",
                "start_ms": 3700,
                "end_ms": 8200,
                "priority": "should_keep",
                "rationale": "color",
            },
        ]
    }
    snapped = snap_ideal_cuts(
        cuts,
        {"words": _words()},
        cfg={"analysis": {"ideal_cuts": {"acoustic_edge_refine": False, "min_cut_ms": 2000}}},
    )
    assert snapped["cut_count"] == 2
    assert all(c.get("snapped") for c in snapped["cuts"])
    bounds = boundaries_from_snapped_cuts(snapped)
    assert bounds["_meta"]["segment_contract"]["publisher_stage"] == "ideal_cuts_materialize"
    assert bounds["_meta"]["segment_contract"]["timeline_valid"] is True
    assert len(bounds["boundaries"]) == 2
    seed = selection_seed_from_snapped(snapped)
    assert seed["ordered_segment_ids"] == ["seg_001", "seg_002"]
    assert seed["must_keep_segment_ids"] == ["seg_001"]


def test_evaluate_boundary_quality_flags_sparse_ideal_cut_bind():
    from interview_mux.stages.segmentation import evaluate_boundary_quality

    # 56-minute interview with only 4 keep windows → metric_coarse
    doc = {
        "boundaries": [
            {"segment_id": "seg_001", "start_ms": 0, "end_ms": 60_000},
            {"segment_id": "seg_002", "start_ms": 600_000, "end_ms": 720_000},
            {"segment_id": "seg_003", "start_ms": 1_200_000, "end_ms": 1_320_000},
            {"segment_id": "seg_004", "start_ms": 3_000_000, "end_ms": 3_120_000},
        ]
    }
    report = evaluate_boundary_quality(doc, duration_ms=3_350_000)
    assert report["reject"] is True
    assert report["metric_coarse"] is True
    assert report["segment_count"] == 4


def test_evaluate_boundary_quality_accepts_dense_timeline():
    from interview_mux.stages.segmentation import evaluate_boundary_quality

    boundaries = []
    t = 0
    for i in range(80):
        boundaries.append(
            {
                "segment_id": f"seg_{i+1:03d}",
                "start_ms": t,
                "end_ms": t + 40_000,
            }
        )
        t += 40_000
    report = evaluate_boundary_quality({"boundaries": boundaries}, duration_ms=t)
    assert report["reject"] is False
    assert report["segment_count"] == 80


def test_evaluate_boundary_quality_accepts_fine_map_with_minor_coverage_hole():
    """Turn-mapped fine segments must not fail at ~84% coverage (silence gaps)."""
    from interview_mux.stages.segmentation import evaluate_boundary_quality

    duration_ms = 3_347_860
    boundaries = []
    t = 0
    # ~84.5% coverage with hundreds of short segments (Full-auto-like turn map).
    while t < int(duration_ms * 0.845):
        end = min(t + 8_500, int(duration_ms * 0.845))
        if end <= t:
            break
        boundaries.append(
            {
                "segment_id": f"seg_{len(boundaries)+1:03d}",
                "start_ms": t,
                "end_ms": end,
            }
        )
        t = end
    report = evaluate_boundary_quality(
        {"boundaries": boundaries}, duration_ms=duration_ms
    )
    assert report["coverage_ratio"] < 0.85
    assert report["coverage_ratio"] >= 0.70
    assert report["reject"] is False
    assert report["segment_count"] >= 100


def test_evaluate_boundary_quality_accepts_long_segments_without_duration_cap():
    """No max_segment_duration_ms — segment length is not a quality gate."""
    from interview_mux.segment_timeline_standard import segmentation_cfg
    from interview_mux.stages.segmentation import evaluate_boundary_quality

    max_ms = 180_000
    boundaries = []
    t = 0
    for i in range(57):
        boundaries.append(
            {
                "segment_id": f"seg_{i+1:03d}",
                "start_ms": t,
                "end_ms": t + 61_000,
            }
        )
        t += 61_000
    boundaries.append(
        {
            "segment_id": "seg_058",
            "start_ms": t,
            "end_ms": t + max_ms + 60_000,
        }
    )
    duration_ms = boundaries[-1]["end_ms"]
    assert segmentation_cfg().get("max_segment_duration_ms") is None
    report = evaluate_boundary_quality({"boundaries": boundaries}, duration_ms=duration_ms)
    assert report["over_max_count"] == 0
    assert report["reject"] is False
    assert report["coverage_ratio"] >= 0.95


def test_evaluate_boundary_quality_accepts_isolated_over_max_when_cap_configured(monkeypatch):
    """Legacy cap: isolated over-max on a dense map still must not hard-stop."""
    from interview_mux.stages.segmentation import evaluate_boundary_quality

    monkeypatch.setattr(
        "interview_mux.stages.segmentation.segmentation_cfg",
        lambda: {
            "max_segment_duration_ms": 180_000,
            "boundary_quality_min_coverage_ratio": 0.85,
            "boundary_quality_critical_coverage_ratio": 0.70,
        },
    )
    max_ms = 180_000
    boundaries = []
    t = 0
    for i in range(57):
        boundaries.append(
            {
                "segment_id": f"seg_{i+1:03d}",
                "start_ms": t,
                "end_ms": t + 61_000,
            }
        )
        t += 61_000
    boundaries.append(
        {
            "segment_id": "seg_058",
            "start_ms": t,
            "end_ms": t + max_ms + 60_000,
            "overlong_unsplit": True,
        }
    )
    duration_ms = boundaries[-1]["end_ms"]
    report = evaluate_boundary_quality({"boundaries": boundaries}, duration_ms=duration_ms)
    assert report["over_max_count"] == 1
    assert report["metric_coarse"] is False
    assert report["reject"] is False
    assert report["over_max_warning"] is True


def test_resolve_ideal_cuts_air_order_appends_missing():
    seed = {"ordered_segment_ids": ["seg_001", "seg_003"]}
    bind = resolve_ideal_cuts_air_order(
        seed=seed,
        selection_ordered=["seg_001", "seg_002", "seg_003"],
    )
    assert bind["order_authority"] == "ideal_cuts"
    assert bind["ordered_segment_ids"] == ["seg_001", "seg_003", "seg_002"]


def test_resolve_keeper_air_bounds_respects_prev_keeper_floor():
    from interview_mux.ideal_cuts import resolve_keeper_air_bounds

    # Previous keeper ended at 5000; open must not walk back into that slab.
    start, end = resolve_keeper_air_bounds(
        source_start_ms=5100,
        source_end_ms=9000,
        cuts_doc=None,
        words=[
            {"text": "and", "start_ms": 4800, "end_ms": 4950},
            {"text": "then", "start_ms": 5100, "end_ms": 5300},
            {"text": "we", "start_ms": 5400, "end_ms": 5500},
            {"text": "shipped.", "start_ms": 5600, "end_ms": 6000},
        ],
        segment_id="seg_002",
        prev_keeper_end_ms=5000,
        next_keeper_start_ms=12000,
        meta_out={},
    )
    assert start >= 5080  # prev_end + 80
    assert end > start


def test_snap_falls_back_to_clock_when_anchors_unresolved():
    """Paraphrased anchors must not wipe must_keep cuts that have usable clocks."""
    from interview_mux.ideal_cuts import snap_ideal_cuts

    words = [
        {"text": "Hello", "start_ms": 0, "end_ms": 200, "speaker_id": "spk_0"},
        {"text": "world.", "start_ms": 220, "end_ms": 500, "speaker_id": "spk_0"},
        {"text": "Goodbye", "start_ms": 2000, "end_ms": 2300, "speaker_id": "spk_0"},
        {"text": "now.", "start_ms": 2320, "end_ms": 2600, "speaker_id": "spk_0"},
    ]
    cuts = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "start_ms": 0,
                "end_ms": 500,
                "priority": "must_keep",
                "rationale": "wrong anchors, good clocks",
                "start_anchor": "tissue biopsy",
                "end_anchor": "treatment is given",
            }
        ]
    }
    snapped = snap_ideal_cuts(
        cuts,
        {"words": words},
        cfg={
            "analysis": {
                "ideal_cuts": {
                    "min_cut_ms": 200,
                    "acoustic_edge_refine": False,
                    "reject_unresolved_must_keep_anchors": True,
                    "anchor_max_delta_ms": 2000,
                }
            }
        },
    )
    assert snapped["cut_count"] == 1
    resolve = snapped["cuts"][0].get("anchor_resolve") or {}
    start_meta = resolve.get("start") or {}
    assert start_meta.get("source") == "approx_snap"
    assert start_meta.get("fallback") == "approx_snap"
    assert start_meta.get("reason") == "anchor_not_found_near_approx"


def test_snap_ignores_default_zero_word_indexes_far_from_approx():
    """OpenAI schemas force word indexes; models often emit 0/0 when unsure.

    Trusting index 0 collapsed every cut onto the first transcript words and
    emptied bind-mode materialize (no valid cuts after snap).
    """
    words = _words()
    cuts = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "start_ms": 3700,
                "end_ms": 8200,
                "start_word_index": 0,
                "end_word_index": 0,
                "priority": "must_keep",
                "rationale": "bogus indexes must not win",
            }
        ]
    }
    snapped = snap_ideal_cuts(
        cuts,
        {"words": words},
        cfg={
            "analysis": {
                "ideal_cuts": {
                    "acoustic_edge_refine": False,
                    "min_cut_ms": 2000,
                    "anchor_max_delta_ms": 8_000,
                }
            }
        },
    )
    assert snapped["cut_count"] == 1
    cut = snapped["cuts"][0]
    # Must keep the second span — not collapse onto transcript word[0].
    assert int(cut["start_ms"]) >= 2000
    assert int(cut["end_ms"]) >= 7000
    warnings = snapped.get("snap_warnings") or []
    assert any("word_index" in w for w in warnings)
    resolve = cut.get("anchor_resolve") or {}
    assert (
        any("identical start/end word_index" in w for w in warnings)
        or (resolve.get("start") or {}).get("word_index_ignored") is True
        or (resolve.get("start") or {}).get("source") != "word_index"
    )


def test_snap_prefers_verified_anchor_near_approx():
    from interview_mux.ideal_cuts import snap_ideal_cuts

    words = []
    phrase = "tissue biopsy is important.".split()
    t = 10_000
    for tok in phrase:
        words.append(
            {
                "text": tok if tok != "important." else "important.",
                "start_ms": t,
                "end_ms": t + 300,
                "speaker_id": "spk_1",
            }
        )
        t += 350
    # Pad duration
    for i in range(10):
        words.append(
            {
                "text": f"more{i}.",
                "start_ms": t,
                "end_ms": t + 280,
                "speaker_id": "spk_1",
            }
        )
        t += 400
    cuts = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "start_ms": 10_050,
                "end_ms": words[-1]["end_ms"],
                "priority": "must_keep",
                "rationale": "anchor match",
                "start_anchor": "tissue biopsy",
            }
        ]
    }
    snapped = snap_ideal_cuts(
        cuts,
        {"words": words},
        cfg={
            "analysis": {
                "ideal_cuts": {
                    "min_cut_ms": 2000,
                    "acoustic_edge_refine": False,
                    "reject_unresolved_must_keep_anchors": True,
                }
            }
        },
    )
    assert snapped["cut_count"] == 1
    resolve = snapped["cuts"][0].get("anchor_resolve") or {}
    assert (resolve.get("start") or {}).get("source") == "anchor"
    assert (resolve.get("start") or {}).get("matched") is True


def test_empty_snap_demotes_bind_mode_instead_of_raising(tmp_path, monkeypatch):
    from interview_mux.ideal_cuts import (
        IDEAL_CUTS_REL,
        MATERIALIZED_REL,
        run_ideal_cuts_materialize,
    )
    from interview_mux.run_context import RunContext

    ctx = RunContext(str(tmp_path / "cuts_empty"), create=True)
    ctx.write_json(
        IDEAL_CUTS_REL,
        {
            "cuts": [
                {
                    "cut_id": "c1",
                    "talking_point_id": "tp_1",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "priority": "must_keep",
                    "rationale": "empty snap fixture",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json("transcript/full.json", {"words": []})
    monkeypatch.setattr(
        "interview_mux.ideal_cuts.snap_ideal_cuts",
        lambda *a, **k: {"cuts": [], "snap_warnings": ["empty"]},
    )
    monkeypatch.setattr("interview_mux.ideal_cuts.bind_boundaries_enabled", lambda cfg=None: True)
    monkeypatch.setattr("interview_mux.ideal_cuts.bind_ranking_enabled", lambda cfg=None: True)
    run_ideal_cuts_materialize(ctx)
    mat = ctx.read_json(MATERIALIZED_REL)
    assert mat["bind_mode_used"] == "off"
    assert mat["boundary_skip_reason"] == "empty_snap_demote"
    assert mat.get("cuts") == []


def test_icp_b4_span_persist_raises_stage_error_after_retry(monkeypatch):
    """ICP-B4: span coverage RuntimeError retries once, then StageError (no fail-open)."""
    from unittest.mock import MagicMock, patch

    import pytest

    from interview_mux.llm_simple import StageError, run_llm_stage_simple

    ctx = MagicMock()
    ctx.mark_done = MagicMock()
    ctx.log = MagicMock()
    persist_calls = {"n": 0}

    cuts = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "start_ms": 0,
                "end_ms": 3000,
                "priority": "must_keep",
                "rationale": "clustered fixture",
            }
        ]
    }
    envelope = {"status": "complete", "artifacts": cuts}

    def _persist(_ctx, _arts):
        persist_calls["n"] += 1
        raise RuntimeError(
            "ideal_cuts_propose span coverage 0.100 < min 0.450 "
            "(cuts clustered early — redistribute across the interview)"
        )

    with patch("interview_mux.llm_simple.ensure_analysis_workspace"):
        with patch(
            "interview_mux.llm_simple.run_prompt_envelope", return_value=envelope
        ) as invoke:
            with patch(
                "interview_mux.local_volley_framer.prepare_volley_for_llm",
                side_effect=Exception("skip framer"),
            ):
                with pytest.raises(StageError, match="span coverage"):
                    run_llm_stage_simple(
                        ctx,
                        "ideal_cuts_propose",
                        "understanding/ideal-cuts-propose.system.txt",
                        lambda _c: {"task": "propose"},
                        _persist,
                        auto_complete=True,
                    )

    assert invoke.call_count == 2
    assert persist_calls["n"] == 2
    ctx.mark_done.assert_not_called()


def test_icp_b2_defaults_expose_min_span_coverage_ratio():
    """ICP-B2: app.defaults.json documents the 0.45 span floor used by ideal_cuts_cfg."""
    import json
    from pathlib import Path

    from interview_mux.ideal_cuts import ideal_cuts_cfg

    defaults = json.loads(Path("config/app.defaults.json").read_text(encoding="utf-8"))
    block = (defaults.get("analysis") or {}).get("ideal_cuts") or {}
    assert block.get("min_span_coverage_ratio") == 0.45
    assert float(ideal_cuts_cfg().get("min_span_coverage_ratio") or 0) == 0.45
