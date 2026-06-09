"""Stage execution reuse from prior runs (same source audio)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.config import merged_config
from interview_mux.file_store import write_json as fs_write_json
from interview_mux.run_context import RunContext
from interview_mux.stage_execution_reuse import (
    StageReuseOfferPending,
    apply_stage_reuse,
    configure_stage_reuse_cli,
    find_reuse_candidates,
    record_reuse_decision,
    reset_stage_reuse_cli,
    resolve_before_stage_run,
    reuse_already_applied,
)
from run_fixtures import init_run_meta_for_test


def _patch_executions_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "ASSETS" / "executions"
    root.mkdir(parents=True)
    cfg = {**merged_config(), "executions_root": str(root), "assets_root": str(tmp_path / "ASSETS")}
    monkeypatch.setattr("interview_mux.config.merged_config", lambda: cfg)
    monkeypatch.setattr("interview_mux.run_context.merged_config", lambda: cfg)
    monkeypatch.setattr("interview_mux.stage_execution_reuse.merged_config", lambda: cfg)
    monkeypatch.setattr("interview_mux.write_staging.merged_config", lambda: cfg)
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: False,
    )
    return root


def _ctx_in_root(run_id: str, executions_root: Path) -> RunContext:
    ctx = RunContext(run_id, create=True)
    init_run_meta_for_test(ctx, input_audio_path="ASSETS/input/demo.wav")
    return ctx


def test_find_candidates_same_input_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_001_20260101T000000Z", tmp_path)
    current = _ctx_in_root("exec_002_20260101T000001Z", tmp_path)
    other = _ctx_in_root("exec_003_20260101T000002Z", tmp_path)
    init_run_meta_for_test(other, input_audio_path="ASSETS/input/other.wav")

    prior.write_json("transcript/full.json", {"segments": []})
    prior.write_json("transcript/speakers.json", {"speakers": []})
    prior.mark_done("transcribe")

    candidates = find_reuse_candidates(current, "transcribe")
    assert len(candidates) == 1
    assert candidates[0].run_id == "exec_001_20260101T000000Z"
    assert "source_audio_hash" in candidates[0].to_dict()

    other.write_json("transcript/full.json", {"segments": []})
    other.write_json("transcript/speakers.json", {"speakers": []})
    other.mark_done("transcribe")
    assert len(find_reuse_candidates(current, "transcribe")) == 1


def test_apply_reuse_copies_and_marks_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_010_20260101T000010Z", tmp_path)
    current = _ctx_in_root("exec_011_20260101T000011Z", tmp_path)

    prior.write_json("transcript/full.json", {"segments": [{"id": "s1"}]})
    prior.write_json("transcript/speakers.json", {"speakers": [{"id": "spk_0"}]})
    prior.mark_done("transcribe")

    record_reuse_decision(
        current, "transcribe", action="accept", source_run_id="exec_010_20260101T000010Z"
    )
    copied = apply_stage_reuse(current, "transcribe", "exec_010_20260101T000010Z")
    assert "transcript/full.json" in copied
    assert current.is_done("transcribe")
    data = current.read_json("transcript/full.json")
    assert data["segments"][0]["id"] == "s1"


def test_apply_reuse_copies_operator_transcript_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_012_20260101T000012Z", tmp_path)
    current = _ctx_in_root("exec_013_20260101T000013Z", tmp_path)

    prior.write_json("transcript/full.json", {"text": "Hello", "words": []})
    prior.write_json("transcript/speakers.json", {"speakers": []})
    prior.write_json("operator/transcript_corrected.json", {"text": "Hello corrected", "words": []})
    prior.path("operator/transcript_corrected.txt").parent.mkdir(parents=True, exist_ok=True)
    prior.path("operator/transcript_corrected.txt").write_text("Hello corrected", encoding="utf-8")
    prior.mark_done("transcribe")

    copied = apply_stage_reuse(current, "transcribe", "exec_012_20260101T000012Z")
    assert "operator/transcript_corrected.json" in copied
    assert "operator/transcript_corrected.txt" in copied
    assert current.read_json("operator/transcript_corrected.json")["text"] == "Hello corrected"


def test_decline_runs_fresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_020_20260101T000020Z", tmp_path)
    current = _ctx_in_root("exec_021_20260101T000021Z", tmp_path)
    prior.path("ingest").mkdir(exist_ok=True)
    (prior.path("ingest") / "normalized.wav").write_bytes(b"RIFF" + b"\0" * 40)
    fs_write_json(
        prior.path("ingest/checksums.json"),
        {
            "source_path": "ASSETS/input/demo.wav",
            "source_sha256": "a" * 64,
            "normalized_sha256": "b" * 64,
            "sample_rate": 48000,
        },
    )
    prior.mark_done("ingest")

    record_reuse_decision(current, "ingest", action="decline")
    assert resolve_before_stage_run(current, "ingest") == "run"


def test_resolve_raises_when_offer_needed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_030_20260101T000030Z", tmp_path)
    current = _ctx_in_root("exec_031_20260101T000031Z", tmp_path)
    prior.path("ingest").mkdir(exist_ok=True)
    (prior.path("ingest") / "normalized.wav").write_bytes(b"RIFF" + b"\0" * 40)
    fs_write_json(
        prior.path("ingest/checksums.json"),
        {
            "source_path": "ASSETS/input/demo.wav",
            "source_sha256": "a" * 64,
            "normalized_sha256": "b" * 64,
            "sample_rate": 48000,
        },
    )
    prior.mark_done("ingest")

    with pytest.raises(StageReuseOfferPending) as exc:
        resolve_before_stage_run(current, "ingest")
    assert exc.value.stage_id == "ingest"
    assert exc.value.candidates[0].run_id == "exec_030_20260101T000030Z"


def test_auto_reuse_from_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_040_20260101T000040Z", tmp_path)
    current = _ctx_in_root("exec_041_20260101T000041Z", tmp_path)
    fs_write_json(
        prior.path("understanding/speakers.json"),
        {
            "speakers": [
                {
                    "speaker_id": "spk_0",
                    "role": "interviewer",
                    "confidence": 0.9,
                    "label": "Speaker 1",
                }
            ]
        },
    )
    prior.mark_done("speaker_roles")

    configure_stage_reuse_cli(reuse_from="exec_040_20260101T000040Z", no_reuse_offers=False)
    try:
        assert resolve_before_stage_run(current, "speaker_roles") == "skipped"
        assert current.is_done("speaker_roles")
    finally:
        reset_stage_reuse_cli()


def test_accept_reuse_not_reapplied_when_staged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: True)
    prior = _ctx_in_root("exec_060_20260101T000060Z", tmp_path)
    current = _ctx_in_root("exec_061_20260101T000061Z", tmp_path)

    prior.write_json("transcript/full.json", {"segments": []})
    prior.write_json("transcript/speakers.json", {"speakers": []})
    prior.mark_done("transcribe")

    record_reuse_decision(
        current, "transcribe", action="accept", source_run_id="exec_060_20260101T000060Z"
    )
    apply_stage_reuse(current, "transcribe", "exec_060_20260101T000060Z")
    assert not current.is_done("transcribe")
    assert reuse_already_applied(current, "transcribe")
    assert resolve_before_stage_run(current, "transcribe") == "skipped"


def test_clear_stage_reuse_on_invalidate(tmp_path: Path, monkeypatch) -> None:
    from interview_mux.pipeline import ANALYSIS_ORDER
    from interview_mux.stage_execution_reuse import clear_stage_reuse_from

    _patch_executions_root(monkeypatch, tmp_path)
    ctx = _ctx_in_root("exec_050_20260101T000050Z", tmp_path)
    record_reuse_decision(ctx, "ingest", action="accept", source_run_id="exec_001")
    record_reuse_decision(ctx, "transcribe", action="decline")
    clear_stage_reuse_from(ctx, "ingest", ANALYSIS_ORDER)
    meta = ctx.read_json("run_meta.json")
    assert "ingest" not in (meta.get("stage_reuse") or {})
    assert "transcribe" not in (meta.get("stage_reuse") or {})
