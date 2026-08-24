"""Product delivery_recovery helpers (archive restore, G1, resume)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from interview_mux.delivery_recovery import (
    ensure_g1_pickups,
    ensure_mmaudio_qa_before_mix,
    newest_archived,
    restore_master_artifact,
    suggest_delivery_resume,
)
from interview_mux.durable_jobs import begin_job, complete_unit, load_job, pending_units


def _ctx(tmp_path: Path):
    from interview_mux.run_context import RunContext

    run_dir = tmp_path / "exec_del"
    run_dir.mkdir()
    (run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    ctx = RunContext.__new__(RunContext)
    ctx.run_dir = run_dir
    ctx.run_id = "exec_del"

    def final_path(*parts: str) -> Path:
        return run_dir.joinpath(*parts)

    def artifact_exists(rel: str) -> bool:
        return (run_dir / rel).is_file()

    def read_json(rel: str):
        return json.loads((run_dir / rel).read_text(encoding="utf-8"))

    def is_done(sid: str) -> bool:
        return (run_dir / ".stage_done" / sid).is_file()

    def log(*_a, **_k):
        return None

    ctx.final_path = final_path  # type: ignore[method-assign]
    ctx.artifact_exists = artifact_exists  # type: ignore[method-assign]
    ctx.read_json = read_json  # type: ignore[method-assign]
    ctx.is_done = is_done  # type: ignore[method-assign]
    ctx.log = log  # type: ignore[method-assign]
    return ctx


def test_restore_master_artifact_from_archive(tmp_path: Path):
    ctx = _ctx(tmp_path)
    arch = ctx.run_dir / ".archived" / "20260814T120000Z" / "master"
    arch.mkdir(parents=True)
    src = arch / "assembly.wav"
    src.write_bytes(b"RIFF" + b"\x00" * 2000)
    assert newest_archived(ctx, "master/assembly.wav") == src
    dest = restore_master_artifact(ctx, "master/assembly.wav", min_bytes=1000)
    assert dest is not None and dest.is_file()
    assert dest.read_bytes()[:4] == b"RIFF"


def test_suggest_delivery_resume_with_assembly(tmp_path: Path):
    ctx = _ctx(tmp_path)
    master = ctx.run_dir / "master"
    master.mkdir()
    (master / "edl.json").write_text("{}", encoding="utf-8")
    (master / "assembly.wav").write_bytes(b"x" * 100)
    assert suggest_delivery_resume(ctx) == "junction_snip_qa"

    done = ctx.run_dir / ".stage_done"
    done.mkdir()
    (done / "junction_snip_qa").write_text("1", encoding="utf-8")
    assert suggest_delivery_resume(ctx) in {
        "master_finalize",
        "master_transcript_build",
        "junction_snip_qa",
        "episode_meta_build",
        "episode_cover_prompt_craft",
        "podcast_encode_mp3",
        "episode_cover_generate",
        "podcast_publish",
    }


def test_ensure_mmaudio_qa_before_mix(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert ensure_mmaudio_qa_before_mix(ctx)["ok"] is False
    sd = ctx.run_dir / "sound_design"
    sd.mkdir()
    (sd / "mmaudio_qa.json").write_text("{}", encoding="utf-8")
    assert ensure_mmaudio_qa_before_mix(ctx)["ok"] is True


def test_durable_job_resume_units(tmp_path: Path):
    ctx = _ctx(tmp_path)
    job = begin_job(
        ctx,
        stage_id="g1_vo",
        job_id="ensure_pickups",
        units=["line_a", "line_b"],
        input_payload={"line_ids": ["line_a", "line_b"]},
    )
    assert set(pending_units(job)) == {"line_a", "line_b"}
    complete_unit(
        ctx,
        "g1_vo",
        "ensure_pickups",
        "line_a",
        output_path="vo_pickup/line_a.wav",
    )
    job2 = load_job(ctx, "g1_vo", "ensure_pickups")
    assert pending_units(job2) == ["line_b"]
    assert job2["status"] == "partial"


def test_ensure_g1_pickups_missing_gap_report(tmp_path: Path):
    ctx = _ctx(tmp_path)
    out = ensure_g1_pickups(ctx, heal_spoken_copy=False)
    assert out["ok"] is False
    assert out["error"] == "missing_gap_report"


def test_ensure_g1_pickups_synthesizes_missing(tmp_path: Path, monkeypatch):
    ctx = _ctx(tmp_path)
    und = ctx.run_dir / "understanding"
    und.mkdir()
    (und / "gap_report.json").write_text(
        json.dumps(
            {
                "interviewer_lines": [
                    {
                        "line_id": "vo_1",
                        "delivery": "synthesize",
                        "text": "Hello there.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    fake_out = ctx.run_dir / "vo_pickup" / "synthesized" / "vo_1.wav"
    fake_out.parent.mkdir(parents=True)
    fake_out.write_bytes(b"wav")

    synth = MagicMock(return_value=fake_out)
    promote = MagicMock(return_value=fake_out)
    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", synth)
    monkeypatch.setattr("interview_mux.s2s_runner.promote_synthesized_vo", promote)
    monkeypatch.setattr(
        "interview_mux.stages.assembly.resolve_vo_pickup_path",
        lambda *_a, **_k: None,
    )

    state = {"n": 0}

    def _check(_ctx):
        state["n"] += 1
        return ["vo_1"] if state["n"] == 1 else []

    monkeypatch.setattr("interview_mux.gates.check_g1_vo", _check)

    out = ensure_g1_pickups(ctx, heal_spoken_copy=False, promote=True)
    assert "vo_1" in out["synthesized"]
    synth.assert_called_once()
    assert out.get("job")


def test_suggest_resume_unmarks_hollow_music_when_theme_wavs_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from run_fixtures import isolated_run_ctx, sound_design_plan_with

    ctx = isolated_run_ctx(tmp_path, "exec_theme_gap")
    master = ctx.run_dir / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "edl.json").write_text("{}", encoding="utf-8")
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "show_theme_v1_motif",
                    "role": "theme_cold_open",
                    "description": "motif",
                    "duration_seconds": 12,
                }
            ]
        ),
        skip_handoff=True,
    )
    done = ctx.run_dir / ".stage_done"
    done.mkdir(exist_ok=True)
    for sid in ("music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx"):
        (done / sid).write_text("1", encoding="utf-8")
    assert suggest_delivery_resume(ctx) == "music_palette_compose"
    assert not ctx.is_done("mmaudio_sfx")
    assert not ctx.is_done("sfx_prompt_craft")
    assert not ctx.is_done("music_palette_compose")


def test_resume_theme_generation_keeps_mix_when_wavs_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from interview_mux.delivery_recovery import resume_theme_generation
    from run_fixtures import isolated_run_ctx, sound_design_plan_with

    ctx = isolated_run_ctx(tmp_path, "exec_theme_keep")
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "show_theme_v1_motif",
                    "role": "theme_cold_open",
                    "description": "motif",
                    "duration_seconds": 12,
                }
            ]
        ),
        skip_handoff=True,
    )
    wav = ctx.run_dir / "sound_design" / "assets" / "show_theme_v1_motif.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    assert resume_theme_generation(ctx) == "mix"
    assert ctx.is_done("mmaudio_sfx")
