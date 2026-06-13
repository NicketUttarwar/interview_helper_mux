"""Shared helpers for isolated run directories (import as `from run_fixtures import ...`)."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

MINIMAL_WAV_BYTES = b"RIFF" + b"\x00" * 64

# Stable hash pair for reuse tests (same source audio fingerprint).
TEST_SOURCE_AUDIO_HASH = "a" * 64
TEST_SOURCE_AUDIO_HASH_SHORT = "a" * 12

_MERGED_CONFIG_MODULES = (
    "interview_mux.config",
    "interview_mux.run_context",
    "interview_mux.stage_execution_reuse",
    "interview_mux.web.server",
    "interview_mux.gui_session",
    "interview_mux.write_staging",
    "interview_mux.custom_run_handoff",
    "interview_mux.llm_call_record",
    "interview_mux.llm_calls_gui",
    "interview_mux.journey_orchestrator",
    "interview_mux.journey_state",
    "interview_mux.disfluency.config",
    "interview_mux.llm_flow_hardening",
    "interview_mux.llm_preflight",
    "interview_mux.artifact_cross_validate",
)


def patch_merged_config(monkeypatch, cfg: dict[str, Any]) -> None:
    """Patch merged_config in every imported module that binds it at load time."""
    import importlib

    for mod_name in _MERGED_CONFIG_MODULES:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        if hasattr(mod, "merged_config"):
            monkeypatch.setattr(mod, "merged_config", lambda c=cfg: c)


def _execution_number_from_run_id(run_id: str) -> int | None:
    if not run_id.startswith("exec_"):
        return None
    part = run_id.split("_")[1]
    return int(part) if part.isdigit() else None


def ensure_test_wav(
    root: Path,
    rel: str = "ASSETS/input/interview.wav",
    *,
    content: bytes = MINIMAL_WAV_BYTES,
) -> Path:
    """Create a minimal WAV under root for init_run_meta / hash tests."""
    wav = root / rel
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(content)
    return wav


def populated_analysis_state(run_id: str, *, verified: bool = False) -> dict[str, Any]:
    """Minimal complete analysis_state for gate / handoff tests."""
    from interview_mux.analysis_memory import default_analysis_state

    state = default_analysis_state(run_id)
    state["themes"] = [{"id": "t1", "label": "Theme", "summary": "Summary text"}]
    state["narrative"] = {"thesis": "Core thesis from the interview."}
    state["interview_identity"] = {"one_line_summary": "A conversation about testing."}
    state["style"] = {
        "tone": "Warm investigative conversation",
        "tone_class": "journalistic",
        "format_class": "one_on_one",
        "pacing": "measured",
        "format_notes": "",
        "interviewer_style": "curious",
        "interviewee_style": "analytical",
    }
    state["meta"]["operator_verified"] = verified
    state["completion"] = {"analysis_ready": True, "blockers": []}
    return state


def init_run_meta_for_test(
    ctx: RunContext,
    input_audio_path: str = "ASSETS/input/demo.wav",
    *,
    source_audio_hash: str | None = TEST_SOURCE_AUDIO_HASH,
    source_audio_hash_short: str | None = TEST_SOURCE_AUDIO_HASH_SHORT,
) -> None:
    """Minimal run_meta when run_dir is outside the repo tree (pytest tmp_path)."""
    now = datetime.now(timezone.utc).isoformat()
    meta: dict[str, Any] = {
        "created_at": now,
        "updated_at": now,
        "execution_id": ctx.run_id,
        "execution_number": _execution_number_from_run_id(ctx.run_id),
        "input_audio_path": input_audio_path,
        "storage_root": str(ctx.run_dir.relative_to(ctx.root)) if ctx.run_dir.is_relative_to(ctx.root) else str(ctx.run_dir),
    }
    if source_audio_hash:
        meta["source_audio_hash"] = source_audio_hash
    if source_audio_hash_short:
        meta["source_audio_hash_short"] = source_audio_hash_short
    ctx.write_json("run_meta.json", meta, skip_handoff=True)


def isolated_run_ctx(tmp_path: Path, run_id: str) -> RunContext:
    """Run under tmp_path only — avoids collisions with data/run_* in the repo."""
    ctx = RunContext(run_id, create=True)
    ctx.run_dir = tmp_path / run_id
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done").mkdir(exist_ok=True)
    (ctx.run_dir / "vo_pickup").mkdir(exist_ok=True)
    return ctx


def ctx_from_fixture(tmp_path: Path, *, run_id: str = "exec_smoke_fixture") -> RunContext:
    """Copy tests/fixtures/runs/base_smoke into tmp_path for pipeline/gate smokes."""
    fixture = Path(__file__).parent / "fixtures" / "runs" / "base_smoke"
    run_dir = tmp_path / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(fixture, run_dir)
    ctx = RunContext(run_id, create=False)
    ctx.run_dir = run_dir
    return ctx


def minimal_source_acoustic_profile(**patch: Any) -> dict[str, Any]:
    """Schema-valid SAP for tests that write via RunContext.write_json."""
    base: dict[str, Any] = {
        "schema_version": 1,
        "derived_from": {
            "normalized_wav": "ingest/normalized.wav",
            "transcript": "transcript/full.json",
            "computed_at": "2026-01-01T00:00:00+00:00",
            "stage": "source_acoustic_profile",
        },
        "pacing": {
            "global_wpm": 142,
            "wpm_by_quartile": [130, 140, 145, 150],
            "pause_p50_ms": 680,
            "pace_class": "conversational",
        },
        "energy": {"room_timbre_hint": "dry_close_mic_warm_low_mid"},
        "mix_contract": {"underscore_policy": "normal", "duck_under_speech_db": 16},
        "prompt_tokens": {
            "bed": "loopable ambient bed, no melody hook",
            "stinger": "soft mid-register rise under 1.5s",
            "avoid": "trailer whoosh, drum loop",
            "density": "normal beds; pace=conversational",
        },
        "placement_hints": {
            "stinger_density": "low",
            "prefer_stinger_after_pause_tail": True,
            "stinger_min_pause_after_speech_ms": 400,
        },
        "operator_overrides": {},
    }
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def sound_design_plan_with(**patch: Any) -> dict[str, Any]:
    """Schema-valid sound_design_plan.json starting from defaults."""
    from interview_mux.analysis_memory import default_sound_design_plan

    plan = default_sound_design_plan()
    for key, value in patch.items():
        if key == "flow_plans" and isinstance(value, dict):
            flow_plans = dict(plan.get("flow_plans") or {})
            for flow_key, flow_val in value.items():
                if isinstance(flow_val, dict) and isinstance(flow_plans.get(flow_key), dict):
                    flow_plans[flow_key] = {**flow_plans[flow_key], **flow_val}
                else:
                    flow_plans[flow_key] = flow_val
            plan["flow_plans"] = flow_plans
        elif key == "assets" and isinstance(value, list):
            plan["assets"] = value
        elif key == "generated" and isinstance(value, dict):
            plan["generated"] = {**(plan.get("generated") or {}), **value}
        else:
            plan[key] = value
    return plan


def minimal_manifest_segment(
    segment_id: str = "seg_001",
    *,
    start_ms: int = 0,
    end_ms: int = 5000,
    text: str = "Sample segment text.",
    **patch: Any,
) -> dict[str, Any]:
    """Schema-valid segment for segments/manifest.json."""
    base: dict[str, Any] = {
        "segment_id": segment_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker_id": "spk_001",
        "speaker_role": "interviewer",
        "type": "interviewer_question",
        "text": text,
        "topic_tags": ["origin_story"],
    }
    base.update(patch)
    return base


def minimal_manifest(*segments: dict[str, Any] | str) -> dict[str, Any]:
    """Schema-valid segments/manifest.json payload."""
    if not segments:
        return {"segments": [minimal_manifest_segment()]}
    out: list[dict[str, Any]] = []
    for i, seg in enumerate(segments):
        if isinstance(seg, str):
            out.append(minimal_manifest_segment(seg, start_ms=i * 5000, end_ms=(i + 1) * 5000))
        else:
            out.append(seg)
    return {"segments": out}


def minimal_narrative_plan(**patch: Any) -> dict[str, Any]:
    """Schema-valid flow_1_master/narrative_plan.json."""
    base: dict[str, Any] = {
        "arc_summary": "Test narrative arc for pytest.",
        "chapters": [
            {
                "chapter_id": "ch_01",
                "title": "Opening",
                "suggested_open_segment_id": "seg_001",
            }
        ],
        "ordering_constraints": [],
    }
    for key, value in patch.items():
        base[key] = value
    return base


def minimal_gap_line(**patch: Any) -> dict[str, Any]:
    """Schema-valid gap_report interviewer line."""
    base: dict[str, Any] = {
        "line_id": "line_001",
        "targets_segment_id": "seg_001",
        "delivery": "record",
        "gap_type": "missing_setup",
        "text": "Can you add context here?",
        "placement": "before",
    }
    base.update(patch)
    return base


def minimal_gap_report(*lines: dict[str, Any]) -> dict[str, Any]:
    """Schema-valid understanding/gap_report.json."""
    if not lines:
        return {"interviewer_lines": []}
    return {"interviewer_lines": list(lines)}


def minimal_gap_evaluations(*evaluations: dict[str, Any]) -> dict[str, Any]:
    """Schema-valid understanding/gap_evaluations.json."""
    if not evaluations:
        evaluations = (
            {
                "segment_id": "seg_001",
                "self_explanatory": True,
                "gap_type": "ok_with_light_bridge",
                "listener_confusion": "",
                "severity": "low",
            },
        )
    return {"evaluations": list(evaluations)}


def minimal_content_brief(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "thesis": "A clear thesis for testing.",
        "topics": [
            {
                "name": "Topic A",
                "summary": "Summary of topic A.",
                "segment_ids": ["seg_001"],
            }
        ],
        "topic_relationships": [{"from": "Topic A", "to": "Topic A", "relation": "supports"}],
    }
    base.update(patch)
    return base


def minimal_speakers() -> dict[str, Any]:
    return {
        "speakers": [
            {
                "speaker_id": "spk_0",
                "role": "interviewer",
                "confidence": 0.95,
                "evidence": ["Opening question pattern"],
            },
            {
                "speaker_id": "spk_1",
                "role": "interviewee",
                "confidence": 0.92,
                "evidence": ["Extended answers"],
            },
        ]
    }


def seed_flow1_full_sound_path(ctx: RunContext) -> None:
    """Flow 1 sound path with ranking, transitions, and narrative plan stubs for cross-validate."""
    seed_flow1_sound_spend_ready(ctx)
    ctx.write_json(
        "flow_1_master/selection.json",
        {"ordered_segment_ids": ["seg_001"], "chapters": [{"chapter_id": "ch1", "segment_ids": ["seg_001"]}]},
        skip_handoff=True,
    )
    ctx.write_json(
        "flow_1_master/transitions.json",
        {
            "transitions": [
                {
                    "transition_id": "t1",
                    "type": "topic_shift",
                    "before_segment_id": "seg_001",
                    "after_segment_id": "seg_001",
                    "text": "Next.",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/narrative_arc_plan.json",
        {"chapters": [{"chapter_id": "ch1", "title": "Opening", "segment_ids": ["seg_001"]}]},
        skip_handoff=True,
    )


def seed_flow1_sound_spend_ready(ctx: RunContext) -> None:
    """Minimal Flow 1 sound path artifacts for cross-validate spend/mix regression tests."""
    seed_analysis_ready_artifacts(ctx, verified=True)
    ctx.write_json(
        "flow_1_master/selection.json",
        {"ordered_segment_ids": ["seg_001"], "chapters": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "bed_01",
                    "role": "ambient_bed",
                    "palette_id": "p1",
                    "description": "Warm sparse room tone",
                    "duration_seconds": 6.0,
                }
            ],
            flow_plans={
                "flow1": {
                    "cues": [
                        {
                            "cue_id": "c1",
                            "asset_id": "bed_01",
                            "placement": "under_segment",
                            "segment_id": "seg_001",
                        }
                    ]
                }
            },
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "sound_design/elevenlabs_prompts.json",
        {
            "prompts": [
                {
                    "asset_id": "bed_01",
                    "elevenlabs_prompt": "soft non-vocal room tone loop without rhythm or melody for podcast underscore",
                    "duration_seconds": 6,
                    "negative_prompt": "vocals lyrics speech",
                }
            ]
        },
        skip_handoff=True,
    )
    assets_dir = ctx.path("sound_design", "assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "bed_01.wav").write_bytes(MINIMAL_WAV_BYTES)


def seed_analysis_ready_artifacts(ctx: RunContext, *, verified: bool = False) -> None:
    """Write minimal complete analysis artifacts for gate / hardening tests."""
    from interview_mux.artifact_writes import write_validated_artifact

    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.path("segments").mkdir(parents=True, exist_ok=True)
    write_validated_artifact(
        ctx,
        "understanding/speakers.json",
        minimal_speakers(),
        merge_from_disk=False,
        stage_key="speaker_roles",
    )
    write_validated_artifact(
        ctx,
        "understanding/content_brief.json",
        minimal_content_brief(),
        merge_from_disk=False,
        stage_key="content_brief_reanchor",
    )
    write_validated_artifact(
        ctx,
        "segments/manifest.json",
        minimal_manifest(),
        merge_from_disk=False,
        stage_key="segment_classification",
    )
    write_validated_artifact(
        ctx,
        "understanding/gap_evaluations.json",
        minimal_gap_evaluations(),
        merge_from_disk=False,
        stage_key="missing_framing",
    )
    write_validated_artifact(
        ctx,
        "understanding/gap_report.json",
        minimal_gap_report(),
        merge_from_disk=False,
        stage_key="optimal_questions",
    )
    state = populated_analysis_state(ctx.run_id, verified=verified)
    state["completion"] = {"analysis_ready": True, "blockers": []}
    write_validated_artifact(
        ctx,
        "understanding/analysis_state.json",
        state,
        merge_from_disk=False,
        stage_key="content_context",
    )
    ctx.mark_done("optimal_questions")


def minimal_flow2_selection(**patch: Any) -> dict[str, Any]:
    """Schema-valid flow_2_highlights/selection.json."""
    base: dict[str, Any] = {
        "reel_thesis": "Highlight reel thesis for pytest.",
        "highlights": [
            {
                "rank": 1,
                "segment_id": "seg_001",
                "start_ms": 0,
                "end_ms": 5000,
                "headline": "Hook",
                "scores": {
                    "salience": 0.9,
                    "clarity": 0.8,
                    "emotion": 0.7,
                    "quotability": 0.6,
                    "diversity_bonus": 0.1,
                },
            }
        ],
    }
    for key, value in patch.items():
        base[key] = value
    return base


def minimal_content_brief(**patch: Any) -> dict[str, Any]:
    """Schema-valid understanding/content_brief.json."""
    base: dict[str, Any] = {
        "thesis": "Test thesis for pytest.",
        "topics": [{"name": "Topic A", "summary": "Summary here."}],
    }
    base.update(patch)
    return base


def patch_server_ctx(monkeypatch, ctx: RunContext) -> None:
    """Route FastAPI handlers to an isolated RunContext."""
    from fastapi import HTTPException

    from interview_mux.web import server

    def _ctx(run_id: str) -> RunContext:
        if run_id != ctx.run_id:
            raise HTTPException(404, f"Run not found: {run_id}")
        return ctx

    monkeypatch.setattr(server, "_ctx", _ctx)


def patch_executions_root(monkeypatch, tmp_path: Path, **cfg_overrides: Any) -> Path:
    """Point executions_root at tmp_path so JobRunner threads resolve the same run dir."""
    from interview_mux.config import merged_config

    root = tmp_path / "ASSETS" / "executions"
    root.mkdir(parents=True, exist_ok=True)
    cfg = {
        **merged_config(),
        "assets_root": str((tmp_path / "ASSETS").resolve()),
        "executions_root": str(root.resolve()),
        **cfg_overrides,
    }
    patch_merged_config(monkeypatch, cfg)
    return root


def seed_analysis_complete(ctx: RunContext) -> None:
    """Mark shared analysis done and satisfy G0/G1 gates for flow execution."""
    from interview_mux import pipeline
    from interview_mux.analysis_memory import default_analysis_state

    for stage in pipeline.ANALYSIS_ORDER:
        ctx.mark_done(stage)
    ctx.mark_done("transcript_review")
    ctx.mark_done("vo_ingest")
    state = default_analysis_state(ctx.run_id)
    state["meta"]["operator_verified"] = True
    ctx.write_json("understanding/analysis_state.json", state)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "line_001",
                    "targets_segment_id": "seg_001",
                    "delivery": "record",
                    "gap_type": "context",
                    "text": "Add context",
                    "placement": "before",
                }
            ]
        },
    )
    pickup = ctx.path("vo_pickup")
    pickup.mkdir(parents=True, exist_ok=True)
    (pickup / "line_001.wav").write_bytes(b"RIFF")
    ctx.write_json("analysis_complete.json", {"analysis_ready": True, "blockers": []})
    meta = ctx.read_json("run_meta.json")
    meta["handoff_ack"] = {
        "sound_design_palettes": "2026-01-01T00:00:00+00:00",
        "speaker_roles": "2026-01-01T00:00:00+00:00",
        "content_context": "2026-01-01T00:00:00+00:00",
    }
    meta["handoff_pending_writes"] = {}
    ctx.write_json("run_meta.json", meta)
