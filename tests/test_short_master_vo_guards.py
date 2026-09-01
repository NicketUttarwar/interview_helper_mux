"""Guards against exec_1576-class short masters and QC-prose synthetic VO."""

from __future__ import annotations

import json

from interview_mux.ideal_cuts import (
    cut_span_coverage_ratio,
    map_cuts_onto_existing_boundaries,
    selection_seed_from_snapped,
    strip_provisional_segment_ids,
)
from interview_mux.junction_snip_qa import apply_junction_repairs
from interview_mux.order_hash import stamp_order_hash
from interview_mux.rank_candidates import pick_best_order
from interview_mux.spoken_meta_lint import is_editorial_qc_prose, lint_spoken_text
from run_fixtures import isolated_run_ctx


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_strip_provisional_ids_and_span_coverage():
    snapped = {
        "cuts": [
            {
                "cut_id": "c1",
                "start_ms": 0,
                "end_ms": 30_000,
                "priority": "must_keep",
                "segment_id": "seg_001",
            },
            {
                "cut_id": "c2",
                "start_ms": 60_000,
                "end_ms": 90_000,
                "priority": "must_keep",
                "segment_id": "seg_002",
            },
        ]
    }
    cleaned = strip_provisional_segment_ids(snapped)
    assert all(not c.get("segment_id") for c in cleaned["cuts"])
    assert cut_span_coverage_ratio(snapped, 1_000_000) == 0.09
    assert cut_span_coverage_ratio(
        {
            "cuts": [
                {"start_ms": 0, "end_ms": 100_000},
                {"start_ms": 400_000, "end_ms": 500_000},
            ]
        },
        1_000_000,
    ) == 0.5


def test_redistribute_clustered_cuts_reaches_floor():
    from interview_mux.ideal_cuts import redistribute_clustered_cuts

    duration_ms = 3_000_000
    words = []
    t = 0
    while t < duration_ms:
        words.append({"word": "x", "start_ms": t, "end_ms": t + 400})
        t += 500
    out = redistribute_clustered_cuts(
        {
            "cuts": [
                {
                    "cut_id": "c1",
                    "talking_point_id": "tp_001",
                    "start_ms": 0,
                    "end_ms": 40_000,
                    "priority": "must_keep",
                    "rationale": "early",
                }
            ]
        },
        duration_ms,
        talking_points={
            "talking_points": [
                {"talking_point_id": "tp_001", "importance": "must_keep"}
            ]
        },
        transcript={"words": words},
        floor=0.45,
    )
    assert cut_span_coverage_ratio(out, duration_ms) >= 0.45
    assert any(str(c.get("cut_id") or "").startswith("cut_span_") for c in out["cuts"])


def test_spread_talking_point_time_hints_on_long_tape():
    from interview_mux.ideal_cuts import spread_talking_point_time_hints

    doc = spread_talking_point_time_hints(
        {
            "talking_points": [
                {"talking_point_id": "tp_001", "approx_time_hint_ms": 30_000},
                {"talking_point_id": "tp_002", "approx_time_hint_ms": 45_000},
                {"talking_point_id": "tp_003", "approx_time_hint_ms": 80_000},
            ]
        },
        3_000_000,
        floor=0.45,
    )
    hints = [int(p["approx_time_hint_ms"]) for p in doc["talking_points"]]
    assert (max(hints) - min(hints)) / 3_000_000 >= 0.45


def test_map_cuts_attaches_multi_overlap_segment_ids():
    snapped = {
        "cuts": [
            {
                "cut_id": "c1",
                "start_ms": 0,
                "end_ms": 90_000,
                "priority": "must_keep",
                "segment_id": "stale_seg",
            }
        ]
    }
    bounds = {
        "boundaries": [
            {"segment_id": "seg_001", "start_ms": 0, "end_ms": 60_000},
            {"segment_id": "seg_002", "start_ms": 60_000, "end_ms": 120_000},
        ]
    }
    mapped = map_cuts_onto_existing_boundaries(snapped, bounds, min_overlap_ms=500)
    cut = mapped["cuts"][0]
    assert cut["segment_id"] == "seg_001"
    assert cut["segment_ids"] == ["seg_001", "seg_002"]
    seed = selection_seed_from_snapped(mapped)
    assert seed["ordered_segment_ids"] == ["seg_001"]


def test_pick_best_order_penalizes_short_vs_brief():
    by_id = {
        f"seg_{i:03d}": {
            "segment_id": f"seg_{i:03d}",
            "start_ms": i * 10_000,
            "end_ms": (i + 1) * 10_000,
        }
        for i in range(1, 21)
    }
    short = [f"seg_{i:03d}" for i in range(1, 4)]
    long = [f"seg_{i:03d}" for i in range(1, 21)]
    pick = pick_best_order(
        [
            {"source": "narrative_chapters", "ordered_segment_ids": short},
            {"source": "ranking", "ordered_segment_ids": long},
        ],
        segments_by_id=by_id,
        brief_min_sec=150.0,
        brief_ideal_sec=200.0,
    )
    assert pick["winner"] == "ranking"
    assert len(pick["ordered_segment_ids"]) == 20


def test_editorial_qc_prose_detected():
    bad = (
        'Quickly — The single-word answer "Okay" makes no sense without the '
        "unheard prompt, then continue."
    )
    assert is_editorial_qc_prose(bad)
    errs = lint_spoken_text(bad, label="vo")
    assert any("spoken_editorial_qc_prose" in e for e in errs)
    assert not is_editorial_qc_prose("What was the turning point in that stretch?")


def test_spoken_internal_segment_references_are_blocked():
    bad_lines = [
        "And then — what happens as we get to 153?",
        "Where does 167 take this?",
        "Let us move to segment 204.",
        "That connects here — how does 208 follow from 205?",
        "Continue with seg_241.",
    ]
    for text in bad_lines:
        errs = lint_spoken_text(text, label="transition")
        assert any("spoken_internal_identifier" in err for err in errs), text

    assert lint_spoken_text(
        "Moving from fundraising constraints to the strategic sale, what changed?",
        label="transition",
    ) == []


def test_topic_forward_register_lint():
    from interview_mux.spoken_meta_lint import spoken_structure_hits

    assert "spoken_speaker_role_label" in spoken_structure_hits(
        "The host now explains the limitations of ctDNA-only analysis?"
    )
    assert "spoken_name_attribution" in spoken_structure_hits(
        "Utawar explains why OneCell is pursuing a different route."
    )
    assert "spoken_gendered_pronoun" in spoken_structure_hits(
        "Utawar says imaging may not detect a tumour. He closes with the access goal."
    )
    assert "spoken_name_attribution" not in spoken_structure_hits(
        "OneCell reports a 99.8 percent equivalency in an independent comparison."
    )
    assert spoken_structure_hits(
        "The next piece is cell biopsy — CTCs, not fragments alone."
    ) == []


def test_high_gap_seed_does_not_paste_confusion(tmp_path, monkeypatch):
    from interview_mux.artifact_repairs import _seed_missing_high_gap_interviewer_lines

    ctx = isolated_run_ctx(tmp_path, "exec_vo_seed")
    man = {
        "segments": [
            {
                "segment_id": "seg_004",
                "start_ms": 0,
                "end_ms": 8000,
                "text": "I was very sure if we kept building.",
                "speaker_id": "spk_0",
            }
        ]
    }
    path = ctx.path("segments", "manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(man), encoding="utf-8")
    _write_raw(
        ctx,
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_004",
                    "severity": "high",
                    "gap_type": "missing_followup",
                    "recommended_framing": "question",
                    "self_explanatory": False,
                    "listener_confusion": (
                        "Thought stops mid-sentence, so the listener never hears "
                        "the conclusion of his resistance to investors."
                    ),
                }
            ]
        },
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_prior_context.apply_prior_context_to_density_seed",
        lambda *a, **k: (
            "seg_004",
            "Building on that — what was the turning point in that stretch?",
            None,
            {"density_forced": True},
        ),
    )
    out: dict = {"interviewer_lines": []}
    applied: list = []
    _seed_missing_high_gap_interviewer_lines(
        ctx, out, manifest_ids={"seg_004"}, applied=applied
    )
    assert applied
    line = out["interviewer_lines"][0]
    assert "makes no sense" not in line["text"].lower()
    assert "mid-sentence" not in line["text"].lower()
    assert "Quickly" not in line["text"]
    assert "listener_confusion" in (line.get("extracted_from") or {})


def test_exclude_micro_strips_orphan_vo_pickup(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_orphan_vo")
    _write_raw(
        ctx,
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_002", "seg_003", "seg_004"],
            "excluded_segment_ids": [],
        },
    )
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_seed_seg_003",
                    "gap_type": "missing_question",
                    "line_category": "framing_question",
                    "text": "What was the turning point?",
                    "targets_segment_id": "seg_003",
                    "placement": "before",
                    "delivery": "synthesize",
                    "supports_segment_ids": ["seg_003"],
                }
            ]
        },
    )
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_002", "seg_003", "seg_004"],
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_002",
                    "source_start_ms": 0,
                    "source_end_ms": 5000,
                    "timeline_start_ms": 0,
                    "duration_ms": 5000,
                },
                {
                    "type": "vo_pickup",
                    "line_id": "vo_seed_seg_003",
                    "targets_segment_id": "seg_003",
                    "placement": "before",
                    "timeline_start_ms": 5000,
                    "duration_ms": 4000,
                    "source_path": "vo_pickup/synthesized/vo_seed_seg_003.wav",
                },
                {
                    "type": "speech",
                    "segment_id": "seg_003",
                    "source_start_ms": 5000,
                    "source_end_ms": 5200,
                    "timeline_start_ms": 9000,
                    "duration_ms": 200,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_004",
                    "source_start_ms": 5200,
                    "source_end_ms": 12000,
                    "timeline_start_ms": 9200,
                    "duration_ms": 6800,
                },
            ],
            "gap_placements": [
                {
                    "line_id": "vo_seed_seg_003",
                    "targets_segment_id": "seg_003",
                    "placement": "before",
                }
            ],
            "timeline_duration_ms": 16000,
        }
    )
    findings = [
        {
            "kind": "vo_micro",
            "severity": "critical",
            "segment_id": "seg_003",
            "action": "exclude_micro",
            "detail": {},
            "evidence": "micro Okay",
        }
    ]
    new_edl, applied, changed = apply_junction_repairs(ctx, edl, findings)
    assert changed
    assert not any(
        c.get("type") == "vo_pickup" and c.get("targets_segment_id") == "seg_003"
        for c in (new_edl.get("clips") or [])
    )
    assert any(a.get("action") == "strip_orphan_vo_pickup" for a in applied)
    gr = json.loads(ctx.path("understanding", "gap_report.json").read_text(encoding="utf-8"))
    assert not any(
        ln.get("line_id") == "vo_seed_seg_003" for ln in (gr.get("interviewer_lines") or [])
    )


def test_e2e_soft_flag_cannot_waive_nugget_retention(tmp_path, monkeypatch):
    from interview_mux.post_master_quality import evaluate_post_master_quality

    ctx = isolated_run_ctx(tmp_path, "exec_pmq_no_soft_nugget")
    master = ctx.path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF....")
    _write_raw(
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
    _write_raw(
        ctx,
        "master/render_ledger.json",
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "edl_hash": "x",
            "assembly": {"path": "master/assembly.wav"},
            "clips": [],
        },
    )
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {"residual_findings": [], "blocking_reasons": []},
    )
    _write_raw(
        ctx,
        "run_meta.json",
        {"e2e_soft_listen_delight": True, "e2e_soft_listenability": True},
    )
    _write_raw(
        ctx,
        "mastering/listen_delight_audit.json",
        {
            "version": 1,
            "mode": "authoritative",
            "blocking": True,
            "overall": 0.86,
            "overall_min": 0.90,
            "dimensions": {
                "nugget_retention": 0.4,
                "cut_integrity": 1.0,
                "conversation_fit": 0.95,
                "sonic_weave": 0.9,
                "mode_coherence": 1.0,
                "finishability": 0.93,
                "recommendability": 0.87,
            },
            "dimension_floors": {
                "nugget_retention": 0.80,
                "cut_integrity": 0.85,
                "conversation_fit": 0.85,
                "sonic_weave": 0.85,
                "mode_coherence": 0.80,
                "finishability": 0.80,
                "recommendability": 0.75,
            },
        },
    )
    segs = [
        {
            "segment_id": f"seg_{i:03d}",
            "start_ms": i * 30_000,
            "end_ms": (i + 1) * 30_000,
            "text": f"beat {i}",
        }
        for i in range(40)
    ]
    _write_raw(ctx, "segments/manifest.json", {"segments": segs})
    _write_raw(
        ctx,
        "master/selection.json",
        {"ordered_segment_ids": [s["segment_id"] for s in segs]},
    )
    _write_raw(
        ctx,
        "understanding/delivery_brief.json",
        {"target_duration_sec": {"min": 600, "ideal": 900, "max": 2000}},
    )
    monkeypatch.setattr(
        "interview_mux.post_master_quality.post_master_quality_cfg",
        lambda: {
            "block_on_feel_unavailable": True,
            "overall_min": 0.50,
            "dimension_floors": {},
        },
    )
    monkeypatch.setattr(
        "interview_mux.delivery_brief.delivery_brief_cfg",
        lambda cfg=None: {"enforce_duration": False},
    )
    quality = evaluate_post_master_quality(ctx)
    assert "listen_delight_floors" in quality["failed_checks"]
    detail = next(
        c["detail"] for c in quality["checks"] if c["check_id"] == "listen_delight_floors"
    )
    assert "nugget_retention" in (detail.get("hard_failed_dimensions") or [])
