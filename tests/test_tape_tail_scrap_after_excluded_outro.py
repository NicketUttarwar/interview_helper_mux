"""A scrap after the tape's closing sponsor read never airs, whatever kept it (ISSUES 180).

exec_026: the closing sponsor read seg_032 (and its split pieces) was excluded,
so the live NLE view had no row for it; the tail check found no closing start
and flagged nothing. The undecodable last 5 s of tape (seg_033, "You are
listening to usHS\\ufffd bone...") was also hard-kept by the low-conf island
scan, and aired as the episode's last line.
"""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.media_ip_cta import _tape_tail_scrap_ids
from run_fixtures import isolated_run_ctx

GARBLE = "You most of the time, Michael. You are listening to usHS� bone and cut -edge on depression."


def _row(sid: str, s: int, e: int, text: str) -> dict:
    return {"segment_id": sid, "start_ms": s, "end_ms": e, "text": text}


def test_tail_scrap_found_when_the_live_view_lacks_the_excluded_sponsor_row() -> None:
    live = {
        "seg_030": _row("seg_030", 3_377_500, 3_501_900, "It's about the insurers."),
        "seg_033": _row("seg_033", 3_562_180, 3_567_460, GARBLE),
    }
    manifest = dict(live)
    manifest["seg_032"] = _row("seg_032", 3_506_320, 3_538_260, "Thanks again to our sponsor.")
    ordered = ["seg_030", "seg_033"]
    assert _tape_tail_scrap_ids(live, ordered, {"seg_032"}) == set()
    assert _tape_tail_scrap_ids(live, ordered, {"seg_032"}, manifest) == {"seg_033"}


def test_story_after_the_outro_is_not_a_scrap() -> None:
    live = {"seg_033": _row("seg_033", 3_562_180, 3_567_460, "And that is why early detection saves lives.")}
    manifest = dict(live, seg_032=_row("seg_032", 3_506_320, 3_538_260, "Thanks to our sponsor."))
    assert _tape_tail_scrap_ids(live, ["seg_033"], {"seg_032"}, manifest) == set()


def test_hard_keep_never_protects_a_post_outro_scrap(tmp_path: Path) -> None:
    from interview_mux.hard_keep import hard_keep_segment_ids

    ctx = isolated_run_ctx(tmp_path, "exec_tail_keep")
    rows = [
        _row("seg_030", 3_377_500, 3_501_900, "It's about the insurers and whether they reimburse."),
        _row("seg_032", 3_506_320, 3_538_260, "Thanks again to our sponsor, Agilisium Labs."),
        _row("seg_033", 3_562_180, 3_567_460, GARBLE),
    ]
    (ctx.run_dir / "segments").mkdir(exist_ok=True)
    (ctx.run_dir / "segments" / "manifest.json").write_text(
        json.dumps({"segments": [dict(r, speaker_id="spk_0") for r in rows]})
    )
    (ctx.run_dir / "master").mkdir(exist_ok=True)
    (ctx.run_dir / "master" / "selection.json").write_text(
        json.dumps(
            {
                "ordered_segment_ids": ["seg_030", "seg_033"],
                "excluded_segment_ids": [{"segment_id": "seg_032", "reason": "media_ip_cta"}],
            }
        )
    )
    (ctx.run_dir / "understanding").mkdir(exist_ok=True)
    (ctx.run_dir / "understanding" / "ideal_cuts.json").write_text(
        json.dumps({"must_keep_segment_ids": ["seg_030", "seg_033"], "cuts": []})
    )
    keeps = hard_keep_segment_ids(ctx)
    assert "seg_030" in keeps
    assert "seg_033" not in keeps


def test_include_excluded_view_keeps_nle_only_cta_children() -> None:
    from interview_mux.nle_state import apply_segments_with_nle

    segments = [_row("seg_032", 3_506_320, 3_538_260, "Thanks again to our sponsor.")]
    nle = {
        "segment_overrides": {
            "seg_032": {"excluded": True, "split_into": ["seg_032a", "seg_032g"]},
            "seg_032a": {"start_ms": 3_506_320, "end_ms": 3_509_100, "parent_id": "seg_032", "excluded": True},
            "seg_032g": {"start_ms": 3_530_000, "end_ms": 3_538_260, "parent_id": "seg_032"},
        }
    }
    live = {s["segment_id"] for s in apply_segments_with_nle(segments, nle)}
    every = {s["segment_id"] for s in apply_segments_with_nle(segments, nle, include_excluded=True)}
    assert live == {"seg_032g"}
    assert every == {"seg_032", "seg_032a", "seg_032g"}


def test_closing_tail_tape_end_counts_excluded_closing_rows() -> None:
    from interview_mux.media_ip_cta import _closing_outro_tail_ids

    # Parent seg_020 is mid-tape; the real tape end is an excluded outro row.
    live = {
        "seg_020a": _row("seg_020a", 100_000, 110_000, "story"),
        "seg_020c": _row("seg_020c", 115_000, 120_000, "more story after the read"),
    }
    every = dict(live, seg_099=_row("seg_099", 900_000, 960_000, "credits"))
    sel = {"excluded_segment_ids": [{"segment_id": "seg_020b", "reason": "media_ip_cta"}]}
    ordered = ["seg_020a", "seg_020c"]
    assert _closing_outro_tail_ids(live, ordered, {"seg_020"}, sel) == {"seg_020c"}
    assert _closing_outro_tail_ids(live, ordered, {"seg_020"}, sel, every) == set()
