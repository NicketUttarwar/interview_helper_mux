"""An accepted hanging end silences chapter_bleed_incomplete too (ISSUES 100, upstream exec_006)."""

from __future__ import annotations

import pytest
from run_fixtures import isolated_run_ctx

from interview_mux.junction_snip_qa import (
    detect_junction_findings,
    live_incomplete_cut_critical_findings,
)
from interview_mux.nle_state import load_nle, save_nle


def _seg(sid: str, start: int, end: int, text: str, spk: str = "spk_1") -> dict:
    return {
        "segment_id": sid,
        "start_ms": start,
        "end_ms": end,
        "text": text,
        "type": "interviewee_answer",
        "speaker_id": spk,
        "speaker_role": "interviewee",
        "topic_tags": ["t"],
    }


def _speech(sid: str, start: int, end: int) -> dict:
    return {
        "type": "speech",
        "segment_id": sid,
        "source_start_ms": start,
        "source_end_ms": end,
        "timeline_start_ms": 0,
        "duration_ms": end - start,
    }


def _words(text: str, start: int, spk: str) -> list[dict]:
    out, t = [], start
    for w in text.split():
        out.append({"word": w, "start_ms": t, "end_ms": t + 600, "speaker_id": spk})
        t += 700
    return out


@pytest.fixture
def bleed(tmp_path, monkeypatch):
    """seg_014 ends mid-thought on a chapter boundary; its neighbour is far away on tape."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_chapter_bleed_accept")
    a = "taking that industry forward to the third generation,"
    b = "So we built the next platform."
    edl = {
        "version": 1,
        "clips": [_speech("seg_014", 462_800, 469_580), _speech("seg_030", 600_000, 610_000)],
        "ordered_segment_ids": ["seg_014", "seg_030"],
        "timeline_duration_ms": 16_780,
    }
    ctx.write_json(
        "master/selection.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_014", "seg_030"],
            "excluded_segment_ids": [],
            "chapters": [
                {"chapter_id": "ch_01", "title": "a", "segment_ids": ["seg_014"]},
                {"chapter_id": "ch_02", "title": "b", "segment_ids": ["seg_030"]},
            ],
        },
        stage_key="selection_order_sanitize",
    )
    ctx.write_json(
        "segments/manifest.json",
        {"version": 1, "segments": [_seg("seg_014", 462_800, 469_580, a), _seg("seg_030", 600_000, 610_000, b, "spk_2")]},
        stage_key="segment_classification",
    )
    ctx.write_json(
        "transcript/full.json",
        {"version": 1, "words": _words(a, 462_800, "spk_1") + _words(b, 600_000, "spk_2")},
        stage_key="transcribe",
    )
    return ctx, edl


def _bleed_findings(ctx, edl):
    return [
        f
        for f in detect_junction_findings(ctx, edl)
        if f.get("segment_id") == "seg_014" and f.get("kind") == "chapter_bleed_incomplete"
    ]


def test_without_a_decision_the_bleed_is_critical(bleed) -> None:
    ctx, edl = bleed
    found = _bleed_findings(ctx, edl)
    assert found and found[0]["severity"] == "critical"
    assert not found[0]["detail"].get("accepted_hanging_end")


def test_an_accepted_hanging_end_makes_the_bleed_advisory_so_mix_can_seat(bleed) -> None:
    ctx, edl = bleed
    nle = load_nle(ctx)
    overrides = dict(nle.get("segment_overrides") or {})
    overrides["seg_014"] = {"accepted_hanging_end": "hard_keep_no_recut_no_fuse"}
    nle["segment_overrides"] = overrides
    save_nle(ctx, nle)

    found = _bleed_findings(ctx, edl)
    assert found and found[0]["severity"] == "advisory"
    assert found[0]["detail"].get("accepted_hanging_end") is True

    ctx.write_json("master/edl.json", edl, stage_key="edl")
    assert [
        f for f in live_incomplete_cut_critical_findings(ctx) if f.get("segment_id") == "seg_014"
    ] == []


def test_the_decision_covers_the_incomplete_clause_branch_too(bleed) -> None:
    """Same clip, same decision, no chapter join: the incomplete_clause ladder must also yield."""
    ctx, edl = bleed
    ctx.write_json(
        "master/selection.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_014", "seg_030"],
            "excluded_segment_ids": [],
            "chapters": [{"chapter_id": "ch_01", "title": "a", "segment_ids": ["seg_014", "seg_030"]}],
        },
        stage_key="selection_order_sanitize",
    )
    before = [
        f for f in detect_junction_findings(ctx, edl)
        if f.get("segment_id") == "seg_014" and f.get("severity") == "critical"
    ]
    assert before, "fixture must still raise a critical incomplete cut without the decision"

    nle = load_nle(ctx)
    overrides = dict(nle.get("segment_overrides") or {})
    overrides["seg_014"] = {"accepted_hanging_end": "hard_keep_no_recut_no_fuse"}
    nle["segment_overrides"] = overrides
    save_nle(ctx, nle)

    after = [
        f for f in detect_junction_findings(ctx, edl)
        if f.get("segment_id") == "seg_014" and f.get("severity") == "critical"
    ]
    assert after == []
