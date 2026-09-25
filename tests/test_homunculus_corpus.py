"""Homunculus 0.1.0 contracts against the mastering quality eval corpus.

No live OpenAI. Spec: docs/cross-cutting/mastering-eval-corpus.md
"""

from __future__ import annotations

import pytest

from interview_mux.homunculus.agenda import skip_stage
from interview_mux.homunculus.gates import recommended_framing_action, set_gate_decision
from interview_mux.homunculus.host_tools import run_mmaudio_host
from interview_mux.homunculus.judge import write_judgment
from interview_mux.homunculus.kb import lesson_ids
from interview_mux.homunculus.packer import default_pack_fact_ids, pack_volley
from interview_mux.homunculus.source_card import SOURCE_CARD_REL, build_source_card
from interview_mux.run_context import RunContext
from mastering_quality_corpus import fixture_ids, load_fixture
from run_fixtures import write_fixture_json


def _ctx() -> RunContext:
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
    )
    return ctx


def _apply_fixture(ctx: RunContext, fixture: dict) -> None:
    import json

    tags = fixture.get("tags") or {}
    topology = fixture.get("topology") or {}

    def _raw(rel: str, payload: dict) -> None:
        path = ctx.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    _raw(
        "understanding/source_topology.json",
        {
            "topology_class": topology.get("kind") or tags.get("topology"),
            "pickup_eligible_speaker_id": topology.get("pickup_eligible_speaker_id"),
        },
    )
    _raw(
        "understanding/conversation_profile.json",
        {"format_class_candidate": tags.get("topology")},
    )
    if tags.get("acoustics") == "noisy":
        _raw("understanding/source_acoustic_profile.json", {"noisy": True})
    speakers = fixture.get("speakers") or []
    _raw("understanding/speakers.json", {"speakers": speakers})
    ctx.write_json(
        "ingest/transcript.json",
        {"text": "Closed G0 transcript for corpus fixture."},
    )
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "transcript_review_build").write_text("", encoding="utf-8")
    (ctx.run_dir / ".stage_done" / "transcript_review").write_text("", encoding="utf-8")
    dur_ms = int(fixture.get("source_duration_ms") or 0)
    if dur_ms:
        _raw("transcript/full.json", {"duration_ms": dur_ms, "text": "tape"})


@pytest.mark.parametrize("fid", fixture_ids())
def test_corpus_homunculus_block_present(fid: str) -> None:
    _fixture, exp = load_fixture(fid)
    hom = exp.get("homunculus") or {}
    assert hom.get("required_facts"), fid
    assert hom.get("clone_policy") == "least_spoken_host"


@pytest.mark.parametrize("fid", fixture_ids())
def test_packer_includes_source_card_axes(fid: str) -> None:
    fixture, exp = load_fixture(fid)
    ctx = _ctx()
    _apply_fixture(ctx, fixture)
    card = build_source_card(ctx)
    assert ctx.artifact_exists(SOURCE_CARD_REL)
    assert card.get("clone_policy") == "least_spoken_host"
    pack = pack_volley(ctx, fact_ids=default_pack_fact_ids(ctx, "full_master_ranking"), tool_id="full_master_ranking")
    blob = str(pack)
    for fact in exp["homunculus"]["required_facts"]:
        if fact == "g0_transcript":
            assert pack.get("g0_bootstrapped") or "G0" in blob
        else:
            assert fact in pack.get("fact_ids", []) or fact in blob


@pytest.mark.parametrize("fid", fixture_ids())
def test_illegal_gate_enforced(fid: str) -> None:
    fixture, exp = load_fixture(fid)
    ctx = _ctx()
    _apply_fixture(ctx, fixture)
    build_source_card(ctx)
    illegal = (exp.get("homunculus") or {}).get("illegal_gate") or {}
    if not illegal:
        return
    with pytest.raises(RuntimeError):
        set_gate_decision(ctx, str(illegal["category"]), str(illegal["action"]))


def test_monologue_framing_is_skip_not_dense_vo() -> None:
    fixture, exp = load_fixture("memoir_monologue_noisy")
    ctx = _ctx()
    _apply_fixture(ctx, fixture)
    build_source_card(ctx)
    assert recommended_framing_action(ctx) == exp["homunculus"]["framing_recommended"]
    assert recommended_framing_action(ctx) == "skip"


def test_hosted_interview_framing_auto_resolves_yes() -> None:
    fixture, exp = load_fixture("technical_1on1_landmined")
    ctx = _ctx()
    _apply_fixture(ctx, fixture)
    card = build_source_card(ctx)
    assert card.get("framing_posture") == "least_spoken_host"
    assert "monologue" not in (card.get("circumstances") or [])
    assert recommended_framing_action(ctx) == "auto_resolve"
    assert recommended_framing_action(ctx) == exp["homunculus"]["framing_recommended"]


def test_fireside_format_is_not_treated_as_monologue() -> None:
    ctx = _ctx()
    write_fixture_json(
        ctx,
        "understanding/source_topology.json",
        {"topology_class": "one_on_one_balanced", "pickup_eligible_speaker_id": "spk_1"},
    )
    write_fixture_json(
        ctx,
        "understanding/conversation_profile.json",
        {"format_class_candidate": "fireside"},
    )
    write_fixture_json(
        ctx,
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_1", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
            ]
        },
    )
    card = build_source_card(ctx)
    assert "monologue" not in (card.get("circumstances") or [])
    assert card.get("framing_posture") == "least_spoken_host"
    assert recommended_framing_action(ctx) == "auto_resolve"


def test_lessons_after_reject_packed_for_mix() -> None:
    fixture, exp = load_fixture("technical_1on1_landmined")
    ctx = _ctx()
    _apply_fixture(ctx, fixture)
    build_source_card(ctx)
    ctx.write_json(
        "mastering/listen_delight_audit.json",
        {"failed_dimensions": ["conversation_fit"], "passed": False},
    )
    write_judgment(
        ctx,
        verdict="reject",
        reason="landmine",
        implicated_groups=list(exp["homunculus"].get("expected_implicated") or ["mix"]),
        fail_open_reason="test",
    )
    ids = lesson_ids(ctx)
    assert ids
    packed = default_pack_fact_ids(ctx, "mix")
    assert any(i in packed for i in ids)


def test_musicgen_not_first_mmaudio_for_theme() -> None:
    ctx = _ctx()
    denied = run_mmaudio_host(ctx, {"prompt": "motif", "role": "theme_underscore"})
    assert denied["ok"] is False
    assert denied["error"] == "prefer_musicgen_first"


def test_legal_skip_does_not_raise_for_non_island() -> None:
    ctx = _ctx()
    skip_stage(ctx, "nle_operator_edits", reason="corpus skip")
    assert True
