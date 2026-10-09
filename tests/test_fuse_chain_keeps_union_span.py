"""Chained connector fuses must leave the survivor spanning the union.

On a real 6-minute run, two high-value clusters fused five rows into one in
two passes (seg_002+seg_003, seg_001+seg_002, then seg_004+seg_005,
seg_001+seg_004). The audit recorded the survivor at 0 to 357,370 ms, yet the
persisted manifest and boundaries row for seg_001 spanned 93,790 to 184,010:
another row's span under the survivor's id. Coverage fell to 25% and every
delivery stage refused the map as unsafe cuts.
"""

from __future__ import annotations

from interview_mux.run_context import RunContext
from interview_mux.segment_fuse import apply_connector_fuses
import pytest


@pytest.fixture
def ctx() -> RunContext:
    rid = "exec_902_20260101T000000Z"
    c = RunContext(rid, create=True)
    c.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return c

SPANS = [(0, 62300), (62300, 65700), (70790, 160890), (184010, 297010), (297010, 313510)]


def _rows():
    return [
        {"segment_id": f"seg_{i:03d}", "start_ms": a, "end_ms": b, "speaker_id": "spk_0", "speaker_role": "interviewee",
         "text": f"t{i}", "type": "interviewee_answer", "topic_tags": ["t"]}
        for i, (a, b) in enumerate(SPANS, 1)
    ]


def _verdict(a: str, b: str) -> dict:
    return {"pair_id": f"{a}__{b}", "earlier_segment_id": a, "later_segment_id": b,
            "decision": "fuse", "forced_by": "high_value_speech_island",
            "reason_code": "high_value_speech_neighbor", "rationale": "test", "confidence": 1.0}


def test_two_cluster_passes_keep_the_union_span(ctx: RunContext) -> None:
    ctx.write_json("segments/manifest.json", {"segments": _rows()})
    ctx.write_json("segments/boundaries.json", {"boundaries": [dict(r, proposed_split_reason="turn") for r in _rows()]})
    ctx.write_json("transcript/full.json", {"words": []})
    # cluster hvc_005 then hvc_007, each a fresh load from disk like the stage does
    apply_connector_fuses(ctx, [_verdict("seg_002", "seg_003"), _verdict("seg_001", "seg_002")], pass_id="p:hv_cluster:hvc_005")
    apply_connector_fuses(ctx, [_verdict("seg_004", "seg_005"), _verdict("seg_001", "seg_004")], pass_id="p:hv_cluster:hvc_007")
    man = ctx.read_json("segments/manifest.json")["segments"]
    bnd = ctx.read_json("segments/boundaries.json")["boundaries"]
    assert [s["segment_id"] for s in man] == ["seg_001"], man
    assert (man[0]["start_ms"], man[0]["end_ms"]) == (0, 313510), man[0]
    assert len(bnd) == 1 and (bnd[0]["start_ms"], bnd[0]["end_ms"]) == (0, 313510), bnd


def test_air_trim_after_fuse_keeps_source_boundaries(ctx: RunContext, monkeypatch) -> None:
    """The keeper trim lands in the manifest only; the boundary map keeps the union.

    Traced on a real 6-minute run: apply_connector_fuses wrote the fused seg_001 as
    (0, 90370); rerun_air_bounds_on_fused then rewrote it to (46270, 62280) in
    both files, and _assert_boundary_quality measured 25% coverage.
    """
    from interview_mux import segment_fuse as sf

    ctx.write_json("segments/manifest.json", {"segments": _rows()})
    ctx.write_json("segments/boundaries.json", {"boundaries": [dict(r, proposed_split_reason="turn") for r in _rows()]})
    ctx.write_json("transcript/full.json", {"words": []})
    sf.apply_connector_fuses(ctx, [_verdict("seg_001", "seg_002"), _verdict("seg_001", "seg_003")], pass_id="p:hv_cluster:c1")
    # A keeper trim well inside the fused slab, as ideal cuts would resolve it.
    monkeypatch.setattr(
        "interview_mux.ideal_cuts.resolve_keeper_air_bounds",
        lambda **kw: (46270, 62280),
    )
    out = sf.rerun_air_bounds_on_fused(ctx, fused_ids=["seg_001"], pass_id="p:hv_cluster:c1")
    assert out["trimmed"] == 1
    man = {s["segment_id"]: s for s in ctx.read_json("segments/manifest.json")["segments"]}
    bnd = {b["segment_id"]: b for b in ctx.read_json("segments/boundaries.json")["boundaries"]}
    assert (man["seg_001"]["start_ms"], man["seg_001"]["end_ms"]) == (46270, 62280), "manifest carries the trim"
    assert (bnd["seg_001"]["start_ms"], bnd["seg_001"]["end_ms"]) == (0, 160890), "boundaries keep the source union"


def _host_rows():
    rows = _rows()
    rows[1].update({"speaker_id": "spk_2", "speaker_role": "interviewer", "type": "interviewer_question"})
    return rows


def test_cross_speaker_island_fuse_never_swallows_the_host_question(ctx: RunContext) -> None:
    """On a real 6-minute run island_straddle fuses absorbed every host question row."""
    from interview_mux.segment_fuse import apply_connector_fuses

    ctx.write_json("segments/manifest.json", {"segments": _host_rows()})
    ctx.write_json("segments/boundaries.json", {"boundaries": [dict(r, proposed_split_reason="turn") for r in _host_rows()]})
    ctx.write_json("transcript/full.json", {"words": []})
    v = _verdict("seg_001", "seg_002"); v["forced_by"] = None
    v["reason_code"] = "island_straddle"; v["deterministic_hints"] = {"island_straddle": True}
    out = apply_connector_fuses(ctx, [v], pass_id="p:island")
    assert out.get("applied") == 0, out
    assert any(sk.get("reason") == "host_frame_protected" for sk in out.get("skipped") or []), out
    ids = [s["segment_id"] for s in ctx.read_json("segments/manifest.json")["segments"]]
    assert "seg_002" in ids


def test_concept_text_fuse_never_swallows_the_host_question(ctx: RunContext) -> None:
    from interview_mux.segment_fuse import apply_connector_fuses

    ctx.write_json("segments/manifest.json", {"segments": _host_rows()})
    ctx.write_json("segments/boundaries.json", {"boundaries": [dict(r, proposed_split_reason="turn") for r in _host_rows()]})
    ctx.write_json("transcript/full.json", {"words": []})
    v = _verdict("seg_001", "seg_002")
    v["forced_by"] = "concept_text"
    v["reason_code"] = "mid_sentence_continue"
    out = apply_connector_fuses(ctx, [v], pass_id="p:concept")
    assert out.get("applied") == 0, out
    assert any(sk.get("reason") == "host_frame_protected" for sk in out.get("skipped") or []), out
    ids = [s["segment_id"] for s in ctx.read_json("segments/manifest.json")["segments"]]
    assert "seg_002" in ids


def test_same_speaker_island_fuse_still_applies(ctx: RunContext) -> None:
    from interview_mux.segment_fuse import apply_connector_fuses

    ctx.write_json("segments/manifest.json", {"segments": _rows()})
    ctx.write_json("segments/boundaries.json", {"boundaries": [dict(r, proposed_split_reason="turn") for r in _rows()]})
    ctx.write_json("transcript/full.json", {"words": []})
    v = _verdict("seg_001", "seg_002"); v["forced_by"] = None
    v["reason_code"] = "island_straddle"; v["deterministic_hints"] = {"island_straddle": True}
    out = apply_connector_fuses(ctx, [v], pass_id="p:island")
    assert out.get("applied") == 1, out
