"""Semantic + acoustic edge refine for ideal native cuts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from interview_mux.cut_edge_refine import (
    exact_word_edges,
    pad_end_into_following_pause,
    refine_cut_edges,
    resolve_ms_from_anchor_text,
)
from interview_mux.gap_vo_prior_context import (
    clause_continues_before,
    ends_hanging_setup,
    is_legal_conceptual_open,
)
from interview_mux.ideal_cuts import (
    first_legal_open_start_ms,
    resolve_keeper_air_bounds,
    snap_ideal_cuts,
)


def _list_words() -> list[dict]:
    # "Amazon, Naturell, and WholeFoods completed the stack."
    toks = [
        ("Amazon,", 0, 180),
        ("Naturell,", 200, 380),
        ("and", 400, 480),
        ("WholeFoods", 500, 700),
        ("completed", 720, 900),
        ("the", 920, 1000),
        ("stack.", 1020, 1200),
    ]
    return [
        {"text": t, "start_ms": s, "end_ms": e, "speaker_id": "spk_0"}
        for t, s, e in toks
    ]


def test_pad_end_into_following_pause_midpoint() -> None:
    """Longitudinally-style: word end then 1.5s pause → cut at mid-pause."""
    words = [
        {"text": "16", "start_ms": 1455000, "end_ms": 1455200},
        {"text": "genes", "start_ms": 1455300, "end_ms": 1455600},
        {"text": "longitudinally.", "start_ms": 1456100, "end_ms": 1456720},
        {"text": "It's", "start_ms": 1458240, "end_ms": 1458740},
    ]
    assert pad_end_into_following_pause(1456720, words) == (1456720 + 1458240) // 2
    # Already in the pause → still canonicalize to midpoint.
    assert pad_end_into_following_pause(1457000, words) == (1456720 + 1458240) // 2


def test_pad_end_caps_long_gaps_at_one_second() -> None:
    words = [
        {"text": "done.", "start_ms": 0, "end_ms": 400},
        {"text": "Later", "start_ms": 5400, "end_ms": 5600},
    ]
    # Midpoint would be +2500ms; cap at +1000ms after the word.
    assert pad_end_into_following_pause(400, words) == 1400
    assert pad_end_into_following_pause(400, words, max_pad_ms=1000) == 1400


def test_pad_end_skips_tiny_or_abutting_gaps() -> None:
    words = [
        {"text": "hello", "start_ms": 0, "end_ms": 200},
        {"text": "world.", "start_ms": 220, "end_ms": 400},
    ]
    assert pad_end_into_following_pause(200, words) == 200


def test_refine_cut_edges_applies_pause_midpoint() -> None:
    words = [
        {"text": "done.", "start_ms": 100, "end_ms": 400},
        {"text": "Next", "start_ms": 1400, "end_ms": 1600},
    ]
    _s, end, meta = refine_cut_edges(
        start_ms=100,
        end_ms=400,
        words=words,
        wav_path=None,
        apply_exact_words=True,
        apply_acoustic=False,
    )
    assert end == (400 + 1400) // 2
    assert "pause_midpoint_end" in meta["steps"]


def test_and_yet_is_hanging_setup() -> None:
    assert ends_hanging_setup("we tried everything and yet")
    assert ends_hanging_setup("the fact that")
    assert not ends_hanging_setup("we tried everything and yet we won.")


def test_mid_list_open_is_illegal_and_walks_back() -> None:
    words = _list_words()
    # Late open on Naturell — Amazon dropped.
    start = words[1]["start_ms"]
    assert clause_continues_before(words, start)
    assert not is_legal_conceptual_open(
        "Naturell, and WholeFoods completed the stack.",
        words=words,
        start_ms=start,
    )
    fixed = first_legal_open_start_ms(
        words, from_ms=start, hard_floor_ms=0, hard_ceil_ms=1200
    )
    assert fixed == words[0]["start_ms"]


def test_snap_ideal_cuts_repairs_mid_list_open() -> None:
    words = _list_words()
    # Pad duration past min_cut_ms with trailing silence words.
    for i in range(8):
        t0 = 1400 + i * 500
        words.append(
            {
                "text": f"extra{i}.",
                "start_ms": t0,
                "end_ms": t0 + 400,
                "speaker_id": "spk_0",
            }
        )
    cuts = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "start_ms": words[1]["start_ms"],
                "end_ms": words[-1]["end_ms"],
                "priority": "must_keep",
                "rationale": "list proof",
                "start_anchor": "Naturell and WholeFoods",
            }
        ]
    }
    snapped = snap_ideal_cuts(
        cuts,
        {"words": words},
        cfg={
            "analysis": {
                "ideal_cuts": {
                    "min_cut_ms": 800,
                    "acoustic_edge_refine": False,
                    "word_snap_max_shift_ms": 80,
                }
            }
        },
    )
    assert snapped["cut_count"] == 1
    assert snapped["cuts"][0]["start_ms"] == words[0]["start_ms"]
    assert any("illegal open" in w for w in snapped.get("snap_warnings") or [])


def test_snap_uses_end_anchor_and_rejects_and_yet() -> None:
    toks = "we tried everything and yet we kept going until the win.".split()
    words = []
    t = 0
    for tok in toks:
        words.append({"text": tok, "start_ms": t, "end_ms": t + 180, "speaker_id": "spk_0"})
        t += 200
    # Hang on "yet"
    yet_end = words[4]["end_ms"]
    cuts = {
        "cuts": [
            {
                "cut_id": "c1",
                "talking_point_id": "tp_1",
                "start_ms": 0,
                "end_ms": yet_end,
                "priority": "must_keep",
                "rationale": "hang",
                "end_anchor": "and yet",
            }
        ]
    }
    snapped = snap_ideal_cuts(
        cuts,
        {"words": words},
        cfg={
            "analysis": {
                "ideal_cuts": {
                    "min_cut_ms": 800,
                    "acoustic_edge_refine": False,
                    "semantic_edge_buffer_ms": 8_000,
                }
            }
        },
    )
    assert snapped["cut_count"] == 1
    assert snapped["cuts"][0]["end_ms"] > yet_end
    last = [
        w["text"]
        for w in words
        if int(w["end_ms"]) <= snapped["cuts"][0]["end_ms"]
    ][-1]
    assert last.lower().rstrip(".,!?") != "yet"


def test_anchor_text_resolves_near_approx() -> None:
    words = _list_words()
    ms = resolve_ms_from_anchor_text(
        words, "Amazon Naturell", approx_ms=50, prefer="start"
    )
    assert ms == 0
    ms_end = resolve_ms_from_anchor_text(
        words, "completed the stack", approx_ms=1100, prefer="end"
    )
    assert ms_end == words[-1]["end_ms"]


def test_exact_word_edges_no_margin() -> None:
    words = _list_words()
    s, e = exact_word_edges(words, 0, 1200)
    assert s == 0
    assert e == words[-1]["end_ms"]
    # Mid-word open must not steal the previous word start.
    s2, _e2 = exact_word_edges(words, 210, 1100)
    assert s2 == 210
    assert s2 > words[0]["end_ms"]


def test_exact_word_edges_completes_straddling_last_word() -> None:
    """Turn-cap mid last word must finish that word, not snap back to 'the'."""
    from interview_mux.cut_edge_refine import outgoing_last_word_end_ms

    words = [
        {"text": "treatments", "start_ms": 80740, "end_ms": 81680, "speaker_id": "spk_0"},
        {"text": "by", "start_ms": 81680, "end_ms": 82260, "speaker_id": "spk_0"},
        {"text": "the", "start_ms": 82260, "end_ms": 82460, "speaker_id": "spk_0"},
        {"text": "ecologists.", "start_ms": 82460, "end_ms": 83020, "speaker_id": "spk_0"},
        {"text": "And", "start_ms": 83740, "end_ms": 84300, "speaker_id": "spk_1"},
    ]
    # next_start 83070 → soft cap 82990 lands inside "ecologists."
    owned = outgoing_last_word_end_ms(
        words,
        clip_start_ms=74810,
        proposed_end_ms=82990,
        next_keeper_start_ms=83070,
        speaker_id="spk_0",
    )
    assert owned == 83020
    _s, e = exact_word_edges(words, 74810, 82990)
    assert e == 83020
    # Incoming other-speaker word near the cap must not be stolen.
    owned_next = outgoing_last_word_end_ms(
        words,
        clip_start_ms=74810,
        proposed_end_ms=82990,
        next_keeper_start_ms=83070,
        speaker_id="spk_0",
    )
    assert owned_next != 84300


def test_air_bounds_turn_cap_keeps_outgoing_last_word() -> None:
    """Reproduce exec_1071 seg_003e: disjoint cap + edge snap dropped 'oncologists'."""
    words = [
        {"text": "But", "start_ms": 74960, "end_ms": 75560, "speaker_id": "spk_0"},
        {"text": "this", "start_ms": 76560, "end_ms": 76720, "speaker_id": "spk_0"},
        {"text": "platform", "start_ms": 76720, "end_ms": 77180, "speaker_id": "spk_0"},
        {"text": "can", "start_ms": 77180, "end_ms": 77840, "speaker_id": "spk_0"},
        {"text": "provide", "start_ms": 78700, "end_ms": 79020, "speaker_id": "spk_0"},
        {"text": "earlier", "start_ms": 79020, "end_ms": 79420, "speaker_id": "spk_0"},
        {"text": "diagnosis", "start_ms": 79420, "end_ms": 79980, "speaker_id": "spk_0"},
        {"text": "and", "start_ms": 79980, "end_ms": 80400, "speaker_id": "spk_0"},
        {"text": "guide", "start_ms": 80400, "end_ms": 80740, "speaker_id": "spk_0"},
        {"text": "personalized", "start_ms": 80740, "end_ms": 81160, "speaker_id": "spk_0"},
        {"text": "treatments", "start_ms": 81160, "end_ms": 81680, "speaker_id": "spk_0"},
        {"text": "by", "start_ms": 81680, "end_ms": 82260, "speaker_id": "spk_0"},
        {"text": "the", "start_ms": 82260, "end_ms": 82460, "speaker_id": "spk_0"},
        {"text": "ecologists.", "start_ms": 82460, "end_ms": 83020, "speaker_id": "spk_0"},
        {"text": "And", "start_ms": 83740, "end_ms": 84300, "speaker_id": "spk_1"},
        {"text": "what", "start_ms": 84300, "end_ms": 84840, "speaker_id": "spk_1"},
    ]
    meta: dict = {}
    _s, e = resolve_keeper_air_bounds(
        source_start_ms=74810,
        source_end_ms=83070,
        words=words,
        min_keep_ms=800,
        next_keeper_start_ms=83070,
        meta_out=meta,
    )
    assert e >= 83020
    assert e < 83740
    last = [
        str(w["text"]).lower().rstrip(".,!?")
        for w in words
        if int(w["end_ms"]) <= e and w.get("speaker_id") == "spk_0"
    ][-1]
    assert last == "ecologists"
    reason = str(meta.get("air_bound_reason") or "")
    assert "outgoing_last_word" in reason or e <= 83070


def test_air_bounds_hanging_tail_keeps_through_nearby_turn_without_stt_word() -> None:
    """If STT dropped the last word, do not snap back off 'by the' at a turn."""
    words = [
        {"text": "provide", "start_ms": 78700, "end_ms": 79020, "speaker_id": "spk_0"},
        {"text": "earlier", "start_ms": 79020, "end_ms": 79420, "speaker_id": "spk_0"},
        {"text": "diagnosis", "start_ms": 79420, "end_ms": 79980, "speaker_id": "spk_0"},
        {"text": "and", "start_ms": 79980, "end_ms": 80400, "speaker_id": "spk_0"},
        {"text": "guide", "start_ms": 80400, "end_ms": 80740, "speaker_id": "spk_0"},
        {"text": "personalized", "start_ms": 80740, "end_ms": 81160, "speaker_id": "spk_0"},
        {"text": "treatments", "start_ms": 81160, "end_ms": 81680, "speaker_id": "spk_0"},
        {"text": "by", "start_ms": 81680, "end_ms": 82260, "speaker_id": "spk_0"},
        {"text": "the", "start_ms": 82260, "end_ms": 82460, "speaker_id": "spk_0"},
        {"text": "And", "start_ms": 83740, "end_ms": 84300, "speaker_id": "spk_1"},
    ]
    meta: dict = {}
    _s, e = resolve_keeper_air_bounds(
        source_start_ms=74810,
        source_end_ms=82_460,
        words=words,
        min_keep_ms=800,
        next_keeper_start_ms=83_070,
        meta_out=meta,
    )
    assert e >= 83_070
    last = [
        str(w["text"]).lower().rstrip(".,!?")
        for w in words
        if int(w["end_ms"]) <= e and w.get("speaker_id") == "spk_0"
    ][-1]
    assert last == "the"


def test_acoustic_refine_nudges_into_silence(tmp_path: Path) -> None:
    # 1.4s mono: speech-ish noise 200–1000ms, silence elsewhere.
    sr = 16_000
    n = int(sr * 1.4)
    audio = np.zeros(n, dtype=np.float32)
    speech = slice(int(0.2 * sr), int(1.0 * sr))
    rng = np.random.default_rng(0)
    audio[speech] = 0.2 * rng.standard_normal(speech.stop - speech.start).astype(np.float32)
    wav = tmp_path / "norm.wav"
    sf.write(str(wav), audio, sr)

    words = [
        {"text": "hello", "start_ms": 200, "end_ms": 500},
        {"text": "world.", "start_ms": 520, "end_ms": 900},
    ]
    start, end, meta = refine_cut_edges(
        start_ms=200,
        end_ms=900,
        words=words,
        wav_path=wav,
        search_ms=150,
        apply_exact_words=True,
        apply_acoustic=True,
    )
    assert start <= 200
    assert end >= 900
    assert "exact_word_edges" in meta["steps"]


def test_air_bounds_repairs_and_yet_end() -> None:
    toks = "we tried everything and yet we kept going until the win.".split()
    words = []
    t = 0
    for tok in toks:
        words.append({"text": tok, "start_ms": t, "end_ms": t + 180})
        t += 200
    yet_end = words[4]["end_ms"]
    _s, e = resolve_keeper_air_bounds(
        source_start_ms=0,
        source_end_ms=yet_end,
        words=words,
        min_keep_ms=800,
        max_extend_ms=8_000,
    )
    assert e > yet_end
