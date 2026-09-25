from __future__ import annotations

import math
import wave
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stage_input_checks import (
    StageInputError,
    collect_stage_input_issues,
    require_stage_inputs,
)
from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    staging_approval_hint,
)

from run_fixtures import isolated_run_ctx, patch_merged_config, patch_write_approval_enabled, mark_done_raw


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    executions = root / "ASSETS" / "executions"
    executions.mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {"require_write_approval_per_stage": True},
        },
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.merged_config",
        lambda: {
            "journey_ui": {"require_write_approval_per_stage": True},
        },
    )
    patch_write_approval_enabled(monkeypatch, enabled=True)
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def _write_tone_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        n = 1600
        amp = 8000
        frames = bytearray()
        for i in range(n):
            sample = int(amp * math.sin(2.0 * math.pi * 220.0 * (i / 16000)))
            frames += int(sample).to_bytes(2, byteorder="little", signed=True)
        wf.writeframes(bytes(frames))


def test_staging_approval_hint_when_file_only_in_pending_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    staged = ctx.path("ingest", "normalized.wav")
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"RIFF" + b"\0" * 40)
    exit_stage_staging()
    hint = staging_approval_hint(ctx, "ingest/normalized.wav")
    assert hint is not None
    assert "ingest" in hint
    assert "Save & continue" in hint


def test_source_acoustic_profile_blocked_without_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "transcript/full.json",
        {"text": "hello world", "words": [], "segments": []},
        skip_handoff=True,
    )
    issues = collect_stage_input_issues(ctx, "source_acoustic_profile")
    assert any("normalized" in issue.message.lower() for issue in issues)


def test_source_acoustic_profile_passes_with_approved_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    _write_tone_wav(ctx.final_path("ingest", "normalized.wav"))
    ctx.write_json(
        "transcript/full.json",
        {"text": "hello world", "words": [], "segments": []},
        skip_handoff=True,
    )
    mark_done_raw(ctx, "transcript_review")
    issues = collect_stage_input_issues(ctx, "source_acoustic_profile")
    assert issues == []


def test_require_stage_inputs_raises_with_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    with pytest.raises(StageInputError) as exc:
        require_stage_inputs(ctx, "master_finalize")
    assert exc.value.stage_id == "master_finalize"
    assert any(issue.remediation for issue in exc.value.issues)


def test_read_path_trap_hint_when_final_exists_but_staging_root_misses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.write_staging import staging_read_trap_hint

    ctx = _ctx(tmp_path, monkeypatch)
    _write_tone_wav(ctx.final_path("ingest", "normalized.wav"))
    enter_stage_staging("source_acoustic_profile")
    try:
        hint = staging_read_trap_hint(ctx, "ingest/normalized.wav")
        assert hint is not None
        assert "read_path" in hint
    finally:
        exit_stage_staging()


def test_vo_ingest_reads_pickup_from_final_path_during_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.gaps import ingest_vo_pickup

    from run_fixtures import confirm_test_pickup_speaker, write_fixture_json, write_fixture_vo_wav

    ctx = _ctx(tmp_path, monkeypatch)
    confirm_test_pickup_speaker(ctx)
    pickup = ctx.final_path("vo_pickup")
    write_fixture_vo_wav(pickup / "line_001.wav")
    write_fixture_json(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "line_001",
                    "delivery": "record",
                    "targets_segment_id": "seg_1",
                    "gap_type": "missing_framing",
                    "placement": "before",
                    "text": "Please clarify.",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"mix": {"normalize_vo_pickup": False}},
    )
    monkeypatch.setattr(
        "interview_mux.vo_speech_qa.vo_passes_speech_qa",
        lambda *_a, **_k: True,
    )
    enter_stage_staging("vo_ingest")
    try:
        assert not ctx.path("vo_pickup", "line_001.wav").is_file()
        try:
            ingest_vo_pickup(ctx)
        except Exception:
            # Hollow mark_done is honest; the stage still read the committed pickup.
            pass
    finally:
        exit_stage_staging()
    assert ctx.final_path("vo_pickup", "line_001.wav").is_file()


def test_segment_classification_blocked_when_boundaries_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True}}},
    )
    ctx = _ctx(tmp_path, monkeypatch)
    mark_done_raw(ctx, "boundary_detection")
    import json

    boundaries_path = ctx.path("segments/boundaries.json")
    boundaries_path.parent.mkdir(parents=True, exist_ok=True)
    boundaries_path.write_text(
        json.dumps(
            {
                "boundaries": [{"segment_id": "seg_1", "start_ms": 0, "end_ms": 1000}],
                "_meta": {"resilience": {"partial": True}},
            }
        ),
        encoding="utf-8",
    )
    ctx.write_json(
        "transcript/full.json",
        {"text": "hello", "words": [], "segments": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9, "label": "Host"}
            ]
        },
        skip_handoff=True,
    )
    with pytest.raises(StageInputError) as exc:
        require_stage_inputs(ctx, "segment_classification")
    assert exc.value.stage_id == "segment_classification"
    assert any(
        "boundar" in issue.message.lower() or "segment_contract" in issue.message.lower()
        for issue in exc.value.issues
    )


def _stage_pending(ctx: RunContext, stage_id: str, rel: str) -> None:
    enter_stage_staging(stage_id)
    staged = ctx.path(*rel.split("/"))
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text("{}", encoding="utf-8")
    exit_stage_staging()


def test_deferred_pending_does_not_block_next_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.first_try.write_approval_deferred", lambda cfg=None: True)
    _stage_pending(ctx, "ingest", "ingest/checksums.json")
    # Other stage may run while prior stage writes are deferred.
    write_issues = [
        i for i in collect_stage_input_issues(ctx, "source_topology_build") if i.kind == "write_approval"
    ]
    assert write_issues == []


def test_deferred_pending_blocks_same_stage_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.first_try.write_approval_deferred", lambda cfg=None: True)
    _stage_pending(ctx, "source_topology_build", "understanding/source_topology.json")
    issues = collect_stage_input_issues(ctx, "source_topology_build")
    write_issues = [i for i in issues if i.kind == "write_approval"]
    assert len(write_issues) == 1
    assert write_issues[0].related_stage == "source_topology_build"
    with pytest.raises(StageInputError) as exc:
        require_stage_inputs(ctx, "source_topology_build")
    assert exc.value.write_approval_only is True
    assert exc.value.pending_write_stage == "source_topology_build"


def test_undeferred_pending_blocks_any_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.first_try.write_approval_deferred", lambda cfg=None: False)
    _stage_pending(ctx, "ingest", "ingest/checksums.json")
    issues = collect_stage_input_issues(ctx, "source_topology_build")
    assert any(i.kind == "write_approval" for i in issues)


def test_require_stage_inputs_logs_warning_not_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    logged: list[dict] = []

    def _capture(msg: str, **kwargs: object) -> None:
        logged.append({"msg": msg, **kwargs})

    monkeypatch.setattr("interview_mux.operator_trace.log_step", _capture)
    with pytest.raises(StageInputError):
        require_stage_inputs(ctx, "master_finalize")
    assert logged
    assert logged[0].get("level") == "warning"
    assert "blocked" in str(logged[0].get("msg", "")).lower()


def test_check_write_approval_deferred_same_stage_soft_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.write_staging import check_write_approval_before_execute

    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.first_try.write_approval_deferred", lambda cfg=None: True)
    _stage_pending(ctx, "source_topology_build", "understanding/source_topology.json")
    assert check_write_approval_before_execute(ctx) is None
    assert check_write_approval_before_execute(ctx, stage_id="speaker_roles") is None
    pending = check_write_approval_before_execute(ctx, stage_id="source_topology_build")
    assert pending is not None
    assert pending.stage_id == "source_topology_build"


def test_topic_coverage_audit_does_not_require_removed_profile_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from run_fixtures import populated_analysis_state

    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "understanding/analysis_state.json",
        populated_analysis_state(ctx.run_id, verified=False),
        skip_handoff=True,
    )
    issues = collect_stage_input_issues(ctx, "topic_coverage_audit")
    assert not any("operator-verified" in issue.message.lower() for issue in issues)
