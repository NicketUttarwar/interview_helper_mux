"""Tests for graduated TBIY conformance inventory + strategies."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.delivery_brief import build_delivery_brief, compact_delivery_brief_for_volley
from interview_mux.prompt_validation import validate_delivery_brief
from interview_mux.run_context import RunContext
from interview_mux.source_topology import build_topology_artifacts
from interview_mux.tbiy_conformance import (
    ACTION_COLLAPSE,
    ACTION_VO_BRIDGE,
    apply_conformance_to_adaptation,
    build_conformance_plan,
    compact_conformance_for_volley,
    inventory_from_topology,
)


def _asymmetric_stats():
    return [
        {
            "speaker_id": "spk_0",
            "talk_ms": 70_000,
            "talk_ratio": 0.70,
            "role_hint": "interviewee",
            "turn_count": 10,
            "question_count": 0,
        },
        {
            "speaker_id": "spk_1",
            "talk_ms": 30_000,
            "talk_ratio": 0.30,
            "role_hint": "interviewer",
            "turn_count": 8,
            "question_count": 5,
        },
    ]


def _monologue_stats():
    return [
        {
            "speaker_id": "spk_0",
            "talk_ms": 90_000,
            "talk_ratio": 0.90,
            "role_hint": "interviewee",
            "turn_count": 4,
            "question_count": 0,
        },
        {
            "speaker_id": "spk_1",
            "talk_ms": 10_000,
            "talk_ratio": 0.10,
            "role_hint": "interviewer",
            "turn_count": 2,
            "question_count": 1,
        },
    ]


def test_monologue_prefers_collapse_and_vo_bridge():
    els = inventory_from_topology(
        topology_class="monologue_heavy",
        stats=_monologue_stats(),
        role_map={"reactor_speaker_ids": [], "pickup_eligible_speaker_id": "spk_1"},
        pickup_id="spk_1",
    )
    by_id = {e["id"]: e for e in els}
    assert by_id["five_act_scaffolding"]["action"] == ACTION_COLLAPSE
    assert by_id["act_bridge_capacity"]["action"] == ACTION_VO_BRIDGE
    assert by_id["reaction_texture"]["action"] == ACTION_VO_BRIDGE


def test_asymmetric_strong_frame_applies_reactor():
    els = inventory_from_topology(
        topology_class="one_on_one_asymmetric",
        stats=_asymmetric_stats(),
        role_map={"reactor_speaker_ids": ["spk_1"], "pickup_eligible_speaker_id": "spk_1"},
        pickup_id="spk_1",
    )
    by_id = {e["id"]: e for e in els}
    assert by_id["dual_voice_reactor"]["action"] == "apply"
    assert by_id["pickup_frame_voice"]["action"] == "apply"


def test_conformance_plan_never_falls_back_to_documentary():
    plan = build_conformance_plan(
        topology_class="monologue_heavy",
        stats=_monologue_stats(),
        role_map={"reactor_speaker_ids": []},
        pickup_id="spk_1",
    )
    assert plan["active"] is True
    assert plan["production_style"] == "tbiy_narrative"
    assert plan["guidance"]["never_fallback_to_documentary"] is True
    assert plan["modes"]["five_act_mode"] == "collapsed"
    compact = compact_conformance_for_volley(plan)
    assert compact and compact["modes"]["vo_bridge_priority"] in ("high", "normal", "low")


def test_apply_conformance_updates_adaptation_summary():
    adapt = {
        "topology_class": "monologue_heavy",
        "production_style": "tbiy_narrative",
        "ranking_weights": {
            "narrative_arc_fit": 0.4,
            "claim_impact": 0.3,
            "reaction_opportunity": 0.1,
            "topic_coherence": 0.2,
        },
        "sfx_density": {"max_punctuators": 2, "max_beds": 3, "max_foley": 2},
        "pickup_eligible_speaker_id": "spk_1",
    }
    plan = build_conformance_plan(
        topology_class="monologue_heavy",
        stats=_monologue_stats(),
        pickup_id="spk_1",
    )
    out = apply_conformance_to_adaptation(adapt, plan)
    assert "tbiy_conformance" in out
    assert out["five_act_mode"] == "collapsed"
    assert "TBIY conformance" in (out.get("summary_plain") or "")


def test_source_topology_embeds_conformance_when_tbiy(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "transcript").mkdir()
    (run_dir / "understanding").mkdir()
    words = []
    t = 0
    for _i in range(100):
        words.append({"word": "hi", "speaker": "spk_0", "start_ms": t, "end_ms": t + 500})
        t += 500
    for _i in range(10):
        words.append({"word": "ok", "speaker": "spk_1", "start_ms": t, "end_ms": t + 500})
        t += 500
    (run_dir / "transcript" / "full.json").write_text(json.dumps({"words": words}))
    (run_dir / "understanding" / "speakers.json").write_text(
        json.dumps(
            {
                "speakers": [
                    {"speaker_id": "spk_0", "role": "interviewee"},
                    {"speaker_id": "spk_1", "role": "interviewer"},
                ]
            }
        )
    )
    (run_dir / "run_meta.json").write_text(json.dumps({"production_style": "tbiy_narrative"}))
    ctx = RunContext(str(run_dir))
    _topo, adapt = build_topology_artifacts(ctx)
    assert adapt.get("production_style") == "tbiy_narrative"
    conf = adapt.get("tbiy_conformance")
    assert isinstance(conf, dict) and conf.get("active") is True
    assert adapt.get("five_act_mode") in ("full", "soft", "collapsed")
    assert adapt.get("vo_bridge_priority") in ("high", "normal", "low")


def test_delivery_brief_includes_tbiy_modes(tmp_path: Path):
    run = tmp_path / "exec_tbiy"
    run.mkdir()
    (run / "understanding").mkdir()
    (run / "segments").mkdir()
    (run / "transcript").mkdir()
    (run / "transcript" / "full.json").write_text(
        '{"duration_ms": 3600000}', encoding="utf-8"
    )
    (run / "segments" / "manifest.json").write_text(
        '{"segments": [{"segment_id": "s1"}, {"segment_id": "s2"}, {"segment_id": "s3"}, '
        '{"segment_id": "s4"}, {"segment_id": "s5"}, {"segment_id": "s6"}]}',
        encoding="utf-8",
    )
    (run / "understanding" / "gap_report.json").write_text(
        '{"lines": [{"segment_id": "s1", "delivery": "record", "severity": "high", "script": "Why?"}]}',
        encoding="utf-8",
    )
    (run / "understanding" / "source_topology.json").write_text(
        json.dumps(
            {
                "topology_class": "monologue_heavy",
                "speaker_stats": _monologue_stats(),
                "pickup_eligible_speaker_id": "spk_1",
                "least_spoken_speaker_id": "spk_1",
                "tbiy_role_map": {"reactor_speaker_ids": [], "pickup_eligible_speaker_id": "spk_1"},
                "production_style": "tbiy_narrative",
            }
        ),
        encoding="utf-8",
    )
    (run / "understanding" / "flow_adaptation.json").write_text(
        json.dumps(
            {
                "topology_class": "monologue_heavy",
                "production_style": "tbiy_narrative",
                "sfx_density": {"max_beds": 3, "max_punctuators": 2, "max_foley": 2},
                "ranking_weights": {"narrative_arc_fit": 0.4},
                "pickup_eligible_speaker_id": "spk_1",
            }
        ),
        encoding="utf-8",
    )
    (run / "run_meta.json").write_text(
        json.dumps({"production_style": "tbiy_narrative"}), encoding="utf-8"
    )
    (run / "understanding" / "content_brief.json").write_text(
        json.dumps(
            {
                "strategic_moat_concept": "Network effects",
                "key_claims": [{"id": "c1", "claim": "Density wins"}],
                "topics": [{"name": "Marketplace"}],
            }
        ),
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    brief = build_delivery_brief(ctx)
    errs = validate_delivery_brief(brief)
    assert errs == [], errs
    assert brief.get("five_act_mode") in ("full", "soft", "collapsed")
    assert brief.get("moat_mode") == "require"  # moat named on brief → apply
    assert isinstance(brief.get("tbiy_conformance"), dict)
    compact = compact_delivery_brief_for_volley(brief)
    assert compact and compact.get("moat_mode") == "require"
