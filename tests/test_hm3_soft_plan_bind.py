"""HM-3: soft-gate / degraded plans must not bind as authoritative.

Only plan_status=complete may stamp mastering_plan_bound / plan_bound.
Segment order stays on the ranking lattice. Do not start a run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.delivery_brief import _overlay_mastering_plan
from interview_mux.episode_structure import build_episode_structure
from interview_mux.mastering_plan_loader import plan_is_authoritative
from interview_mux.run_context import RunContext
from interview_mux.shape_order_bind import resolve_air_order
from interview_mux.soundscape_policy import build_policy
from run_fixtures import isolated_run_ctx, minimal_source_acoustic_profile


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

    def log(self, *_a, **_k) -> None:
        pass

    def mark_done(self, *_a, **_k) -> None:
        pass


def _segs(n: int = 3) -> list[dict]:
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


def _degraded_plan(**extra: object) -> dict:
    plan = {
        "plan_status": "degraded",
        "narrative_mode": "hook_montage",
        "confirmed_mode": "hook_montage",
        "target_duration_sec": 999,
        "ordered_segment_ids": ["seg_2", "seg_1", "seg_0"],
        "source": "soft_gate",
        "degradation_reasons": ["soft_gate_not_authoritative"],
    }
    plan.update(extra)
    return plan


def _complete_plan(**extra: object) -> dict:
    plan = _degraded_plan()
    plan["plan_status"] = "complete"
    plan.pop("degradation_reasons", None)
    plan.update(extra)
    return plan


def _seed_soundscape(ctx: RunContext) -> None:
    sap = minimal_source_acoustic_profile(
        pacing={
            "global_wpm": 140,
            "wpm_by_quartile": [120, 130, 140, 150],
            "pace_class": "conversational",
            "speech_active_ratio": 0.7,
            "overlap_proxy": 0.05,
        },
        source_music_risk="low",
        mix_contract={
            "underscore_policy": "normal",
            "duck_under_speech_db": 16,
            "stinger_max_per_minute": 3,
            "bed_level_db_range": [-30, -26],
        },
    )
    ctx.write_json("understanding/source_acoustic_profile.json", sap)
    ctx.write_json(
        "understanding/delivery_brief.json",
        {
            "version": 1,
            "source_duration_ms": 600000,
            "target_duration_sec": {"min": 300, "ideal": 420, "max": 540},
            "question_budget": {"min": 0, "ideal": 2, "max": 4},
            "chapter_budget": {"min": 2, "ideal": 3, "max": 4},
            "selection_mode": "coverage_first",
            "sfx_density": {"max_beds": 2, "max_punctuators": 2, "max_foley": 1},
            "ranking_weights": {},
            "rationale": [],
            "operator_overrides": {},
            "generated": {},
        },
    )


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "hm3_plan")


def test_hm3_plan_is_authoritative_only_when_complete() -> None:
    assert plan_is_authoritative(_complete_plan()) is True
    assert plan_is_authoritative(_degraded_plan()) is False
    assert plan_is_authoritative(_degraded_plan(plan_status="forced_sparse")) is False
    assert plan_is_authoritative({"narrative_mode": "hook_montage"}) is False
    assert plan_is_authoritative(None) is False


def test_hm3_degraded_brief_does_not_bind(ctx: RunContext) -> None:
    ctx.write_json("mastering/mastering_plan.json", _degraded_plan())
    brief = {"rationale": [], "selection_mode": "coverage_first"}
    out = _overlay_mastering_plan(ctx, brief)
    assert out.get("mastering_plan_bound") is not True
    assert out.get("selection_mode") != "plan_bound"
    assert out.get("target_duration_sec") is None


def test_hm3_complete_brief_binds(ctx: RunContext) -> None:
    ctx.write_json("mastering/mastering_plan.json", _complete_plan())
    brief = {"rationale": [], "selection_mode": "coverage_first"}
    out = _overlay_mastering_plan(ctx, brief)
    assert out.get("mastering_plan_bound") is True
    assert out.get("selection_mode") == "plan_bound"
    assert out["target_duration_sec"]["ideal"] == 999


def test_hm3_degraded_episode_keeps_ranking_order(tmp_path: Path) -> None:
    segs = _segs(3)
    manifest_ids = [str(s["segment_id"]) for s in segs]
    arts = {
        "segments/manifest.json": {"segments": segs},
        "understanding/analysis_state.json": {"style": {"format_class": "one_on_one"}},
        "understanding/sonic_context.json": {"scenario": {"atlas_bucket": "one_on_one"}},
        "mastering/mastering_plan.json": _degraded_plan(
            ordered_segment_ids=list(reversed(manifest_ids)),
        ),
    }
    doc = build_episode_structure(_FakeCtx(tmp_path, arts))
    assert doc.get("mastering_plan_bound") is not True
    assert doc["segment_order"] != list(reversed(manifest_ids))
    assert set(doc["segment_order"]) == set(manifest_ids)


def test_hm3_complete_episode_may_bind_order(tmp_path: Path) -> None:
    segs = _segs(3)
    manifest_ids = [str(s["segment_id"]) for s in segs]
    plan_ids = list(reversed(manifest_ids))
    arts = {
        "segments/manifest.json": {"segments": segs},
        "understanding/analysis_state.json": {"style": {"format_class": "one_on_one"}},
        "understanding/sonic_context.json": {"scenario": {"atlas_bucket": "one_on_one"}},
        "mastering/mastering_plan.json": _complete_plan(ordered_segment_ids=plan_ids),
    }
    doc = build_episode_structure(_FakeCtx(tmp_path, arts))
    assert doc.get("mastering_plan_bound") is True
    assert doc["segment_order"][:3] == plan_ids


def test_hm3_degraded_soundscape_does_not_bind(ctx: RunContext) -> None:
    _seed_soundscape(ctx)
    ctx.write_json("mastering/mastering_plan.json", _degraded_plan())
    policy = build_policy(ctx)
    assert policy.get("mastering_plan_bound") is not True
    assert not any(
        "mastering_plan_mode_overlay" in str(r) for r in (policy.get("rationale") or [])
    )


def test_hm3_complete_soundscape_binds(ctx: RunContext) -> None:
    _seed_soundscape(ctx)
    ctx.write_json(
        "mastering/mastering_plan.json",
        _complete_plan(narrative_mode="sparse_source", confirmed_mode="sparse_source"),
    )
    policy = build_policy(ctx)
    assert policy.get("mastering_plan_bound") is True


def test_hm3_air_order_stays_on_ranking_when_degraded() -> None:
    degraded = _degraded_plan(ordered_segment_ids=["a", "b", "c"])
    bind = resolve_air_order(
        mastering_plan=degraded,
        selection_ordered=["c", "b", "a"],
        prefer_shape=True,
    )
    assert bind["order_authority"] == "ranking"
    assert bind["bind_reason"] == "plan_not_complete"
