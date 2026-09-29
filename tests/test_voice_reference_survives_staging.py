"""The approved voice reference must survive a staged flush, and heal if it does not.

Regression for a real stop on exec_016: ``approve_voice_reference`` builds
``understanding/speaker_samples/<sid>.wav``, duration-checks it, then writes a
manifest naming it. The WAV was not in the ownership catalog, so
``flush_stage_writes`` dropped it as ``unknown_path`` while the manifest (an
``operational`` path) landed. The run was left holding an approval that pointed
at a file which did not exist, and hard-stopped 40 stages later with
``voice_reference_unusable``.

That state had no way out: the approval stamp keeps
``check_voice_reference_pending`` False, so no gate reopens it and no recovery
playbook covers it. Both halves are pinned here, because either one alone still
leaves a run that cannot finish.
"""

from __future__ import annotations

import pytest

from interview_mux.artifact_ownership import write_permitted
from interview_mux.run_context import RunContext


@pytest.fixture
def tmp_run_ctx() -> RunContext:
    """A bare run. conftest's redirect_executions_root keeps it under tmp_path."""
    rid = "exec_900_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


# --- half one: the artifact is owned, so a staged flush keeps it -------------


@pytest.mark.parametrize(
    "rel",
    [
        "understanding/speaker_samples/spk_0.wav",
        "understanding/speaker_samples/spk_1.wav",
        "understanding/speaker_samples/spk_0.json",
    ],
)
def test_approved_reference_paths_are_owned(tmp_run_ctx, rel: str) -> None:
    """unknown_path here means flush_stage_writes silently deletes the file."""
    allowed, reason = write_permitted(
        tmp_run_ctx, rel, "missing_framing", role="producer", verb="persist"
    )
    assert allowed, f"{rel} would be dropped at flush ({reason})"


def test_reference_manifest_and_its_wav_agree_on_ownership(tmp_run_ctx) -> None:
    """The manifest and the WAV it names must land together or neither is usable.

    This is the asymmetry that caused the original failure: one side owned, the
    other not, so the run ended up with a dangling approval.
    """
    manifest_ok, _ = write_permitted(
        tmp_run_ctx,
        "understanding/voice_reference/spk_0.json",
        "missing_framing",
        role="producer",
        verb="persist",
    )
    wav_ok, _ = write_permitted(
        tmp_run_ctx,
        "understanding/speaker_samples/spk_0.wav",
        "missing_framing",
        role="producer",
        verb="persist",
    )
    assert manifest_ok == wav_ok, (
        "the approval manifest and the WAV it points at must be equally "
        "persistable, or an approval can outlive its audio"
    )


# --- half two: an approval with no audio repairs itself ----------------------


def test_unusable_reference_is_repaired_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    """vo_path_ready must rebuild once before reporting voice_reference_unusable."""
    from interview_mux import gap_vo_gates as g

    calls: list[str] = []

    monkeypatch.setattr(g, "gap_fill_was_skipped", lambda ctx: False)
    monkeypatch.setattr(g, "gap_framing_enabled", lambda ctx: True)
    monkeypatch.setattr(g, "check_gap_framing_decision_pending", lambda ctx: False)
    monkeypatch.setattr(g, "pickup_speaker_confirmed", lambda ctx: True)
    monkeypatch.setattr(g, "voice_reference_approved", lambda ctx: True)
    monkeypatch.setattr(g, "_run_meta", lambda ctx: {"gap_vo_delivery": "chatterbox"})
    monkeypatch.setattr(g, "resolve_gap_vo_delivery", lambda ctx: "chatterbox")
    monkeypatch.setattr(g, "check_clone_consent_pending", lambda ctx: False)
    monkeypatch.setattr(g, "approved_voice_reference_usable", lambda ctx: False)

    def fake_repair(ctx):
        calls.append("repair")
        return True

    monkeypatch.setattr(g, "repair_unusable_voice_reference", fake_repair)

    ok, reason = g.vo_path_ready(object())
    assert calls == ["repair"], "the dead-end state must attempt a rebuild"
    assert reason != "voice_reference_unusable"
    assert ok, "a successful rebuild must let the VO ladder proceed"


def test_failed_repair_still_reports_unusable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rebuild that cannot succeed must stop loudly, not pretend readiness."""
    from interview_mux import gap_vo_gates as g

    monkeypatch.setattr(g, "gap_fill_was_skipped", lambda ctx: False)
    monkeypatch.setattr(g, "gap_framing_enabled", lambda ctx: True)
    monkeypatch.setattr(g, "check_gap_framing_decision_pending", lambda ctx: False)
    monkeypatch.setattr(g, "pickup_speaker_confirmed", lambda ctx: True)
    monkeypatch.setattr(g, "voice_reference_approved", lambda ctx: True)
    monkeypatch.setattr(g, "_run_meta", lambda ctx: {"gap_vo_delivery": "chatterbox"})
    monkeypatch.setattr(g, "resolve_gap_vo_delivery", lambda ctx: "chatterbox")
    monkeypatch.setattr(g, "check_clone_consent_pending", lambda ctx: False)
    monkeypatch.setattr(g, "approved_voice_reference_usable", lambda ctx: False)
    monkeypatch.setattr(g, "repair_unusable_voice_reference", lambda ctx: False)

    ok, reason = g.vo_path_ready(object())
    assert (ok, reason) == (False, "voice_reference_unusable")


def test_repair_is_attempted_at_most_once_per_run(tmp_run_ctx, monkeypatch) -> None:
    """A marker caps the rebuild so a broken source cannot loop forever."""
    from interview_mux import gap_vo_gates as g

    monkeypatch.setattr(g, "approved_voice_reference_usable", lambda ctx: False)
    monkeypatch.setattr(g, "pickup_eligible_speaker_id", lambda ctx: "spk_0")

    attempts: list[str] = []

    def boom(ctx, sid):
        attempts.append(sid)
        raise ValueError("no reference audio")

    import interview_mux.voice_reference as vr

    monkeypatch.setattr(vr, "approve_voice_reference", boom)

    assert g.repair_unusable_voice_reference(tmp_run_ctx) is False
    assert g.repair_unusable_voice_reference(tmp_run_ctx) is False
    assert attempts == ["spk_0"], "repair must not retry a failure on every check"


# --- the decisive one: it survives an actual flush ---------------------------


def _staging_ctx(tmp_path, monkeypatch) -> RunContext:
    """A run with per-stage write approval on, which is what stages writes."""
    from run_fixtures import patch_merged_config

    root = tmp_path / "repo"
    (root / "ASSETS" / "executions").mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    patch_merged_config(
        monkeypatch,
        {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {"require_write_approval_per_stage": True},
        },
    )
    rid = "exec_901_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_speaker_sample_wav_survives_a_real_flush(tmp_path, monkeypatch) -> None:
    """End to end through flush_stage_writes, not just the write_permitted gate.

    This is the assertion that would have caught the original bug. The gate test
    above pins the catalog, but the failure the operator actually saw was a file
    that vanished between being written and being read, so the flush itself is
    what needs pinning.
    """
    from interview_mux.write_staging import (
        enter_stage_staging,
        exit_stage_staging,
        flush_stage_writes,
    )

    ctx = _staging_ctx(tmp_path, monkeypatch)
    rel_wav = "understanding/speaker_samples/spk_0.wav"
    rel_manifest = "understanding/voice_reference/spk_0.json"

    enter_stage_staging("missing_framing")
    try:
        wav = ctx.path(*rel_wav.split("/"))
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(b"RIFF" + b"0" * 512)
        ctx.write_json(rel_manifest, {"speaker_id": "spk_0", "wav": rel_wav})
    finally:
        exit_stage_staging()

    # Both were staged, so neither is committed yet.
    assert not ctx.final_path(*rel_wav.split("/")).is_file()

    flushed = flush_stage_writes(ctx, "missing_framing")

    assert rel_wav in flushed, (
        "the approved reference WAV was dropped by the flush that was supposed to "
        f"commit it; flushed={sorted(flushed)}"
    )
    assert ctx.final_path(*rel_wav.split("/")).is_file()
    assert ctx.final_path(*rel_manifest.split("/")).is_file(), (
        "the manifest must land too, otherwise the pair is inconsistent the other way"
    )


def test_manifest_never_lands_without_its_wav(tmp_path, monkeypatch) -> None:
    """The specific inconsistency that stranded the run: approval without audio.

    Stated as a property rather than a path list, so it keeps holding if the
    layout changes.
    """
    from interview_mux.write_staging import (
        enter_stage_staging,
        exit_stage_staging,
        flush_stage_writes,
    )

    ctx = _staging_ctx(tmp_path, monkeypatch)
    rel_wav = "understanding/speaker_samples/spk_0.wav"
    rel_manifest = "understanding/voice_reference/spk_0.json"

    enter_stage_staging("missing_framing")
    try:
        wav = ctx.path(*rel_wav.split("/"))
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(b"RIFF" + b"0" * 512)
        ctx.write_json(rel_manifest, {"speaker_id": "spk_0", "wav": rel_wav})
    finally:
        exit_stage_staging()

    flush_stage_writes(ctx, "missing_framing")

    manifest_landed = ctx.final_path(*rel_manifest.split("/")).is_file()
    wav_landed = ctx.final_path(*rel_wav.split("/")).is_file()
    assert not (manifest_landed and not wav_landed), (
        "an approval manifest landed while the WAV it names did not: this is the "
        "dangling-approval state that no gate can recover from"
    )
