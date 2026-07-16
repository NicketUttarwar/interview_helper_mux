"""Tests for numbered stage steps in GUI guidance."""

from __future__ import annotations

from interview_mux.stage_guidance import STAGE_UNLOCKS, build_stage_guidance
from interview_mux.stage_steps import attach_steps_to_guidance, build_stage_steps
from interview_mux.web.stages import STAGE_BY_ID
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def test_every_stage_has_steps(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_all")
    init_run_meta_for_test(ctx)
    for stage_id in STAGE_BY_ID:
        guidance = build_stage_guidance(ctx, stage_id, status="pending")
        attach_steps_to_guidance(ctx, stage_id, guidance, status="pending")
        steps = guidance.get("steps") or []
        assert steps, f"{stage_id} has no steps"
        numbers = [s["number"] for s in steps]
        assert numbers == list(range(1, len(numbers) + 1)), stage_id
        ids = [s["id"] for s in steps]
        assert len(ids) == len(set(ids)), f"{stage_id} duplicate step ids"


def test_stage_unlocks_covers_steps() -> None:
    missing = set(STAGE_BY_ID) - set(STAGE_UNLOCKS)
    assert not missing


def test_ingest_steps_include_run_and_write(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_ingest")
    init_run_meta_for_test(ctx)
    guidance = build_stage_guidance(ctx, "ingest", status="pending")
    steps = build_stage_steps(ctx, "ingest", status="pending", guidance=guidance)
    kinds = {s["kind"] for s in steps}
    assert "info" in kinds
    assert "run" in kinds


def test_g0_gate_steps(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_g0")
    init_run_meta_for_test(ctx)
    guidance = build_stage_guidance(ctx, "transcript_review", status="action_required")
    steps = build_stage_steps(ctx, "transcript_review", status="action_required", guidance=guidance)
    assert len(steps) == 1
    assert steps[0]["id"] == "review_transcript"
    assert steps[0]["embed"] == "transcript_review"
    assert steps[0]["primary_button"] == "Complete transcript review"


def test_locked_stage_single_step(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_locked")
    init_run_meta_for_test(ctx)
    guidance = build_stage_guidance(ctx, "speaker_roles", status="locked")
    steps = build_stage_steps(ctx, "speaker_roles", status="locked", guidance=guidance)
    assert len(steps) == 1
    assert steps[0]["kind"] == "locked"


def test_done_stage_summary(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_done")
    init_run_meta_for_test(ctx)
    ctx.mark_done("ingest")
    guidance = build_stage_guidance(ctx, "ingest", status="done")
    steps = build_stage_steps(ctx, "ingest", status="done", guidance=guidance)
    assert steps[0]["kind"] == "done"


def test_preclean_steps_after_accept_before_run(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_preclean_accept")
    init_run_meta_for_test(ctx)
    meta = ctx.read_json("run_meta.json")
    meta["audio_preclean"] = {
        "enabled": True,
        "scope": "full_source",
        "decisions": [{"checkpoint": "before_ingest", "action": "accept"}],
    }
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    guidance = build_stage_guidance(ctx, "audio_preclean", status="pending")
    steps = build_stage_steps(ctx, "audio_preclean", status="pending", guidance=guidance)
    by_id = {s["id"]: s for s in steps}
    assert by_id["review_offer"]["status"] == "done"
    assert by_id["wait_run"]["status"] == "waiting"
    assert "continue_ingest" not in by_id
    assert "write_approval" not in by_id


def test_preclean_steps_while_running(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_preclean_running")
    init_run_meta_for_test(ctx)
    meta = ctx.read_json("run_meta.json")
    meta["audio_preclean"] = {
        "enabled": True,
        "scope": "full_source",
        "decisions": [{"checkpoint": "before_ingest", "action": "accept"}],
    }
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    ctx.write_json(
        "gui_job.json",
        {"status": "running", "stage": "audio_preclean", "current_stage": "audio_preclean"},
        skip_handoff=True,
    )
    guidance = build_stage_guidance(ctx, "audio_preclean", status="pending")
    steps = build_stage_steps(ctx, "audio_preclean", status="pending", guidance=guidance)
    by_id = {s["id"]: s for s in steps}
    assert by_id["review_offer"]["status"] == "done"
    assert by_id["wait_run"]["status"] == "active"
    assert "continue_ingest" not in by_id


def test_preclean_steps_awaiting_write_approval(tmp_path, monkeypatch) -> None:
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    monkeypatch.setattr(
        "interview_mux.write_staging.merged_config",
        lambda: {"journey_ui": {"require_write_approval_per_stage": True}},
    )
    ctx = isolated_run_ctx(tmp_path, "steps_preclean_write")
    init_run_meta_for_test(ctx)
    meta = ctx.read_json("run_meta.json")
    meta["audio_preclean"] = {
        "enabled": True,
        "scope": "full_source",
        "decisions": [{"checkpoint": "before_ingest", "action": "accept"}],
    }
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    enter_stage_staging("audio_preclean")
    iso = ctx.path("preclean/isolated.wav")
    iso.parent.mkdir(parents=True, exist_ok=True)
    iso.write_bytes(b"wav")
    ctx.path("preclean/lineage.json").write_text("{}", encoding="utf-8")
    exit_stage_staging()
    guidance = build_stage_guidance(ctx, "audio_preclean", status="awaiting_write_approval")
    steps = build_stage_steps(
        ctx, "audio_preclean", status="awaiting_write_approval", guidance=guidance
    )
    by_id = {s["id"]: s for s in steps}
    assert by_id["review_offer"]["status"] == "done"
    assert by_id["wait_run"]["status"] == "done"
    assert by_id["write_approval"]["status"] == "todo"
    assert "continue_ingest" not in by_id


def test_automated_steps_awaiting_write_marks_run_done(tmp_path, monkeypatch) -> None:
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    monkeypatch.setattr(
        "interview_mux.write_staging.merged_config",
        lambda: {"journey_ui": {"require_write_approval_per_stage": True}},
    )
    ctx = isolated_run_ctx(tmp_path, "steps_ingest_write")
    init_run_meta_for_test(ctx)
    enter_stage_staging("ingest")
    wav = ctx.path("ingest/normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"wav")
    ctx.path("ingest/checksums.json").write_text("{}", encoding="utf-8")
    exit_stage_staging()
    guidance = build_stage_guidance(ctx, "ingest", status="awaiting_write_approval")
    steps = build_stage_steps(ctx, "ingest", status="awaiting_write_approval", guidance=guidance)
    by_id = {s["id"]: s for s in steps}
    assert by_id["run"]["status"] == "done"
    assert by_id["write_approval"]["status"] == "todo"
    assert "complete" not in by_id


def test_automated_steps_gate_blocks_write_approval(tmp_path, monkeypatch) -> None:
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    monkeypatch.setattr(
        "interview_mux.write_staging.merged_config",
        lambda: {"journey_ui": {"require_write_approval_per_stage": True}},
    )
    ctx = isolated_run_ctx(tmp_path, "steps_speaker_gate")
    init_run_meta_for_test(ctx)
    enter_stage_staging("speaker_roles")
    state = ctx.path("understanding/analysis_state.json")
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{}", encoding="utf-8")
    exit_stage_staging()
    ctx.write_json(
        "gui_job.json",
        {
            "status": "gate",
            "stage": "speaker_roles",
            "message": "LLM stage gate (speaker_roles): artifact not complete (status=blocked).",
        },
        skip_handoff=True,
    )
    guidance = build_stage_guidance(ctx, "speaker_roles", status="action_required")
    steps = build_stage_steps(ctx, "speaker_roles", status="action_required", guidance=guidance)
    by_id = {s["id"]: s for s in steps}
    assert "write_approval" not in by_id
    assert by_id["llm_gate"]["status"] == "todo"
    assert by_id["run"]["status"] == "done"


def test_preclean_steps_done(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "steps_preclean_done")
    init_run_meta_for_test(ctx)
    ctx.mark_done("audio_preclean")
    guidance = build_stage_guidance(ctx, "audio_preclean", status="done")
    steps = build_stage_steps(ctx, "audio_preclean", status="done", guidance=guidance)
    kinds = [s["kind"] for s in steps]
    assert "done" in kinds
    assert any(s["id"] == "continue_ingest" for s in steps)
