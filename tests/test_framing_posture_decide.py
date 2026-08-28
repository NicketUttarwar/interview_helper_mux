"""framing_posture_decide — monologue skip, 2M advisory, mock LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.framing_posture import (
    FRAMING_POSTURE_DECISION_REL,
    apply_host_gate,
    build_framing_posture_input,
    persist_framing_decision,
    should_run_framing_posture_llm,
)
from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
from interview_mux.pipeline import ANALYSIS_ORDER
from interview_mux.prompt_validation import validate_stage_artifacts
from interview_mux.stages import framing_posture_decide as stage_mod
from interview_mux.v2.config import ALL_LLM_STAGES
from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_manifest_segment


def _write_homunculus_meta(ctx, version: str = "0.1.0") -> None:
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": version,
            "homunculus_kind": "homunculus" if version >= "0.1.0" else "original_pipeline",
        },
    )


def _write_monologue_fixtures(ctx) -> None:
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
            ],
            "conversation_profile": {"format_class_candidate": "fireside", "dynamics": {}},
        },
    )
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "monologue_heavy", "speaker_stats": []},
    )
    ctx.write_json(
        "understanding/content_brief.json",
        minimal_content_brief(thesis="Solo founder monologue."),
    )
    ctx.write_json(
        "segments/manifest.json",
        {"segments": [minimal_manifest_segment(segment_id="seg_001", speaker_id="spk_0")]},
    )


def _write_hosted_interview_fixtures(ctx) -> None:
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ],
            "conversation_profile": {"format_class_candidate": "one_on_one", "dynamics": {}},
        },
    )
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "speaker_stats": [
                {"speaker_id": "spk_0", "talk_ratio": 0.3},
                {"speaker_id": "spk_1", "talk_ratio": 0.7},
            ],
        },
    )
    ctx.write_json(
        "understanding/content_brief.json",
        minimal_content_brief(thesis="Hosted product interview."),
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                minimal_manifest_segment(
                    segment_id="seg_001",
                    speaker_id="spk_0",
                    segment_type="interviewer_question",
                ),
                minimal_manifest_segment(
                    segment_id="seg_002",
                    speaker_id="spk_1",
                    segment_type="interviewee_answer",
                ),
            ]
        },
    )


def test_analysis_order_places_framing_posture_after_reanchor() -> None:
    reanchor_idx = ANALYSIS_ORDER.index("content_brief_reanchor")
    decide_idx = ANALYSIS_ORDER.index("framing_posture_decide")
    resplit_idx = ANALYSIS_ORDER.index("boundary_topic_resplit")
    assert decide_idx == reanchor_idx + 1
    assert resplit_idx == decide_idx + 1
    assert "framing_posture_decide" in ALL_LLM_STAGES


def test_monologue_skips_llm_and_skips_gap_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "mono_skip")
    _write_homunculus_meta(ctx)
    _write_monologue_fixtures(ctx)

    llm_called = {"n": 0}

    def _boom(*_a, **_k):
        llm_called["n"] += 1

    monkeypatch.setattr(stage_mod, "run_analysis_llm_stage", _boom)

    stage_mod.run_framing_posture_decide(ctx)

    assert llm_called["n"] == 0
    assert ctx.is_done("framing_posture_decide")
    doc = ctx.read_json(FRAMING_POSTURE_DECISION_REL)
    assert doc["recommended_framing"] == "no"
    assert doc["posture_hint"] == "native_only"
    assert doc["decided_by"] == "deterministic_monologue"
    assert gap_fill_was_skipped(ctx)


def test_non_homunculus_skips_stage_without_artifact(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "legacy_skip")
    _write_homunculus_meta(ctx, version="0.0.0")
    _write_hosted_interview_fixtures(ctx)

    stage_mod.run_framing_posture_decide(ctx)

    assert ctx.is_done("framing_posture_decide")
    assert not ctx.artifact_exists(FRAMING_POSTURE_DECISION_REL)


def test_llm_advisory_does_not_skip_gap_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "advisory_yes")
    _write_homunculus_meta(ctx)
    _write_hosted_interview_fixtures(ctx)

    advisory = {
        "recommended_framing": "sparse",
        "posture_hint": "framing_sparse",
        "rationale_plain": "Sparse host bridges would help topic jumps.",
        "reason_codes": ["hosted_one_on_one"],
        "signals_summary": {"speaker_change_rate": 0.5},
    }

    def fake_run(_ctx, stage_key, _prompt, build_input, persist, **_kwargs):
        assert stage_key == "framing_posture_decide"
        payload = build_input(_ctx)
        assert "volley_stats" in payload
        assert payload["volley_stats"]["segment_count"] == 2
        persist(_ctx, advisory)

    monkeypatch.setattr(stage_mod, "run_analysis_llm_stage", fake_run)

    stage_mod.run_framing_posture_decide(ctx)

    doc = ctx.read_json(FRAMING_POSTURE_DECISION_REL)
    assert doc["recommended_framing"] == "sparse"
    assert doc["decided_by"] == "llm_advisory"
    assert doc.get("advisory_only") is True
    assert not gap_fill_was_skipped(ctx)
    assert validate_stage_artifacts("framing_posture_decide", doc) == []


def test_apply_host_gate_ignores_llm_native_only_hint(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "gate_2m")
    _write_homunculus_meta(ctx)
    _write_hosted_interview_fixtures(ctx)

    persist_framing_decision(
        ctx,
        {
            "recommended_framing": "no",
            "posture_hint": "native_only",
            "rationale_plain": "LLM thinks native only.",
            "reason_codes": ["llm_guess"],
            "decided_by": "llm_advisory",
        },
    )

    apply_host_gate(ctx)
    assert not gap_fill_was_skipped(ctx)


def test_should_run_framing_posture_llm(tmp_path: Path) -> None:
    mono = isolated_run_ctx(tmp_path, "should_mono")
    _write_homunculus_meta(mono)
    _write_monologue_fixtures(mono)
    assert not should_run_framing_posture_llm(mono)

    hosted = isolated_run_ctx(tmp_path, "should_hosted")
    _write_homunculus_meta(hosted)
    _write_hosted_interview_fixtures(hosted)
    assert should_run_framing_posture_llm(hosted)


def test_build_framing_posture_input_packs_topology_and_volley(
    tmp_path: Path,
) -> None:
    ctx = isolated_run_ctx(tmp_path, "payload")
    _write_homunculus_meta(ctx)
    _write_hosted_interview_fixtures(ctx)

    payload = build_framing_posture_input(ctx)
    assert "content_brief" in payload
    assert payload["source_topology"]["topology_class"] == "one_on_one_asymmetric"
    assert payload["volley_stats"]["speaker_change_count"] == 1
    assert payload["gap_fill_eligibility"]["eligible"] is True
