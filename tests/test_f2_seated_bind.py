"""F2 seated bind: EDL must not flush vo_pickup; resynth then omit; refuse dirty EDL done.

Fixture shape from exec_11165 ``vo_layup_seg_012`` (sha-bound take gone, EDL pending
holds different bytes). Does not resume that run.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from interview_mux.artifact_sanitize.vo_synthesize import vo_sanitary_errors
from interview_mux.stage_completion import stage_artifact_incompleteness
from interview_mux.vo_bind_authority import heal_seated_bind_mismatch
from interview_mux.vo_synthesis_audit import record_synthesis, wav_content_sha256
from interview_mux.write_staging import (
    discard_non_owner_pending_vo_pickup,
    enter_stage_staging,
    exit_stage_staging,
    promote_glue_then_discard_stale_edl,
    resolve_write_path,
    staging_root,
)
from run_fixtures import isolated_run_ctx, patch_merged_config

_FIX = Path(__file__).resolve().parent / "fixtures" / "f2_seated_bind"
LINE_ID = "vo_layup_seg_012"


def _wav(path: Path, duration_ms: int = 300) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48_000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * duration_ms / 1000))


def _patch_vo_qc_off(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            },
            "artifact_sanitize": {"block_consumers": True},
        },
    )
    monkeypatch.setattr(
        "interview_mux.vo_speech_qa.vo_passes_speech_qa",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.analyze_vo_wav",
        lambda *_a, **_k: {"pass": True, "reasons": []},
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda *_a, **_k: False,
    )


def _plant_012_mismatch(ctx) -> dict:
    line = json.loads((_FIX / "gap_line.json").read_text(encoding="utf-8"))
    seats = json.loads((_FIX / "air_seats.json").read_text(encoding="utf-8"))
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.path("mastering").mkdir(parents=True, exist_ok=True)
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [line]},
        skip_handoff=True,
    )
    ctx.write_json("mastering/mastering_plan.json", seats, skip_handoff=True)
    good = ctx.path("vo_pickup", "synthesized", f"{LINE_ID}.wav")
    _wav(good, duration_ms=300)
    record_synthesis(ctx, line, backend="chatterbox", out_wav=good)
    bound = wav_content_sha256(good)
    seated = ctx.path("vo_pickup", f"{LINE_ID}.wav")
    seated.write_bytes(good.read_bytes())
    # EDL-promoted stale bytes overwrite committed (11165).
    _wav(good, duration_ms=900)
    seated.write_bytes(good.read_bytes())
    pending = (
        staging_root(ctx, "edl") / "vo_pickup" / "synthesized" / f"{LINE_ID}.wav"
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(good.read_bytes())
    (staging_root(ctx, "edl") / "vo_pickup" / f"{LINE_ID}.wav").write_bytes(
        good.read_bytes()
    )
    return {"line": line, "bound": bound}


def test_edl_glue_does_not_promote_stale_vo_pickup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_vo_qc_off(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "f2_glue_no_vo")
    planted = _plant_012_mismatch(ctx)
    committed = ctx.final_path("vo_pickup", "synthesized", f"{LINE_ID}.wav")
    before = wav_content_sha256(committed)
    assert before != planted["bound"]
    flush = promote_glue_then_discard_stale_edl(ctx)
    after = wav_content_sha256(committed)
    assert after == before
    assert after != planted["bound"]
    assert not (staging_root(ctx, "edl") / "vo_pickup").exists()
    assert any("vo_pickup" in x for x in (flush.get("discarded_vo_pickup") or []))


def test_edl_write_path_redirects_vo_pickup_off_edl_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_vo_qc_off(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "f2_redirect")
    enter_stage_staging("edl")
    try:
        dest = resolve_write_path(ctx, f"vo_pickup/synthesized/{LINE_ID}.wav")
    finally:
        exit_stage_staging()
    rel = dest.relative_to(ctx.run_dir).as_posix()
    assert ".pending_writes/vo_synthesize/" in rel
    assert ".pending_writes/edl/" not in rel


def test_heal_resynth_clears_seated_bind_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_vo_qc_off(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "f2_resynth")
    planted = _plant_012_mismatch(ctx)
    assert any("seated_bind_stale:vo_layup_seg_012" in e for e in vo_sanitary_errors(ctx))

    def _fake_synth(c, line, mode="synthesize"):
        lid = str(line.get("line_id"))
        out = c.path("vo_pickup", "synthesized", f"{lid}.wav")
        _wav(out, duration_ms=550)
        record_synthesis(
            c, line, backend="chatterbox", out_wav=out, wav_just_rendered=True
        )
        from interview_mux.s2s_runner import promote_synthesized_vo

        promote_synthesized_vo(c, line_id=lid, src=out)
        return out

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _fake_synth)
    notes = heal_seated_bind_mismatch(ctx, attempt_synth=True)
    assert LINE_ID in (notes.get("resynthesized") or [])
    assert not vo_sanitary_errors(ctx)
    committed = ctx.final_path("vo_pickup", "synthesized", f"{LINE_ID}.wav")
    assert wav_content_sha256(committed) != planted["bound"]
    assert not (staging_root(ctx, "edl") / "vo_pickup").exists()


def test_heal_omits_when_resynth_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_vo_qc_off(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "f2_omit")
    _plant_012_mismatch(ctx)
    assert any("seated_bind_stale:vo_layup_seg_012" in e for e in vo_sanitary_errors(ctx))

    def _boom(*_a, **_k):
        raise RuntimeError("chatterbox unavailable")

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _boom)
    notes = heal_seated_bind_mismatch(ctx, attempt_synth=True)
    assert LINE_ID in (notes.get("omitted") or [])
    assert not vo_sanitary_errors(ctx)
    gap = ctx.read_json("understanding/gap_report.json")
    row = (gap.get("interviewer_lines") or [])[0]
    assert row.get("air_script_omit") is True
    plan = ctx.read_json("mastering/mastering_plan.json")
    seated = (plan.get("air_script") or {}).get("vo_seats") or {}
    assert LINE_ID not in (seated.get("seated_line_ids") or [])
    assert LINE_ID in (seated.get("omitted_line_ids") or [])
    discarded = discard_non_owner_pending_vo_pickup(ctx)
    assert not (staging_root(ctx, "edl") / "vo_pickup").exists() or discarded is not None


def test_edl_stage_done_refused_while_bind_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_vo_qc_off(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "f2_refuse_edl")
    _plant_012_mismatch(ctx)
    edl_path = ctx.final_path("master", "edl.json")
    edl_path.parent.mkdir(parents=True, exist_ok=True)
    edl_path.write_text(
        json.dumps(
            {
                "version": 1,
                "ordered_segment_ids": ["seg_012"],
                "timeline_duration_ms": 1000,
                "clips": [],
            }
        ),
        encoding="utf-8",
    )
    reason = stage_artifact_incompleteness(ctx, "edl")
    assert reason is not None
    assert "seated_bind_stale" in reason or "vo_unsanitary" in reason or "stale" in reason
    assert any("seated_bind_stale:vo_layup_seg_012" in e for e in vo_sanitary_errors(ctx))
