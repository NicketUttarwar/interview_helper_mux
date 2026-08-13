"""Semantic + acoustic edge refine for ideal native cuts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from interview_mux.cut_edge_refine import (
    exact_word_edges,
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
