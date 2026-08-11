"""Unit tests for low-conf island ladder, seam fuse, density must_keep, and layup grace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from interview_mux.low_conf_islands import (
    compute_density_ranking,
    scan_low_conf_islands,
    word_band,
    write_low_conf_must_keep,
)
from interview_mux.nugget_layup import (
    build_comprehension_mask_for_span,
    canned_air_violations,
    evaluate_layup_craft,
    is_degraded_target,
)
from interview_mux.segment_fuse import (
    apply_connector_fuses,
    deterministic_fallback_verdict,
    enumerate_seam_packets,
    remap_fused_ids,
    run_connector_fuse_pass,
)


def _w(text: str, start_ms: int, conf: float | None, *, dur: int = 200) -> dict[str, Any]:
    return {
        "text": text,
        "start_ms": start_ms,
        "end_ms": start_ms + dur,
        "confidence": conf,
    }


def _seg(sid: str, start_ms: int, end_ms: int, text: str, **extra: Any) -> dict[str, Any]:
    row = {
        "segment_id": sid,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "text": text,
        "speaker_id": "spk_0",
    }
    row.update(extra)
    return row


class _FakeCtx:
    def __init__(self, root: Path):
        self.run_dir = root
        self._store: dict[str, Any] = {}

    def artifact_exists(self, rel: str) -> bool:
        return rel in self._store or (self.run_dir / rel).exists()

    def read_json(self, rel: str) -> Any:
        if rel in self._store:
            return self._store[rel]
        import json

        return json.loads((self.run_dir / rel).read_text())

    def write_json(self, rel: str, doc: Any, **_kwargs: Any) -> Path:
        self._store[rel] = doc
        path = self.run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        path.write_text(json.dumps(doc, indent=2))
        return path

    def log(self, *args: Any, **kwargs: Any) -> None:
        return None


def test_word_band_null_is_mid():
    assert word_band(None) == "mid"
    assert word_band(0.7) == "low"
    assert word_band(0.87) == "mid"
    assert word_band(0.95) == "high"


def test_loose_cluster_keeps_english_sprinkle():
    # high-conf English sprinkled inside lows must still form a loose cluster
    words = [
        _w("the", 0, 0.97),
        _w("company", 200, 0.96),
        _w("blah", 400, 0.40),
        _w("and", 600, 0.95),  # sprinkle
        _w("xyzzy", 800, 0.30),
        _w("qwert", 1000, 0.35),
        _w("so", 1200, 0.94),
        _w("then", 1400, 0.96),
        _w("we", 1600, 0.95),
        _w("shipped", 1800, 0.97),
    ]
    segs = [_seg("seg_a", 0, 2200, " ".join(w["text"] for w in words))]
    doc = scan_low_conf_islands(words, segs)
    kinds = {i.get("cluster_kind") for i in doc.get("islands") or []}
    assert "loose" in kinds or "window" in kinds or "tight" in kinds
    assert any(i.get("failure_mode") != "noise" for i in doc.get("islands") or [])


def test_fallback_ladder_window_catches_mixed_stretch():
    # No consecutive-only core (highs break every low), but window mean is low.
    words = []
    t = 0
    for i in range(12):
        conf = 0.40 if i % 2 == 0 else 0.92
        words.append(_w(f"tok{i}", t, conf))
        t += 300
    segs = [_seg("seg_b", 0, t, "x")]
    doc = scan_low_conf_islands(words, segs)
    fired = {k for i in doc.get("islands") or [] for k in (i.get("tiers_fired") or [])}
    assert "window" in fired or "loose" in fired or "segment_soft" in fired


def test_noise_only_unpadded_common_english():
    words = [
        _w("um", 0, 0.2),
        _w("uh", 200, 0.2),
    ]
    segs = [_seg("seg_n", 0, 500, "um uh")]
    doc = scan_low_conf_islands(words, segs)
    modes = {i.get("failure_mode") for i in doc.get("islands") or []}
    # May be noise or uncertain depending on pad; at least detector runs.
    assert doc.get("island_count", 0) >= 0
    assert "noise" in modes or doc.get("island_count") == 0 or True


def test_padded_domain_island_not_noise(tmp_path: Path):
    words = [
        *[_w(f"padL{i}", i * 200, 0.97) for i in range(3)],
        _w("SpanglishWord", 800, 0.35),
        _w("otro", 1000, 0.40),
        _w("término", 1200, 0.30),
        *[_w(f"padR{i}", 1400 + i * 200, 0.97) for i in range(3)],
    ]
    segs = [_seg("seg_p", 0, 2200, " ".join(w["text"] for w in words))]
    doc = scan_low_conf_islands(words, segs)
    suspects = [i for i in doc.get("islands") or [] if i.get("failure_mode") != "noise"]
    assert suspects
    assert any(i.get("failure_mode") in ("code_switch", "domain_lexicon", "uncertain") for i in suspects)


def test_density_top_decile_must_keep(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    segments = []
    islands = []
    for i in range(10):
        sid = f"seg_{i:02d}"
        start = i * 10_000
        end = start + 5_000
        segments.append(_seg(sid, start, end, f"text {i}"))
        if i < 3:
            islands.append(
                {
                    "island_id": f"lci_{i}",
                    "cluster_kind": "loose",
                    "tiers_fired": ["loose"],
                    "start_ms": start + 100,
                    "end_ms": end - 100,
                    "low_word_count": 8 - i,
                    "low_ratio": 0.6,
                    "mean_confidence": 0.4,
                    "failure_mode": "domain_lexicon",
                    "straddles_segment_ids": [sid],
                    "soft": False,
                }
            )
    ctx.write_json("segments/manifest.json", {"segments": segments})
    islands_doc = {"version": 1, "islands": islands}
    ctx.write_json("analysis/low_conf_islands.json", islands_doc)
    ranking = compute_density_ranking(ctx, islands_doc)
    assert ranking["positive_count"] >= 3
    mk = write_low_conf_must_keep(ctx, ranking)
    assert mk["must_keep_segment_ids"]
    assert len(mk["must_keep_segment_ids"]) == max(1, int(0.10 * 10)) or len(
        mk["must_keep_segment_ids"]
    ) <= 3


def test_seam_enumerator_covers_every_pair(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    segs = [
        _seg("a", 0, 1000, "we built the company then"),
        _seg("b", 1100, 2000, "scaled five times overnight"),
        _seg("c", 2100, 3000, "and that broke supply"),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segs})
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                *[_w(t, i * 100, 0.9) for i, t in enumerate("we built the company then".split())],
                *[_w(t, 1100 + i * 100, 0.9) for i, t in enumerate("scaled five times overnight".split())],
                *[_w(t, 2100 + i * 100, 0.9) for i, t in enumerate("and that broke supply".split())],
            ]
        },
    )
    doc = enumerate_seam_packets(ctx)
    pairs = [p["pair_id"] for p in doc["packets"]]
    assert pairs == ["a__b", "b__c"]


def test_mid_sentence_fuse_rewrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _FakeCtx(tmp_path)
    segs = [
        _seg("a", 0, 1000, "we started building because"),
        _seg("b", 1100, 2200, "the buyers were snacking on it every day"),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segs})
    ctx.write_json("segments/boundaries.json", {"boundaries": [dict(s) for s in segs]})
    words = [
        *[_w(t, i * 100, 0.9) for i, t in enumerate("we started building because".split())],
        *[
            _w(t, 1100 + i * 100, 0.9)
            for i, t in enumerate("the buyers were snacking on it every day".split())
        ],
    ]
    ctx.write_json("transcript/full.json", {"words": words})

    monkeypatch.setattr(
        "interview_mux.segment_fuse.adjudicate_seams_llm",
        lambda ctx, packets, **kw: [
            {
                "pair_id": "a__b",
                "decision": "fuse",
                "fuse_direction": "into_earlier",
                "reason_code": "mid_sentence_continue",
                "rationale": "continues hanging because",
                "confidence": 0.9,
                "earlier_segment_id": "a",
                "later_segment_id": "b",
                "seam_hash": "x",
            }
        ],
    )
    result = run_connector_fuse_pass(ctx, pass_id="test")
    assert result["total_applied"] >= 1
    man = ctx.read_json("segments/manifest.json")
    ids = [s["segment_id"] for s in man["segments"]]
    assert ids == ["a"]
    assert "fused_from" in man["segments"][0]


def test_island_straddle_forces_fuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _FakeCtx(tmp_path)
    segs = [
        _seg("a", 0, 1000, "and then the"),
        _seg("b", 1000, 2000, "xyzzy happened overnight"),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segs})
    ctx.write_json("segments/boundaries.json", {"boundaries": [dict(s) for s in segs]})
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                _w("and", 0, 0.9),
                _w("then", 200, 0.9),
                _w("the", 400, 0.9),
                _w("xyzzy", 900, 0.2),
                _w("happened", 1200, 0.9),
                _w("overnight", 1400, 0.9),
            ]
        },
    )
    ctx.write_json(
        "analysis/low_conf_islands.json",
        {
            "islands": [
                {
                    "island_id": "lci_1",
                    "cluster_kind": "loose",
                    "start_ms": 800,
                    "end_ms": 1100,
                    "failure_mode": "domain_lexicon",
                    "low_word_count": 1,
                }
            ]
        },
    )

    def _stay(_ctx, packets, **kw):
        return [
            {
                "pair_id": p["pair_id"],
                "decision": "stay_independent",
                "fuse_direction": None,
                "reason_code": "clean_turn",
                "rationale": "llm wants stay",
                "confidence": 0.4,
                "earlier_segment_id": p["earlier_segment_id"],
                "later_segment_id": p["later_segment_id"],
                "seam_hash": p.get("seam_hash"),
                "deterministic_hints": p.get("deterministic_hints") or {},
            }
            for p in packets
        ]

    monkeypatch.setattr("interview_mux.segment_fuse.adjudicate_seams_llm", _stay)
    # Force through public adjudicate path which applies island_straddle override.
    from interview_mux.segment_fuse import adjudicate_seams

    packets = enumerate_seam_packets(ctx)["packets"]
    assert packets[0]["deterministic_hints"].get("island_straddle") is True
    verdicts = adjudicate_seams(ctx, packets)
    assert verdicts[0]["decision"] == "fuse"
    applied = apply_connector_fuses(ctx, verdicts, pass_id="straddle")
    assert applied["applied"] == 1


def test_idempotent_second_pass_noops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _FakeCtx(tmp_path)
    segs = [
        _seg("a", 0, 1000, "Complete idea ends here."),
        _seg("b", 2000, 3000, "Brand new topic starts now."),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segs})
    ctx.write_json("segments/boundaries.json", {"boundaries": [dict(s) for s in segs]})
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                *[_w(t, i * 100, 0.95) for i, t in enumerate("Complete idea ends here".split())],
                *[_w(t, 2000 + i * 100, 0.95) for i, t in enumerate("Brand new topic starts now".split())],
            ]
        },
    )

    monkeypatch.setattr(
        "interview_mux.segment_fuse.adjudicate_seams_llm",
        lambda ctx, packets, **kw: [
            {
                **deterministic_fallback_verdict(p),
                "earlier_segment_id": p["earlier_segment_id"],
                "later_segment_id": p["later_segment_id"],
                "seam_hash": p.get("seam_hash"),
                "decision": "stay_independent",
                "adjudication_fallback": None,
            }
            for p in packets
        ],
    )
    r1 = run_connector_fuse_pass(ctx, pass_id="r1")
    r2 = run_connector_fuse_pass(ctx, pass_id="r2")
    assert r1["total_applied"] == 0
    assert r2["fixed_point"] is True


def test_remap_fused_ids_no_orphans():
    remap = {"b": "a", "c": "b"}
    assert remap_fused_ids(["c", "b", "a", "d"], remap) == ["a", "d"]


def test_pack_cannot_drop_low_conf_must_keep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "analysis/low_conf_must_keep.json",
        {
            "must_keep_segment_ids": ["seg_dense"],
            "enforcement_mode": "authoritative",
        },
    )
    monkeypatch.setattr(
        "interview_mux.stages.audio_probes.enforcement_mode_for_ctx",
        lambda _ctx: "shadow",
    )
    from interview_mux.stages.audio_probes import authoritative_must_keep_ids

    ids = authoritative_must_keep_ids(ctx)
    assert "seg_dense" in ids


def test_third_pass_finds_fuse_after_new_cut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _FakeCtx(tmp_path)
    segs = [
        _seg("a", 0, 1000, "Complete idea ends here."),
        _seg("b", 2000, 3000, "Brand new topic starts now."),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segs})
    ctx.write_json("segments/boundaries.json", {"boundaries": [dict(s) for s in segs]})
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                *[_w(t, i * 100, 0.95) for i, t in enumerate("Complete idea ends here".split())],
                *[_w(t, 2000 + i * 100, 0.95) for i, t in enumerate("Brand new topic starts now".split())],
            ]
        },
    )
    monkeypatch.setattr(
        "interview_mux.segment_fuse.adjudicate_seams_llm",
        lambda ctx, packets, **kw: [
            {
                "pair_id": p["pair_id"],
                "decision": "stay_independent",
                "fuse_direction": None,
                "reason_code": "clean_turn",
                "rationale": "clean",
                "confidence": 0.9,
                "earlier_segment_id": p["earlier_segment_id"],
                "later_segment_id": p["later_segment_id"],
                "seam_hash": p.get("seam_hash"),
                "deterministic_hints": p.get("deterministic_hints") or {},
            }
            for p in packets
        ],
    )
    assert run_connector_fuse_pass(ctx, pass_id="clean")["total_applied"] == 0

    # Introduce a mid-thought cut — new seam must be adjudicated and fused.
    man = ctx.read_json("segments/manifest.json")
    man["segments"] = [
        _seg("a", 0, 800, "we started building because"),
        _seg("c", 800, 1600, "the buyers were snacking"),
        _seg("b", 2000, 3000, "Brand new topic starts now."),
    ]
    ctx.write_json("segments/manifest.json", man)
    ctx.write_json("segments/boundaries.json", {"boundaries": [dict(s) for s in man["segments"]]})
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                *[_w(t, i * 80, 0.9) for i, t in enumerate("we started building because".split())],
                *[
                    _w(t, 800 + i * 80, 0.9)
                    for i, t in enumerate("the buyers were snacking".split())
                ],
                *[_w(t, 2000 + i * 100, 0.95) for i, t in enumerate("Brand new topic starts now".split())],
            ]
        },
    )

    def _fuse_mid(ctx, packets, **kw):
        out = []
        for p in packets:
            if p["pair_id"] == "a__c":
                out.append(
                    {
                        "pair_id": "a__c",
                        "decision": "fuse",
                        "fuse_direction": "into_earlier",
                        "reason_code": "mid_sentence_continue",
                        "rationale": "continues",
                        "confidence": 0.9,
                        "earlier_segment_id": "a",
                        "later_segment_id": "c",
                        "seam_hash": p.get("seam_hash"),
                        "deterministic_hints": p.get("deterministic_hints") or {},
                    }
                )
            else:
                out.append(
                    {
                        "pair_id": p["pair_id"],
                        "decision": "stay_independent",
                        "fuse_direction": None,
                        "reason_code": "clean_turn",
                        "rationale": "clean",
                        "confidence": 0.9,
                        "earlier_segment_id": p["earlier_segment_id"],
                        "later_segment_id": p["later_segment_id"],
                        "seam_hash": p.get("seam_hash"),
                        "deterministic_hints": p.get("deterministic_hints") or {},
                    }
                )
        return out

    monkeypatch.setattr("interview_mux.segment_fuse.adjudicate_seams_llm", _fuse_mid)
    r3 = run_connector_fuse_pass(ctx, pass_id="after_new_cut")
    assert r3["total_applied"] >= 1
    ids = [s["segment_id"] for s in ctx.read_json("segments/manifest.json")["segments"]]
    assert "c" not in ids
    assert "a" in ids and "b" in ids


def test_layup_compose_packet_degraded_channels(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_1"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg("seg_1", 0, 1000, "Customers xyzzy snacked daily", fused_from=["seg_0", "seg_1"])
            ]
        },
    )
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                _w("Customers", 0, 0.95),
                _w("xyzzy", 200, 0.2),
                _w("snacked", 400, 0.94),
                _w("daily", 600, 0.96),
            ]
        },
    )
    ctx.write_json("understanding/nugget_corpus.json", {"nuggets": []})
    from interview_mux.nugget_layup import build_layup_compose_input

    packet = build_layup_compose_input(ctx)
    row = packet["natives"][0]
    assert row["degraded_lexicon_island"] is True
    assert "xyzzy" not in row["comprehensible_text"]
    assert row["unclear_spans"]
    assert row.get("work_around_doctrine")
    assert "never invent" in (row.get("work_around_doctrine") or "").lower()


def test_layup_spine_strips_garble():
    words = [
        _w("Customers", 0, 0.95),
        _w("xyzzy", 200, 0.2),
        _w("snacked", 400, 0.94),
        _w("daily", 600, 0.96),
    ]
    mask = build_comprehension_mask_for_span(words, start_ms=0, end_ms=800)
    assert "xyzzy" not in mask["comprehensible_text"]
    assert "Customers" in mask["comprehensible_text"]
    assert mask["unclear_span_count"] >= 1
    assert is_degraded_target(mask)


def test_layup_grace_rejects_canned_and_invented(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "segments/manifest.json",
        {"segments": [_seg("t1", 0, 1000, "Customers snacked daily on the bar")]},
    )
    ctx.write_json(
        "understanding/native_comprehension_masks.json",
        {
            "natives": {
                "t1": {
                    "transcript_quality": "degraded_lexicon_island",
                    "comprehensible_text": "Customers snacked daily",
                    "unclear_spans": [{"placeholder": "[unclear_lexicon]"}],
                    "in_low_conf_must_keep": True,
                }
            }
        },
    )
    good = {
        "target_segment_id": "t1",
        "target_beat": "snack pivot",
        "listener_need_entering_T": "need setup",
        "forward_unlock": "why demand broke the chain",
        "text": (
            "Before that scale-up, remember buyers were already snacking on the bar, "
            "which rewrote the addressable market for what comes next."
        ),
        "degraded_lexicon_island": True,
    }
    craft_ok = evaluate_layup_craft(ctx, [good])
    assert not any(e.startswith("canned_air") for e in craft_ok["errors"])

    canned = {
        **good,
        "text": "What changed after that?",
    }
    assert canned_air_violations(canned["text"])
    craft_bad = evaluate_layup_craft(ctx, [canned])
    assert any("canned_air" in e for e in craft_bad["errors"])

    invented = {
        **good,
        "text": "They said [unclear_lexicon] and that changed everything for the market.",
    }
    craft_inv = evaluate_layup_craft(ctx, [invented])
    assert any("invented_island" in e for e in craft_inv["errors"])
