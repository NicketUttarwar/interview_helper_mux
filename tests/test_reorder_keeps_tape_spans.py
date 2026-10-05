"""A reordered air order keeps every keeper on its own tape (ISSUES 178).

exec_025 aired seg_026, seg_025, seg_021: tape order 32:13, 31:39, 27:48. The
EDL builder floored seg_021's open at the previously aired clip's end (31:39),
past seg_021's own end; edge refine then seated it on seg_026's head words
("Okay. We do the whole genome"), the overlap trim shaved it, and the EDL lost
it while the selection kept it: the stage refused itself to the invoke cap.
The same mix-up capped a clip at an air-next keeper that starts earlier on
tape, collapsing it into a full-slab revert (10 to 15 minute clips, runs 22-24).
"""

from __future__ import annotations

from interview_mux.ideal_cuts import resolve_keeper_air_bounds
from interview_mux.stages.assembly import build_flow1_edl

# Real exec_025 words: the tail of seg_021 and the head of seg_026.
_EXEC025_WORDS = [
    ("can", 1710160, 1710420),
    ("become", 1710420, 1710780),
    ("a", 1710780, 1710900),
    ("companion", 1710900, 1711380),
    ("diagnostic.", 1711380, 1712040),
    ("Yes.", 1712260, 1712840),
    ("And", 1712840, 1713260),
    ("eventually", 1713260, 1713760),
    ("a", 1713760, 1714120),
    ("commercial", 1714120, 1714540),
    ("diagnostic", 1714540, 1715200),
    ("test.", 1715200, 1715720),
    ("Okay.", 1933820, 1934480),
    ("We", 1934820, 1935260),
    ("do", 1935260, 1935500),
    ("the", 1935500, 1935700),
    ("whole", 1935700, 1936000),
    ("genome,", 1936000, 1936420),
]
WORDS = [{"text": t, "start_ms": s, "end_ms": e} for t, s, e in _EXEC025_WORDS]


def _seg(sid: str, start: int, end: int, speaker: str) -> dict:
    return {"segment_id": sid, "start_ms": start, "end_ms": end, "speaker_id": speaker, "text": sid}


def test_resolver_ignores_a_previous_keeper_that_ends_after_this_one() -> None:
    start, end = resolve_keeper_air_bounds(
        source_start_ms=1_710_000,
        source_end_ms=1_716_080,
        words=WORDS,
        segment_id="seg_021",
        max_keep_ms=180_000,
        next_keeper_start_ms=2_122_380,
        prev_keeper_end_ms=1_933_460,
    )
    assert 1_709_000 <= start < 1_716_080
    assert end <= 1_717_100


def test_resolver_ignores_a_next_keeper_that_starts_before_this_one() -> None:
    toks = ("We sequence the tumour and report back. " * 120).split()
    words = [
        {"text": t, "start_ms": 50_000 + i * 350, "end_ms": 50_000 + i * 350 + 300}
        for i, t in enumerate(toks)
    ]
    start, end = resolve_keeper_air_bounds(
        source_start_ms=50_000,
        source_end_ms=400_000,
        words=words,
        segment_id="seg_long",
        max_keep_ms=180_000,
        next_keeper_start_ms=10_000,
    )
    assert start >= 49_000
    assert end - start <= 182_000


def test_reordered_edl_keeps_seg_021_on_its_own_tape() -> None:
    segs = {
        "seg_021": _seg("seg_021", 1_710_000, 1_716_080, "spk_1"),
        "seg_025": _seg("seg_025", 1_925_000, 1_933_460, "spk_1"),
        "seg_026": _seg("seg_026", 1_933_820, 1_937_000, "spk_0"),
        "seg_028": _seg("seg_028", 2_122_380, 2_130_000, "spk_1"),
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_026", "seg_025", "seg_021", "seg_028"]},
        segments_by_id=segs,
        transcript_words=WORDS,
        max_keeper_ms=180_000,
    )
    speech = {c["segment_id"]: c for c in edl["clips"] if c.get("type") == "speech"}
    assert set(speech) == set(segs)
    clip = speech["seg_021"]
    assert 1_709_000 <= clip["source_start_ms"] < 1_716_080
    assert clip["source_end_ms"] <= 1_717_100
    assert not edl.get("omitted_unplayable_segment_ids")
