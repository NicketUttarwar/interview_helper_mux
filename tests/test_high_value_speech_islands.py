"""High-value speech islands: volume gate, force-fuse, must_keep union."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from interview_mux.high_value_speech_islands import (
    _find_stt_skip_energy_spans,
    _passes_volume_gate,
    high_value_must_keep_segment_ids,
    high_value_speech_cfg,
    scan_high_value_speech_islands,
)
from interview_mux.low_conf_islands import (
    authoritative_low_conf_must_keep_ids,
    write_low_conf_must_keep,
)
from interview_mux.segment_fuse import apply_connector_fuses, plan_high_value_fuses


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

    def read_path(self, *parts: str) -> Path:
        raise FileNotFoundError("no wav")

    def log(self, *args: Any, **kwargs: Any) -> None:
        return None


def _fake_energy(median: float = 0.1) -> tuple[np.ndarray, np.ndarray, float]:
    # 10s of windows at 400ms → 25 buckets
    times = np.arange(0, 10000, 400, dtype=np.float64)
    rms = np.full(len(times), median, dtype=np.float64)
    return rms, times, median


def test_volume_gate_rejects_quiet_and_spike():
    conf = high_value_speech_cfg({"analysis": {"high_value_speech_islands": {}}})
    ok, ratio = _passes_volume_gate(0.01, 0.1, conf=conf)
    assert ok is False
    assert ratio is not None and ratio < 0.55
    ok2, _ = _passes_volume_gate(0.2, 0.1, conf=conf)  # 2.0 > 1.45
    assert ok2 is False
    ok3, ratio3 = _passes_volume_gate(0.1, 0.1, conf=conf)
    assert ok3 is True
    assert abs((ratio3 or 0) - 1.0) < 1e-6


def test_stt_skip_energy_detects_speech_gap_rejects_quiet(tmp_path: Path):
    conf = high_value_speech_cfg()
    words = [
        {"text": "hello", "start_ms": 0, "end_ms": 200},
        {"text": "world", "start_ms": 3200, "end_ms": 3400},  # 3s gap
    ]
    energy = _fake_energy(0.1)
    spans = _find_stt_skip_energy_spans(words, energy, conf=conf)
    assert len(spans) >= 1
    assert spans[0]["kind"] == "stt_skip_energy"
    assert spans[0]["word_count"] == 0

    # Quiet gap: set gap windows near zero
    rms, times, median = energy
    quiet = rms.copy()
    quiet[(times >= 200) & (times <= 3200)] = 0.01
    spans_quiet = _find_stt_skip_energy_spans(
        words, (quiet, times, median), conf=conf
    )
    assert spans_quiet == []


def test_single_low_word_cluster_rejected(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "hi", "start_ms": 0, "end_ms": 200, "confidence": 0.99},
                {"text": "xyz", "start_ms": 400, "end_ms": 600, "confidence": 0.3},
                {"text": "ok", "start_ms": 800, "end_ms": 1000, "confidence": 0.99},
            ]
        },
    )
    ctx.write_json(
        "analysis/low_conf_islands.json",
        {
            "islands": [
                {
                    "island_id": "lci_001",
                    "cluster_kind": "tight",
                    "start_ms": 400,
                    "end_ms": 600,
                    "word_count": 1,
                    "failure_mode": None,
                }
            ]
        },
    )
    energy = _fake_energy(0.1)
    doc = scan_high_value_speech_islands(
        ctx,
        low_conf_islands=ctx.read_json("analysis/low_conf_islands.json"),
        energy_override=energy,
    )
    assert doc["island_count"] == 0


def test_multi_low_conf_cluster_accepted(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json("transcript/full.json", {"words": []})
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "text": "garble",
                    "speaker_id": "spk_0",
                }
            ]
        },
    )
    ctx.write_json(
        "analysis/low_conf_islands.json",
        {
            "islands": [
                {
                    "island_id": "lci_010",
                    "cluster_kind": "loose",
                    "start_ms": 1000,
                    "end_ms": 3500,
                    "word_count": 5,
                    "failure_mode": None,
                }
            ]
        },
    )
    energy = _fake_energy(0.1)
    doc = scan_high_value_speech_islands(
        ctx,
        low_conf_islands=ctx.read_json("analysis/low_conf_islands.json"),
        energy_override=energy,
    )
    assert doc["island_count"] == 1
    assert doc["islands"][0]["kind"] == "low_conf_cluster"
    assert "seg_001" in doc["segment_ids_touched"]
    assert high_value_must_keep_segment_ids(ctx) == {"seg_001"}


def test_same_topic_attaches_one_neighbor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_a",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "text": "setup about funding",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "seg_b",
                    "start_ms": 2000,
                    "end_ms": 4500,
                    "text": "garble domain words",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "seg_c",
                    "start_ms": 4500,
                    "end_ms": 7000,
                    "text": "payoff about funding",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
            ]
        },
    )
    ctx.write_json(
        "analysis/high_value_speech_islands.json",
        {
            "islands": [
                {
                    "island_id": "hvi_001",
                    "start_ms": 2100,
                    "end_ms": 4400,
                    "segment_ids_touched": ["seg_b"],
                    "kind": "low_conf_cluster",
                }
            ],
            "segment_ids_touched": ["seg_b"],
            "island_count": 1,
        },
    )
    ctx.write_json("transcript/full.json", {"words": []})
    ctx.write_json("segments/boundaries.json", {"boundaries": []})

    plan = plan_high_value_fuses(ctx)
    assert plan["applied_plans"] == 1
    assert plan["plans"][0]["mode"] in {"richer_neighbor", "left", "right"}
    assert plan["plans"][0]["mode"] != "bridge"
    chain = list(plan["plans"][0]["chain"])
    assert "seg_b" in chain
    assert len(chain) == 2
    assert not ({"seg_a", "seg_b", "seg_c"} <= set(chain))
    assert all(v.get("forced_by") == "high_value_speech_island" for v in plan["verdicts"])

    # Apply without LLM — one neighbor only, the other complete beat stays.
    result = apply_connector_fuses(ctx, plan["verdicts"], pass_id="test_hv")
    assert result["applied"] >= 1
    man = ctx.read_json("segments/manifest.json")
    surviving = [s["segment_id"] for s in man["segments"]]
    assert len(surviving) == 2
    hv_rows = [s for s in man["segments"] if s.get("high_value_speech")]
    assert hv_rows
    assert hv_rows[0].get("retention") == "must_keep"


def test_richer_neighbor_when_topics_differ(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_prev",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "text": "long previous context with many words here about product",
                    "speaker_id": "spk_0",
                    "topic_tags": ["product"],
                },
                {
                    "segment_id": "seg_island",
                    "start_ms": 5000,
                    "end_ms": 6500,
                    "text": "garble",
                    "speaker_id": "spk_0",
                    "topic_tags": ["misc"],
                },
                {
                    "segment_id": "seg_next",
                    "start_ms": 6500,
                    "end_ms": 7500,
                    "text": "short next",
                    "speaker_id": "spk_0",
                    "topic_tags": ["exit"],
                },
            ]
        },
    )
    ctx.write_json(
        "analysis/high_value_speech_islands.json",
        {
            "islands": [
                {
                    "island_id": "hvi_002",
                    "start_ms": 5100,
                    "end_ms": 6400,
                    "segment_ids_touched": ["seg_island"],
                }
            ],
            "segment_ids_touched": ["seg_island"],
            "island_count": 1,
        },
    )
    plan = plan_high_value_fuses(ctx)
    assert plan["plans"][0]["mode"] == "richer_neighbor"
    assert plan["plans"][0]["chain"][0] == "seg_prev"


def test_must_keep_unions_high_value(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "analysis/low_conf_density_ranking.json",
        {
            "ranking": [
                {"segment_id": "seg_004", "density": 2.5, "rank": 1, "percentile": 1.0},
                {"segment_id": "seg_010", "density": 1.2, "rank": 2, "percentile": 0.5},
            ],
            "positive_count": 2,
            "segment_count": 2,
        },
    )
    ctx.write_json(
        "analysis/high_value_speech_islands.json",
        {
            "segment_ids_touched": ["seg_010"],
            "islands": [],
            "island_count": 0,
        },
    )
    out = write_low_conf_must_keep(ctx, ctx.read_json("analysis/low_conf_density_ranking.json"))
    assert "seg_004" in out["must_keep_segment_ids"]
    assert "seg_010" in out["must_keep_segment_ids"]
    assert "seg_010" in (out.get("high_value_segment_ids") or [])
    assert "seg_010" in authoritative_low_conf_must_keep_ids(ctx)


def test_remap_updates_must_keep_after_fuse(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_a",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "text": "a",
                    "speaker_id": "spk_0",
                    "topic_tags": ["t"],
                },
                {
                    "segment_id": "seg_b",
                    "start_ms": 2000,
                    "end_ms": 4000,
                    "text": "b",
                    "speaker_id": "spk_0",
                    "topic_tags": ["t"],
                },
            ]
        },
    )
    ctx.write_json("transcript/full.json", {"words": []})
    ctx.write_json("segments/boundaries.json", {"boundaries": []})
    ctx.write_json(
        "analysis/low_conf_must_keep.json",
        {
            "enforcement_mode": "authoritative",
            "must_keep_segment_ids": ["seg_b"],
            "high_value_segment_ids": ["seg_b"],
            "scores": [],
        },
    )
    ctx.write_json(
        "analysis/high_value_speech_islands.json",
        {
            "segment_ids_touched": ["seg_b"],
            "islands": [
                {
                    "island_id": "hvi_x",
                    "segment_ids_touched": ["seg_b"],
                    "start_ms": 2100,
                    "end_ms": 3900,
                }
            ],
        },
    )
    verdicts = [
        {
            "pair_id": "seg_a__seg_b",
            "earlier_segment_id": "seg_a",
            "later_segment_id": "seg_b",
            "decision": "fuse",
            "forced_by": "high_value_speech_island",
            "reason_code": "high_value_speech_neighbor",
            "rationale": "test",
            "confidence": 1.0,
        }
    ]
    apply_connector_fuses(ctx, verdicts, pass_id="remap_test")
    must = ctx.read_json("analysis/low_conf_must_keep.json")
    assert "seg_b" not in must["must_keep_segment_ids"]
    assert "seg_a" in must["must_keep_segment_ids"]
    hv = ctx.read_json("analysis/high_value_speech_islands.json")
    assert "seg_a" in hv["segment_ids_touched"]
