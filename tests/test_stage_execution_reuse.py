"""Stage execution reuse from prior runs (same source audio)."""

from __future__ import annotations

import uuid
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
from interview_mux.write_staging import exit_stage_staging
from run_fixtures import (
    TEST_SOURCE_AUDIO_HASH,
    TEST_SOURCE_AUDIO_HASH_SHORT,
    init_run_meta_for_test,
)


def _patch_executions_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    executions = repo / "ASSETS" / "executions"
    executions.mkdir(parents=True)
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: repo)
    cfg = {
        **merged_config(),
        "assets_root": "ASSETS",
        "executions_root": "ASSETS/executions",
        "data_root": "data",
    }
    monkeypatch.setattr("interview_mux.config.merged_config", lambda: cfg)
    monkeypatch.setattr("interview_mux.run_context.merged_config", lambda: cfg)
    monkeypatch.setattr("interview_mux.stage_execution_reuse.merged_config", lambda: cfg)
    monkeypatch.setattr("interview_mux.write_staging.merged_config", lambda: cfg)
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: False,
    )
    return executions


def _ctx_in_root(run_id: str, executions_root: Path) -> RunContext:
    ctx = RunContext(run_id, create=True)
    init_run_meta_for_test(ctx, input_audio_path="ASSETS/input/demo.wav")
    return ctx


def test_find_candidates_require_hash_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_001_20260101T000000Z", tmp_path)
    current = _ctx_in_root("exec_002_20260101T000001Z", tmp_path)
    prior.write_json("transcript/full.json", {"segments": []})
    prior.write_json("transcript/speakers.json", {"speakers": []})
    prior.mark_done("transcribe")
    candidates = find_reuse_candidates(current, "transcribe")
    assert len(candidates) == 1
    assert candidates[0].match_kind == "hash"
    assert candidates[0].same_source_audio is True


def test_find_candidates_exclude_hash_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_001_20260101T000000Z", tmp_path)
    current = _ctx_in_root("exec_002_20260101T000001Z", tmp_path)
    init_run_meta_for_test(
        prior,
        source_audio_hash=TEST_SOURCE_AUDIO_HASH,
        source_audio_hash_short=TEST_SOURCE_AUDIO_HASH_SHORT,
    )
    init_run_meta_for_test(
        current,
        source_audio_hash="b" * 64,
        source_audio_hash_short="b" * 12,
    )
    prior.write_json("transcript/full.json", {"segments": []})
    prior.write_json("transcript/speakers.json", {"speakers": []})
    prior.mark_done("transcribe")
    assert find_reuse_candidates(current, "transcribe") == []


def test_find_candidates_exclude_incomplete_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_001_20260101T000000Z", tmp_path)
    current = _ctx_in_root("exec_002_20260101T000001Z", tmp_path)
    prior.write_json("transcript/full.json", {"segments": []})
    prior.mark_done("transcribe")
    assert find_reuse_candidates(current, "transcribe") == []


def test_find_candidates_same_input_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_001_20260101T000000Z", tmp_path)
    current = _ctx_in_root("exec_002_20260101T000001Z", tmp_path)
    other = _ctx_in_root("exec_003_20260101T000002Z", tmp_path)
    init_run_meta_for_test(
        other,
        input_audio_path="ASSETS/input/other.wav",
        source_audio_hash="c" * 64,
        source_audio_hash_short="c" * 12,
    )

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
    assert current.read_json("transcript/full.json")["text"] == "Hello corrected"
    from interview_mux.journey_state import read_run_meta

    assert read_run_meta(current).get("transcript_reuse_pending_edit") is True


def test_save_reused_transcript_text_clears_pending_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.transcript_review import save_reused_transcript_text
    from interview_mux.journey_state import read_run_meta

    _patch_executions_root(monkeypatch, tmp_path)
    ctx = _ctx_in_root("exec_014_20260101T000014Z", tmp_path)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "Hello world",
            "words": [
                {"text": "Hello", "start_ms": 0, "end_ms": 200},
                {"text": "world", "start_ms": 200, "end_ms": 400},
            ],
        },
    )
    ctx.write_json(
        "transcript/review_queue.json",
        {
            "chunks": [
                {
                    "chunk_id": "c1",
                    "start_ms": 0,
                    "end_ms": 400,
                    "text": "Hello world",
                    "confidence": 0.5,
                    "rank": 1,
                    "reviewed": False,
                    "needs_review": True,
                }
            ]
        },
    )
    ctx.write_json("transcript/corrections.json", {"corrections": {"c1": {"text": "stale"}}})
    ctx.mutate_run_meta(lambda m: m.update({"transcript_reuse_pending_edit": True}))

    result = save_reused_transcript_text(ctx, "Hello corrected world")
    assert "corrected" in result["text"]
    assert read_run_meta(ctx).get("transcript_reuse_pending_edit") is None
    assert ctx.is_done("transcript_review")
    assert ctx.read_json("operator/transcript_corrected.json")["text"]
    assert ctx.read_json("transcript/corrections.json")["corrections"] == {}


def test_dismiss_transcript_reuse_edit_clears_pending_without_completing_g0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.transcript_review import dismiss_transcript_reuse_edit
    from interview_mux.journey_state import read_run_meta

    _patch_executions_root(monkeypatch, tmp_path)
    ctx = _ctx_in_root("exec_015_20260101T000015Z", tmp_path)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "Hello world",
            "words": [
                {"text": "Hello", "start_ms": 0, "end_ms": 200},
                {"text": "world", "start_ms": 200, "end_ms": 400},
            ],
        },
    )
    ctx.write_json(
        "transcript/review_queue.json",
        {
            "chunks": [
                {
                    "chunk_id": "c1",
                    "start_ms": 0,
                    "end_ms": 400,
                    "text": "Hello world",
                    "confidence": 0.5,
                    "rank": 1,
                    "reviewed": False,
                    "needs_review": True,
                }
            ]
        },
    )
    ctx.mutate_run_meta(lambda m: m.update({"transcript_reuse_pending_edit": True}))

    result = dismiss_transcript_reuse_edit(ctx)
    assert result["dismissed"] is True
    assert read_run_meta(ctx).get("transcript_reuse_pending_edit") is None
    assert not ctx.is_done("transcript_review")


def test_finalize_reused_transcript_from_disk_uses_current_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.transcript_review import finalize_reused_transcript_from_disk
    from interview_mux.journey_state import read_run_meta

    _patch_executions_root(monkeypatch, tmp_path)
    ctx = _ctx_in_root("exec_016_20260101T000016Z", tmp_path)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "Hello dock world",
            "words": [
                {"text": "Hello", "start_ms": 0, "end_ms": 200},
                {"text": "dock", "start_ms": 200, "end_ms": 300},
                {"text": "world", "start_ms": 300, "end_ms": 400},
            ],
        },
    )
    ctx.write_json(
        "transcript/review_queue.json",
        {
            "chunks": [
                {
                    "chunk_id": "c1",
                    "start_ms": 0,
                    "end_ms": 400,
                    "text": "Hello dock world",
                    "confidence": 0.5,
                    "rank": 1,
                    "reviewed": False,
                    "needs_review": True,
                }
            ]
        },
    )
    ctx.mutate_run_meta(lambda m: m.update({"transcript_reuse_pending_edit": True}))

    result = finalize_reused_transcript_from_disk(ctx)
    assert result["text"] == "Hello dock world"
    assert read_run_meta(ctx).get("transcript_reuse_pending_edit") is None
    assert ctx.is_done("transcript_review")


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


def test_accept_reuse_marks_transcribe_done_when_bypassing_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transcript reuse copies to final paths and marks transcribe done even with write approval on."""
    exit_stage_staging()
    _patch_executions_root(monkeypatch, tmp_path)
    suffix = uuid.uuid4().hex[:8]
    prior_id = f"exec_reuse_prior_{suffix}"
    current_id = f"exec_reuse_current_{suffix}"
    prior = _ctx_in_root(prior_id, tmp_path)
    current = _ctx_in_root(current_id, tmp_path)

    prior.write_json("transcript/full.json", {"segments": []})
    prior.write_json("transcript/speakers.json", {"speakers": []})
    prior.mark_done("transcribe", force=True)

    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: True)

    record_reuse_decision(
        current, "transcribe", action="accept", source_run_id=prior_id
    )
    apply_stage_reuse(current, "transcribe", prior_id)
    assert current.is_done("transcribe")
    assert reuse_already_applied(current, "transcribe")
    assert resolve_before_stage_run(current, "transcribe") == "skipped"
    assert current.final_path("transcript/full.json").is_file()
    staging = current.run_dir / ".pending_writes" / "transcribe" / "transcript/full.json"
    assert not staging.is_file()


def test_transcript_review_reuse_does_not_mark_gate_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_070_20260101T000070Z", tmp_path)
    current = _ctx_in_root("exec_071_20260101T000071Z", tmp_path)

    prior.write_json("transcript/full.json", {"text": "Corrected hello", "words": []})
    prior.write_json("transcript/corrections.json", {"corrections": {}})
    prior.write_json(
        "transcript/review_queue.json",
        {
            "version": 1,
            "chunk_count": 0,
            "chunks": [],
        },
    )
    prior.write_json("operator/transcript_corrected.json", {"text": "Corrected hello"})
    prior.write_json("operator/transcript_corrections.json", {"corrections": {}})
    prior.path("operator/transcript_corrected.txt").write_text("Corrected hello", encoding="utf-8")
    prior.mark_done("transcript_review")

    apply_stage_reuse(current, "transcript_review", "exec_070_20260101T000070Z")
    assert not current.is_done("transcript_review")
    from interview_mux.journey_state import read_run_meta

    assert read_run_meta(current).get("transcript_reuse_pending_edit") is None


def test_transcript_review_build_reuse_does_not_set_pending_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_072_20260101T000072Z", tmp_path)
    current = _ctx_in_root("exec_073_20260101T000073Z", tmp_path)

    prior.write_json("transcript/full.json", {"text": "Hello", "words": []})
    prior.write_json("transcript/speakers.json", {"speakers": []})
    prior.write_json(
        "transcript/review_queue.json",
        {"version": 1, "chunk_count": 0, "chunks": []},
    )
    prior.mark_done("transcript_review_build")

    apply_stage_reuse(current, "transcript_review_build", "exec_072_20260101T000072Z")
    from interview_mux.journey_state import read_run_meta

    assert read_run_meta(current).get("transcript_reuse_pending_edit") is None


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


def test_find_candidates_prefilter_by_run_id_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    prior = _ctx_in_root("exec_001_beef00000001_20260101T000000Z", tmp_path)
    current = _ctx_in_root("exec_002_beef00000001_20260101T000001Z", tmp_path)
    other_hash = _ctx_in_root("exec_003_cafe00000002_20260101T000002Z", tmp_path)
    init_run_meta_for_test(
        other_hash,
        source_audio_hash="d" * 64,
        source_audio_hash_short="cafe00000002",
    )
    other_hash.write_json("transcript/full.json", {"segments": []})
    other_hash.write_json("transcript/speakers.json", {"speakers": []})
    other_hash.mark_done("transcribe")

    prior.write_json("transcript/full.json", {"segments": []})
    prior.write_json("transcript/speakers.json", {"speakers": []})
    prior.mark_done("transcribe")

    candidates = find_reuse_candidates(current, "transcribe")
    assert len(candidates) == 1
    assert candidates[0].run_id == "exec_001_beef00000001_20260101T000000Z"


def test_find_candidates_skip_immediate_prior_when_hash_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    reusable = _ctx_in_root("exec_010_20260101T000010Z", tmp_path)
    _ctx_in_root("exec_011_20260101T000011Z", tmp_path)
    current = _ctx_in_root("exec_012_20260101T000012Z", tmp_path)
    init_run_meta_for_test(
        reusable,
        source_audio_hash=TEST_SOURCE_AUDIO_HASH,
        source_audio_hash_short=TEST_SOURCE_AUDIO_HASH_SHORT,
    )
    init_run_meta_for_test(
        current,
        source_audio_hash=TEST_SOURCE_AUDIO_HASH,
        source_audio_hash_short=TEST_SOURCE_AUDIO_HASH_SHORT,
    )
    init_run_meta_for_test(
        RunContext("exec_011_20260101T000011Z", create=False),
        source_audio_hash="b" * 64,
        source_audio_hash_short="b" * 12,
    )
    reusable.write_json("transcript/full.json", {"segments": []})
    reusable.write_json("transcript/speakers.json", {"speakers": []})
    reusable.mark_done("transcribe")

    candidates = find_reuse_candidates(current, "transcribe")
    assert len(candidates) == 1
    assert candidates[0].run_id == "exec_010_20260101T000010Z"


def test_find_candidates_respect_lookback_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    reusable = _ctx_in_root("exec_001_20260101T000001Z", tmp_path)
    for n in range(2, 12):
        _ctx_in_root(f"exec_{n:03d}_20260101T0000{n:02d}Z", tmp_path)
        init_run_meta_for_test(
            RunContext(f"exec_{n:03d}_20260101T0000{n:02d}Z", create=False),
            source_audio_hash="b" * 64,
            source_audio_hash_short="b" * 12,
        )
    current = _ctx_in_root("exec_012_20260101T000012Z", tmp_path)
    init_run_meta_for_test(
        reusable,
        source_audio_hash=TEST_SOURCE_AUDIO_HASH,
        source_audio_hash_short=TEST_SOURCE_AUDIO_HASH_SHORT,
    )
    init_run_meta_for_test(
        current,
        source_audio_hash=TEST_SOURCE_AUDIO_HASH,
        source_audio_hash_short=TEST_SOURCE_AUDIO_HASH_SHORT,
    )
    reusable.write_json("transcript/full.json", {"segments": []})
    reusable.write_json("transcript/speakers.json", {"speakers": []})
    reusable.mark_done("transcribe")

    assert find_reuse_candidates(current, "transcribe") == []


def test_find_candidates_pick_most_recent_matching_in_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_executions_root(monkeypatch, tmp_path)
    older = _ctx_in_root("exec_008_20260101T000008Z", tmp_path)
    newer = _ctx_in_root("exec_010_20260101T000010Z", tmp_path)
    _ctx_in_root("exec_009_20260101T000009Z", tmp_path)
    current = _ctx_in_root("exec_012_20260101T000012Z", tmp_path)
    init_run_meta_for_test(
        RunContext("exec_009_20260101T000009Z", create=False),
        source_audio_hash="b" * 64,
        source_audio_hash_short="b" * 12,
    )
    for ctx in (older, newer, current):
        init_run_meta_for_test(
            ctx,
            source_audio_hash=TEST_SOURCE_AUDIO_HASH,
            source_audio_hash_short=TEST_SOURCE_AUDIO_HASH_SHORT,
        )
    for ctx in (older, newer):
        ctx.write_json("transcript/full.json", {"segments": []})
        ctx.write_json("transcript/speakers.json", {"speakers": []})
        ctx.mark_done("transcribe")

    candidates = find_reuse_candidates(current, "transcribe")
    assert len(candidates) == 1
    assert candidates[0].run_id == "exec_010_20260101T000010Z"
