"""Flow-preserving HV island clusters + structure adjudicate + H-edge cuts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.high_value_speech_islands import (
    group_high_value_island_clusters,
)
from interview_mux.island_cluster_structure import (
    build_island_cluster_structure_packet,
    high_conf_flank_cuts,
    load_locked_seams,
    lock_seams,
    parse_island_cluster_structure_envelope,
)
from interview_mux.segment_fuse import (
    adjudicate_seams_llm,
    apply_connector_fuses,
    plan_cluster_fuses,
    run_high_value_cluster_fuse_rounds,
)


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


def _words_span(start: int, end: int, text: str, conf: float) -> list[dict[str, Any]]:
    parts = text.split()
    if not parts:
        return []
    step = max(1, (end - start) // len(parts))
    out = []
    t = start
    for p in parts:
        out.append(
            {
                "text": p,
                "start_ms": t,
                "end_ms": min(end, t + step),
                "confidence": conf,
                "speaker_id": "spk_0",
            }
        )
        t += step
    return out


def test_flow_keep_short_same_topic_joins_multi(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "h1",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "text": "setup funding",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "l1",
                    "start_ms": 2000,
                    "end_ms": 3500,
                    "text": "garble one",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "h2",
                    "start_ms": 3500,
                    "end_ms": 5000,
                    "text": "mid funding",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "l2",
                    "start_ms": 5000,
                    "end_ms": 6500,
                    "text": "garble two",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "h3",
                    "start_ms": 6500,
                    "end_ms": 8000,
                    "text": "payoff funding",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
            ]
        },
    )
    ctx.write_json("segments/boundaries.json", {"boundaries": []})
    ctx.write_json(
        "analysis/high_value_speech_islands.json",
        {
            "islands": [
                {
                    "island_id": "hvi_001",
                    "start_ms": 2100,
                    "end_ms": 3400,
                    "segment_ids_touched": ["l1"],
                },
                {
                    "island_id": "hvi_002",
                    "start_ms": 5100,
                    "end_ms": 6400,
                    "segment_ids_touched": ["l2"],
                },
            ],
            "segment_ids_touched": ["l1", "l2"],
            "island_count": 2,
        },
    )
    grouped = group_high_value_island_clusters(ctx, write=True)
    assert grouped["cluster_count"] == 1
    assert grouped["clusters"][0]["density"] == "multi"
    assert grouped["clusters"][0]["member_island_ids"] == ["hvi_001", "hvi_002"]


def test_flow_break_topic_shift_splits_and_hinge(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "a",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "text": "about funding",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "l1",
                    "start_ms": 2000,
                    "end_ms": 3500,
                    "text": "garble",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "hinge",
                    "start_ms": 3500,
                    "end_ms": 5000,
                    "text": "now product roadmap",
                    "speaker_id": "spk_0",
                    "topic_tags": ["product"],
                },
                {
                    "segment_id": "l2",
                    "start_ms": 5000,
                    "end_ms": 6500,
                    "text": "garble2",
                    "speaker_id": "spk_0",
                    "topic_tags": ["product"],
                },
                {
                    "segment_id": "b",
                    "start_ms": 6500,
                    "end_ms": 8000,
                    "text": "product payoff",
                    "speaker_id": "spk_0",
                    "topic_tags": ["product"],
                },
            ]
        },
    )
    ctx.write_json(
        "segments/boundaries.json",
        {"boundaries": [{"cut_ms": 4200, "reason": "topic_shift"}]},
    )
    ctx.write_json(
        "analysis/high_value_speech_islands.json",
        {
            "islands": [
                {
                    "island_id": "hvi_001",
                    "start_ms": 2100,
                    "end_ms": 3400,
                    "segment_ids_touched": ["l1"],
                },
                {
                    "island_id": "hvi_002",
                    "start_ms": 5100,
                    "end_ms": 6400,
                    "segment_ids_touched": ["l2"],
                },
            ],
            "island_count": 2,
            "segment_ids_touched": ["l1", "l2"],
        },
    )
    grouped = group_high_value_island_clusters(ctx, write=True)
    assert grouped["cluster_count"] == 2
    assert any(s.get("separate_reason") == "topic_subtopic_change" for s in grouped["splits"])
    assert any(s.get("hinge_attach") in {"left", "right"} for s in grouped["splits"])


def test_packet_has_full_text_no_summary(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    words = (
        _words_span(0, 2000, "high conf left flank words here", 0.95)
        + _words_span(2000, 4000, "low conf garble domain", 0.4)
        + _words_span(4000, 6000, "high conf right flank words", 0.96)
    )
    ctx.write_json("transcript/full.json", {"words": words})
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "h1",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "text": "high conf left flank words here",
                    "speaker_id": "spk_0",
                    "topic_tags": ["t"],
                },
                {
                    "segment_id": "l1",
                    "start_ms": 2000,
                    "end_ms": 4000,
                    "text": "low conf garble domain",
                    "speaker_id": "spk_0",
                    "topic_tags": ["t"],
                },
                {
                    "segment_id": "h2",
                    "start_ms": 4000,
                    "end_ms": 6000,
                    "text": "high conf right flank words",
                    "speaker_id": "spk_0",
                    "topic_tags": ["t"],
                },
            ]
        },
    )
    cluster = {
        "cluster_id": "hvc_001",
        "density": "multi",
        "member_island_ids": ["hvi_001", "hvi_002"],
        "islands": [
            {
                "island_id": "hvi_001",
                "start_ms": 2000,
                "end_ms": 3000,
                "segment_ids_touched": ["l1"],
                "kind": "low_conf_cluster",
                "mean_rms": 0.1,
                "level_ratio": 1.0,
            },
            {
                "island_id": "hvi_002",
                "start_ms": 3000,
                "end_ms": 4000,
                "segment_ids_touched": ["l1"],
                "kind": "low_conf_cluster",
            },
        ],
        "start_ms": 2000,
        "end_ms": 4000,
        "segment_ids_touched": ["l1"],
    }
    packet = build_island_cluster_structure_packet(ctx, cluster)
    assert "summary" not in packet
    assert packet["blocks"]
    assert all("full_text" in b for b in packet["blocks"])
    assert any(b.get("role") == "low_island" for b in packet["blocks"])
    denylist = {"exists", "stage_done", "run_meta"}
    blob = str(packet)
    assert not any(k in blob for k in denylist if k == "stage_done")


def test_parse_guardrails_coerce_bridge_under_split(tmp_path: Path):
    cluster = {
        "cluster_id": "hvc_001",
        "member_island_ids": ["hvi_001", "hvi_002"],
    }
    packet = {
        "blocks": [{"block_id": "blk_001"}],
        "per_island_defaults": [
            {"island_id": "hvi_001", "default_fuse_side": "left"},
            {"island_id": "hvi_002", "default_fuse_side": "right"},
        ],
    }
    envelope = {
        "status": "complete",
        "artifacts": {
            "cluster_id": "hvc_001",
            "topic_unity": "split_topics",
            "assignments": [
                {"island_id": "hvi_001", "fuse_side": "bridge", "rationale": "bad"},
                {"island_id": "unknown", "fuse_side": "left"},
            ],
            "cut_hinge_block_ids": ["blk_001", "blk_missing"],
        },
    }
    parsed = parse_island_cluster_structure_envelope(envelope, packet, cluster)
    assert parsed is not None
    assert parsed["topic_unity"] == "split_topics"
    by = {a["island_id"]: a for a in parsed["assignments"]}
    assert by["hvi_001"]["fuse_side"] in {"left", "right"}
    assert by["hvi_001"]["fuse_side"] != "bridge"
    assert "hvi_002" in by
    assert parsed["cut_hinge_block_ids"] == ["blk_001"]


def test_h_edge_cuts_use_high_conf_flanks(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    words = (
        _words_span(0, 1000, "clear left", 0.97)
        + _words_span(1000, 3000, "murmur garble", 0.3)
        + _words_span(3000, 4000, "clear right", 0.98)
    )
    ctx.write_json("transcript/full.json", {"words": words})
    left = high_conf_flank_cuts(
        ctx, island_start_ms=1000, island_end_ms=3000, fuse_side="left"
    )
    assert left["absorb_start_ms"] == 1000  # end of last high conf before island
    right = high_conf_flank_cuts(
        ctx, island_start_ms=1000, island_end_ms=3000, fuse_side="right"
    )
    assert right["absorb_end_ms"] == 3000  # start of first high conf after island


def test_locked_seam_blocks_llm_fuse(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    lock_seams(ctx, ["seg_a__seg_b"], pass_id="test")
    assert "seg_a__seg_b" in load_locked_seams(ctx)
    packets = [
        {
            "pair_id": "seg_a__seg_b",
            "earlier_segment_id": "seg_a",
            "later_segment_id": "seg_b",
            "same_speaker": True,
            "seam_hash": "abc",
            "deterministic_hints": {},
        }
    ]
    verdicts = adjudicate_seams_llm(ctx, packets)
    assert len(verdicts) == 1
    assert verdicts[0]["decision"] == "stay_independent"
    assert verdicts[0]["forced_by"] == "locked_seam"


def test_plan_cluster_and_apply_simple(tmp_path: Path):
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
    ctx.write_json("transcript/full.json", {"words": []})
    ctx.write_json("segments/boundaries.json", {"boundaries": []})
    cluster = {
        "cluster_id": "hvc_001",
        "density": "simple",
        "member_island_ids": ["hvi_001"],
        "islands": [
            {
                "island_id": "hvi_001",
                "start_ms": 2100,
                "end_ms": 4400,
                "segment_ids_touched": ["seg_b"],
            }
        ],
        "start_ms": 2100,
        "end_ms": 4400,
        "segment_ids_touched": ["seg_b"],
    }
    structure = {
        "topic_unity": "same_conversation",
        "assignments": [{"island_id": "hvi_001", "fuse_side": "bridge"}],
    }
    planned = plan_cluster_fuses(ctx, cluster, structure=structure)
    assert planned["plans"]
    assert any(v.get("decision") == "fuse" for v in planned["verdicts"])
    result = apply_connector_fuses(ctx, planned["verdicts"], pass_id="test_cluster")
    assert result["applied"] >= 1
    man = ctx.read_json("segments/manifest.json")
    assert len(man["segments"]) < 3


def test_simple_cluster_skips_llm_and_packet(tmp_path: Path, monkeypatch):
    ctx = _FakeCtx(tmp_path)
    calls = {"packet": 0, "llm": 0}

    def _no_packet(*_a, **_k):
        calls["packet"] += 1
        return {}

    def _no_llm(*_a, **_k):
        calls["llm"] += 1
        return None

    monkeypatch.setattr(
        "interview_mux.island_cluster_structure.build_island_cluster_structure_packet",
        _no_packet,
    )
    monkeypatch.setattr(
        "interview_mux.island_cluster_structure._llm_structure_call",
        _no_llm,
    )
    from interview_mux.island_cluster_structure import adjudicate_island_cluster_structure

    cluster = {
        "cluster_id": "hvc_simple",
        "density": "simple",
        "member_island_ids": ["hvi_001"],
        "islands": [{"island_id": "hvi_001", "start_ms": 1, "end_ms": 2}],
    }
    out = adjudicate_island_cluster_structure(ctx, cluster)
    assert out.get("skip_reason") == "simple_cluster"
    assert calls["packet"] == 0
    assert calls["llm"] == 0
    assert ctx.artifact_exists("analysis/island_cluster_structure_verdicts.json")
    assert not ctx.artifact_exists("analysis/island_cluster_structure_packets.json")


def test_multi_packet_persisted_and_soft_context(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    words = (
        _words_span(0, 2000, "high conf left flank words here", 0.95)
        + _words_span(2000, 4000, "low conf garble domain", 0.4)
        + _words_span(4000, 6000, "high conf right flank words", 0.96)
    )
    ctx.write_json("transcript/full.json", {"words": words})
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "h1",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "text": "high conf left flank words here",
                    "speaker_id": "spk_0",
                    "topic_tags": ["t"],
                },
                {
                    "segment_id": "l1",
                    "start_ms": 2000,
                    "end_ms": 4000,
                    "text": "low conf garble domain",
                    "speaker_id": "spk_0",
                    "topic_tags": ["t"],
                },
                {
                    "segment_id": "h2",
                    "start_ms": 4000,
                    "end_ms": 6000,
                    "text": "high conf right flank words",
                    "speaker_id": "spk_0",
                    "topic_tags": ["t"],
                },
            ]
        },
    )
    ctx.write_json(
        "understanding/speakers.json",
        {"speakers": [{"speaker_id": "spk_0", "role": "host"}]},
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "funding story", "topics": ["t"]},
    )
    cluster = {
        "cluster_id": "hvc_001",
        "density": "multi",
        "member_island_ids": ["hvi_001", "hvi_002"],
        "islands": [
            {
                "island_id": "hvi_001",
                "start_ms": 2000,
                "end_ms": 3000,
                "segment_ids_touched": ["l1"],
            },
            {
                "island_id": "hvi_002",
                "start_ms": 3000,
                "end_ms": 4000,
                "segment_ids_touched": ["l1"],
            },
        ],
        "start_ms": 2000,
        "end_ms": 4000,
        "segment_ids_touched": ["l1"],
    }
    packet = build_island_cluster_structure_packet(ctx, cluster)
    assert packet["pair_hints"]
    assert "hanging_setup_end" in packet["pair_hints"][0]
    assert "island_straddle" in packet["pair_hints"][0]
    soft = packet.get("soft_context") or {}
    assert soft.get("speaker_roles") or soft.get("content_context_excerpts")
    from interview_mux.island_cluster_structure import _append_packet

    _append_packet(ctx, packet)
    stored = ctx.read_json("analysis/island_cluster_structure_packets.json")
    assert any(
        (p.get("cluster") or {}).get("cluster_id") == "hvc_001"
        for p in (stored.get("packets") or [])
    )


def test_long_high_conf_break_splits(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "l1",
                    "start_ms": 0,
                    "end_ms": 1500,
                    "text": "garble",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "long_h",
                    "start_ms": 1500,
                    "end_ms": 15000,
                    "text": "long comprehensible high confidence monologue about funding",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "l2",
                    "start_ms": 15000,
                    "end_ms": 16500,
                    "text": "garble2",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
            ]
        },
    )
    ctx.write_json("segments/boundaries.json", {"boundaries": []})
    ctx.write_json(
        "analysis/high_value_speech_islands.json",
        {
            "islands": [
                {
                    "island_id": "hvi_001",
                    "start_ms": 100,
                    "end_ms": 1400,
                    "segment_ids_touched": ["l1"],
                },
                {
                    "island_id": "hvi_002",
                    "start_ms": 15100,
                    "end_ms": 16400,
                    "segment_ids_touched": ["l2"],
                },
            ],
            "island_count": 2,
            "segment_ids_touched": ["l1", "l2"],
        },
    )
    grouped = group_high_value_island_clusters(ctx, write=True)
    assert grouped["cluster_count"] == 2
    assert any(s.get("separate_reason") == "long_high_conf_break" for s in grouped["splits"])


def test_pre_ranking_uses_narrative_chapter_split(tmp_path: Path):
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "l1",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "text": "garble",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "h_mid",
                    "start_ms": 2000,
                    "end_ms": 4000,
                    "text": "short bridge",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
                {
                    "segment_id": "l2",
                    "start_ms": 4000,
                    "end_ms": 6000,
                    "text": "garble2",
                    "speaker_id": "spk_0",
                    "topic_tags": ["funding"],
                },
            ]
        },
    )
    ctx.write_json("segments/boundaries.json", {"boundaries": []})
    ctx.write_json(
        "understanding/narrative_arc.json",
        {
            "chapters": [
                {"chapter_id": "ch1", "start_ms": 0, "end_ms": 3000},
                {"chapter_id": "ch2", "start_ms": 3000, "end_ms": 7000},
            ]
        },
    )
    ctx.write_json(
        "analysis/high_value_speech_islands.json",
        {
            "islands": [
                {
                    "island_id": "hvi_001",
                    "start_ms": 100,
                    "end_ms": 1900,
                    "segment_ids_touched": ["l1"],
                },
                {
                    "island_id": "hvi_002",
                    "start_ms": 4100,
                    "end_ms": 5900,
                    "segment_ids_touched": ["l2"],
                },
            ],
            "island_count": 2,
            "segment_ids_touched": ["l1", "l2"],
        },
    )
    grouped = group_high_value_island_clusters(
        ctx, write=True, pass_id="pre_ranking"
    )
    assert grouped["use_narrative_chapters"] is True
    assert grouped["cluster_count"] == 2
    assert any(
        s.get("separate_reason") == "narrative_chapter_change" for s in grouped["splits"]
    )


def test_run_high_value_cluster_rounds_absorbs(tmp_path: Path):
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
    ctx.write_json("transcript/full.json", {"words": []})
    ctx.write_json("segments/boundaries.json", {"boundaries": []})
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
    out = run_high_value_cluster_fuse_rounds(ctx, pass_id="test")
    assert out["mode"] == "per_cluster"
    man = ctx.read_json("segments/manifest.json")
    ids = [s["segment_id"] for s in man["segments"]]
    assert "seg_island" not in ids or len(ids) < 3
