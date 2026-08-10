"""Regression: native source-overlap loops, bridge hinge collision, mid-clause, overlong trim."""

from __future__ import annotations

import pytest

from interview_mux.bridge_completeness import assert_bridges_complete, stub_reorder_bridges
from interview_mux.edl_qc import validate_flow1_edl
from interview_mux.ideal_cuts import resolve_keeper_air_bounds
from interview_mux.junction_snip_qa import (
    SOURCE_OVERLAP_EPS_MS,
    apply_junction_repairs,
    detect_junction_findings,
)
from interview_mux.order_hash import stamp_order_hash
from interview_mux.run_context import RunContext
from interview_mux.seam_glue import default_bridge_text
from interview_mux.stages.assembly import build_flow1_edl
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


def _reverse_pair(after: str, before: str) -> dict:
    return {
        "after_segment_id": after,
        "before_segment_id": before,
        "kind": "reorder",
        "source_gap_ms": -50_000,
        "after_excerpt": "we put everything back into the company",
        "before_excerpt": "the cash in the bank was nearly gone",
    }


def test_default_bridge_dedupes_used_hinges() -> None:
    p1 = _reverse_pair("seg_029", "seg_030")
    p2 = _reverse_pair("seg_030", "seg_031")
    t1 = default_bridge_text(p1)
    t2 = default_bridge_text(p2, used_texts={t1})
    assert t1
    assert t2
    assert t1.strip().lower() != t2.strip().lower()


def test_bridge_completeness_threshold_two_identical() -> None:
    transitions = {
        "transitions": [
            {
                "after_segment_id": "seg_029",
                "before_segment_id": "seg_030",
                "text": "What had set that choice in motion?",
            },
            {
                "after_segment_id": "seg_030",
                "before_segment_id": "seg_031",
                "text": "What had set that choice in motion?",
            },
        ]
    }
    stubs = stub_reorder_bridges(None, transitions)
    assert any(s.get("reason") == "repeated_verbatim_text" for s in stubs)
    bridges = {
        "pairs": [
            {"after_id": "seg_029", "before_id": "seg_030", "kind": "reorder"},
            {"after_id": "seg_030", "before_id": "seg_031", "kind": "reorder"},
        ]
    }
    soft = assert_bridges_complete(bridges, transitions=transitions, soft=True)
    assert soft["complete"] is False
    assert soft["stub_count"] >= 2


def test_edl_qc_flags_overlapping_source_ranges(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_source_overlap", create=True)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a", start_ms=0, end_ms=10_000),
            minimal_manifest_segment("seg_b", start_ms=8_000, end_ms=20_000),
        ),
    )
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []})
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a", "seg_b"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 11_000,
                "timeline_start_ms": 0,
                "duration_ms": 11_000,
            },
            {
                "type": "speech",
                "segment_id": "seg_b",
                "source_start_ms": 8_000,
                "source_end_ms": 20_000,
                "timeline_start_ms": 11_000,
                "duration_ms": 12_000,
            },
        ],
        "timeline_duration_ms": 23_000,
    }
    errors = validate_flow1_edl(ctx, edl)
    assert any("Overlapping source range" in e for e in errors)


def test_junction_extend_clamped_before_next_speech(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_clamp_extend")
    segments = [
        {
            "segment_id": "seg_029",
            "start_ms": 100_000,
            "end_ms": 110_000,
            "speaker_id": "spk_0",
            "speaker_role": "interviewee",
            "type": "interviewee_answer",
            "text": "We put everything back into the company if",
            "topic_tags": [],
            "flags": [],
        },
        {
            "segment_id": "seg_030",
            "start_ms": 110_000,
            "end_ms": 120_000,
            "speaker_id": "spk_0",
            "speaker_role": "interviewee",
            "type": "interviewee_answer",
            "text": "we could raise the round. That was the turning point.",
            "topic_tags": [],
            "flags": [],
        },
        {
            "segment_id": "seg_031",
            "start_ms": 120_000,
            "end_ms": 130_000,
            "speaker_id": "spk_0",
            "speaker_role": "interviewee",
            "type": "interviewee_answer",
            "text": "And then the market opened up for us.",
            "topic_tags": [],
            "flags": [],
        },
    ]
    # Continuum words past seg_029 end into seg_030 — tempt an invading extend.
    words = []
    for i, tok in enumerate(
        "We put everything back into the company if we could raise the round.".split()
    ):
        start = 100_000 + i * 800
        words.append(
            {
                "text": tok if not tok.endswith(".") else tok,
                "start_ms": start,
                "end_ms": start + 700,
                "speaker_id": "spk_0",
            }
        )
    words[-1]["text"] = "round."
    ctx.write_json("segments/manifest.json", {"segments": segments}, skip_handoff=True)
    ctx.write_json("transcript/full.json", {"words": words}, skip_handoff=True)
    selection = stamp_order_hash(
        {
            "ordered_segment_ids": ["seg_029", "seg_030", "seg_031"],
            "chapters": [],
        }
    )
    ctx.write_json("master/selection.json", selection, skip_handoff=True)
    clips = [
        {
            "type": "speech",
            "segment_id": "seg_029",
            "source_start_ms": 100_000,
            "source_end_ms": 110_000,
            "timeline_start_ms": 0,
            "duration_ms": 10_000,
        },
        {
            "type": "speech",
            "segment_id": "seg_030",
            "source_start_ms": 110_000,
            "source_end_ms": 120_000,
            "timeline_start_ms": 10_000,
            "duration_ms": 10_000,
        },
        {
            "type": "speech",
            "segment_id": "seg_031",
            "source_start_ms": 120_000,
            "source_end_ms": 130_000,
            "timeline_start_ms": 20_000,
            "duration_ms": 10_000,
        },
    ]
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_029", "seg_030", "seg_031"],
            "clips": clips,
            "timeline_duration_ms": 30_000,
        }
    )
    findings = [
        {
            "kind": "on_a_roll",
            "severity": "critical",
            "segment_id": "seg_029",
            "action": "extend_later",
            "detail": {"recommended_ms": 118_000, "edge": "end"},
        }
    ]
    new_edl, applied, _ = apply_junction_repairs(ctx, edl, findings)
    speech = {
        c["segment_id"]: c
        for c in new_edl["clips"]
        if c.get("type") == "speech"
    }
    end_029 = int(speech["seg_029"]["source_end_ms"])
    start_030 = int(speech["seg_030"]["source_start_ms"])
    assert end_029 <= start_030 - SOURCE_OVERLAP_EPS_MS
    # No intersecting source ranges among the three keepers
    ranges = [
        (int(speech[s]["source_start_ms"]), int(speech[s]["source_end_ms"]))
        for s in ("seg_029", "seg_030", "seg_031")
    ]
    for i in range(len(ranges)):
        for j in range(i + 1, len(ranges)):
            a0, a1 = ranges[i]
            b0, b1 = ranges[j]
            assert not (a0 < b1 and b0 < a1)


def test_mid_clause_residual_not_soft_passable(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_mid_clause")
    segments = [
        {
            "segment_id": "seg_a",
            "start_ms": 0,
            "end_ms": 5_000,
            "speaker_id": "spk_0",
            "speaker_role": "interviewee",
            "type": "interviewee_answer",
            "text": "Because everything was put back into the company I was very sure if",
            "topic_tags": [],
            "flags": [],
        },
        {
            "segment_id": "seg_b",
            "start_ms": 20_000,
            "end_ms": 25_000,
            "speaker_id": "spk_1",
            "speaker_role": "interviewer",
            "type": "interviewer_question",
            "text": "What happened next?",
            "topic_tags": [],
            "flags": [],
        },
    ]
    words = []
    toks = "Because everything was put back into the company I was very sure if".split()
    for i, tok in enumerate(toks):
        words.append(
            {
                "text": tok,
                "start_ms": i * 400,
                "end_ms": i * 400 + 350,
                "speaker_id": "spk_0",
            }
        )
    ctx.write_json("segments/manifest.json", {"segments": segments}, skip_handoff=True)
    ctx.write_json("transcript/full.json", {"words": words}, skip_handoff=True)
    selection = stamp_order_hash(
        {"ordered_segment_ids": ["seg_a", "seg_b"], "chapters": []}
    )
    ctx.write_json("master/selection.json", selection, skip_handoff=True)
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_a", "seg_b"],
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_a",
                    "source_start_ms": 0,
                    "source_end_ms": 5_000,
                    "timeline_start_ms": 0,
                    "duration_ms": 5_000,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_b",
                    "source_start_ms": 20_000,
                    "source_end_ms": 25_000,
                    "timeline_start_ms": 5_000,
                    "duration_ms": 5_000,
                },
            ],
            "timeline_duration_ms": 10_000,
        }
    )
    findings = detect_junction_findings(ctx, edl)
    incomplete = [
        f
        for f in findings
        if f.get("kind") in {"on_a_roll", "incomplete_clause", "chapter_bleed_incomplete"}
    ]
    assert incomplete
    assert any(str(f.get("severity")) == "critical" for f in incomplete)
    # Soften path must leave unrecoverable / incomplete kinds critical for cut_integrity.
    for f in incomplete:
        detail = f.get("detail") if isinstance(f.get("detail"), dict) else {}
        if detail.get("recommended_ms") is None and f.get("action") != "merge_micro":
            assert detail.get("unrecoverable_within_clip") or f.get("severity") == "critical"


def test_overlong_keeper_uses_ideal_window_air_bounds() -> None:
    words = []
    # Sentence ends around 20s and 35s inside a 180s slab.
    for i, tok in enumerate(
        ("We started with almost nothing in the bank. " * 8).split()
    ):
        start = 10_000 + i * 300
        words.append({"text": tok, "start_ms": start, "end_ms": start + 280})
    cuts = {
        "cuts": [
            {
                "talking_point_id": "tp_1",
                "segment_id": "seg_long",
                "start_ms": 12_000,
                "end_ms": 40_000,
            }
        ]
    }
    start, end = resolve_keeper_air_bounds(
        source_start_ms=0,
        source_end_ms=180_000,
        cuts_doc=cuts,
        words=words,
        segment_id="seg_long",
        max_keep_ms=40_000,
    )
    assert start >= 12_000
    assert end <= 40_000
    assert end - start <= 40_000
    assert end - start >= 2_500

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_long"]},
        segments_by_id={
            "seg_long": {
                "segment_id": "seg_long",
                "start_ms": 0,
                "end_ms": 180_000,
                "speaker_id": "spk_0",
                "text": "long slab",
            }
        },
        ideal_cuts=cuts,
        transcript_words=words,
        max_keeper_ms=40_000,
    )
    speech = [c for c in edl["clips"] if c.get("type") == "speech"]
    assert len(speech) == 1
    assert int(speech[0]["source_start_ms"]) >= 12_000
    assert int(speech[0]["source_end_ms"]) <= 40_000
    assert int(speech[0]["duration_ms"]) == (
        int(speech[0]["source_end_ms"]) - int(speech[0]["source_start_ms"])
    )
