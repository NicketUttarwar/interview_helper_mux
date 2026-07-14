"""Episode structure composer — sparse plans, occupancy, integrity, allowlist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.config import repo_root
from interview_mux.episode_structure import (
    build_compact_digest,
    build_episode_structure,
    check_integrity,
    check_occupancy,
    lint_episode_structure,
    load_pack,
)
from interview_mux.local_llm_config import QUALITY_LOCAL_ALLOWLIST
from interview_mux.prompt_validation import validate_episode_structure


class _FakeCtx:
    def __init__(self, root: Path, artifacts: dict[str, dict]):
        self.run_dir = root
        self._arts = artifacts

    def artifact_exists(self, rel: str) -> bool:
        return rel in self._arts

    def read_json(self, rel: str):
        return self._arts[rel]

    def path(self, *parts: str) -> Path:
        p = self.run_dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write_json(self, rel: str, data: dict) -> None:
        self._arts[rel] = data
        path = self.path(*rel.split("/"))
        path.write_text(json.dumps(data), encoding="utf-8")

    def log(self, *a, **k):
        pass

    def mark_done(self, *a, **k):
        pass


def _segs(n: int = 5) -> list[dict]:
    out = []
    for i in range(n):
        out.append(
            {
                "segment_id": f"seg_{i}",
                "text": ("word " * (20 + i * 5)).strip(),
                "type": "question" if i % 2 == 0 else "answer",
                "topic_tags": ["quote"] if i == 2 else [],
            }
        )
    return out


def test_compose_not_on_quality_allowlist():
    assert "episode_structure_compose" not in QUALITY_LOCAL_ALLOWLIST


def test_packs_load():
    pack = load_pack("debate")
    assert pack.get("pack_id") == "debate"
    assert "DYN_rebuttal_pair_lock" in (pack.get("prefer") or pack.get("unlock_dynamic") or [])


def test_sparse_plan_omits_payoff_by_default(tmp_path):
    arts = {
        "segments/manifest.json": {"segments": _segs(4)},
        "understanding/analysis_state.json": {"style": {"format_class": "one_on_one"}},
        "understanding/sonic_context.json": {"scenario": {"atlas_bucket": "one_on_one"}},
    }
    ctx = _FakeCtx(tmp_path, arts)
    doc = build_episode_structure(ctx)
    errs = validate_episode_structure(doc)
    assert not errs, errs
    lint = lint_episode_structure(doc)
    assert not lint, lint
    emitted = {s["component_id"] for s in doc["slot_plan"]}
    # allow-gated payoff/outro typically omitted when score low
    assert "STD_act_body" in emitted
    assert "STD_payoff_close" not in emitted or any(
        o.get("component_id") == "STD_payoff_close" for o in doc["omit_reasons"]
    ) or "STD_payoff_close" not in emitted


def test_trauma_pack_unlocks_warning(tmp_path):
    arts = {
        "segments/manifest.json": {"segments": _segs(6)},
        "understanding/analysis_state.json": {"style": {}},
        "understanding/sonic_context.json": {"scenario": {"atlas_bucket": "trauma_adjacent"}},
    }
    ctx = _FakeCtx(tmp_path, arts)
    doc = build_episode_structure(ctx)
    emitted = {s["component_id"] for s in doc["slot_plan"]}
    assert "DYN_content_warning_pad" in emitted
    assert "STD_cold_open_slot" not in emitted


def test_occupancy_unique_except_hook():
    order = ["a", "b", "c"]
    slots = [{"bound_segment_ids": ["a"], "repeat_allowed": True}]
    v = check_occupancy(order, slots, hook_id="a", repeat_allowed=True)
    assert v == []
    v2 = check_occupancy(["a", "a", "b"], [], hook_id=None, repeat_allowed=False)
    assert any("a" in x for x in v2)


def test_integrity_detects_orphan_answer():
    segs = [
        {"segment_id": "q1", "type": "question"},
        {"segment_id": "a1", "type": "answer"},
    ]
    ok, flags = check_integrity(segs, ["a1", "q1"])
    assert ok is False
    assert flags


def test_compact_digest_bounded(tmp_path):
    arts = {
        "segments/manifest.json": {"segments": _segs(3)},
        "understanding/analysis_state.json": {"style": {}},
        "understanding/sonic_context.json": {"scenario": {"atlas_bucket": "media_profile"}},
    }
    ctx = _FakeCtx(tmp_path, arts)
    doc = build_episode_structure(ctx)
    digest = build_compact_digest(doc)
    assert "axes:" in digest
    assert len(digest) < 4000


def test_schema_fixture_roundtrip():
    schema = json.loads(
        (repo_root() / "docs/cross-cutting/json-schemas/episode_structure.schema.json").read_text()
    )
    assert schema["title"] == "EpisodeStructure"
